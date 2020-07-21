from datetime import datetime
import json
import logging
import requests
import time

import dateutil.parser
from oandapyV20 import API
from oandapyV20.endpoints import accounts
from oandapyV20.endpoints import instruments
from oandapyV20.endpoints import orders
from oandapyV20.endpoints import positions
from oandapyV20.endpoints import trades
from oandapyV20.endpoints.pricing import PricingInfo
from oandapyV20.endpoints.pricing import PricingStream
from oandapyV20.exceptions import V20Error

import constants
from platforms import Balance
from platforms import Ticker
from platforms import Order
from platforms import OrderTimeoutError
from platforms import Trade
import settings


ORDER_FILLED = 'FILLED'

logger = logging.getLogger(__name__)


class APIClient(object):
    def __init__(self, access_token, account_id, environment='practice'):
        self.access_token = access_token
        self.account_id = account_id
        self.client = API(access_token=access_token, environment=environment)

    def get_balance(self) -> Balance:
        req = accounts.AccountSummary(accountID=self.account_id)
        try:
            resp = self.client.request(req)
        except V20Error as e:
            logger.error(f'action=get_balance error={e}')
            raise

        available = resp['account']['balance']
        currency = resp['account']['currency']
        require_collateral = resp['account']['marginUsed']
        return Balance(currency, available, require_collateral)

    # def get_open_position(self):
    #     req = positions.PositionList(accountID=self.account_id)
    #     try:
    #         resp = self.client.request(req)
    #     except V20Error as e:
    #         logger.error(f'action=get_balance error={e}')
    #         raise
    #
    #     available = resp['account']['balance']
    #     currency = resp['account']['currency']
    #     return resp

    def get_ticker(self, product_code) -> Ticker:
        params = {
            'instruments': product_code
        }
        req = PricingInfo(accountID=self.account_id, params=params)
        try:
            resp = self.client.request(req)
        except V20Error as e:
            logger.error(f'action=get_ticker error={e}')
            raise

        timestamp = datetime.timestamp(
            dateutil.parser.parse(resp['time'])
        )
        price = resp['prices'][0]
        instrument = price['instrument']
        bid = float(price['bids']['0']['price'])
        ask = float(price['asks']['0']['price'])
        volume = self.get_candle_volume()
        return Ticker(instrument, timestamp, bid, ask, volume)

    def get_candle_volume(self, count=1,
                          granularity=constants.TRADE_MAP[settings.trade_duration]['granularity']):
        params = {
            'count': count,
            'granularity': granularity
        }
        req = instruments.InstrumentsCandles(instrument=settings.product_code,
                                             params=params)
        try:
            resp = self.client.request(req)
        except V20Error as e:
            logger.error(f'action=get_candle_volume error={e}')
            raise e

        return int(resp['candles'][0]['volume'])

    def get_realtime_ticker(self, callback):
        req = PricingStream(accountID=self.account_id, params={
            'instruments': settings.product_code
        })
        try:
            for resp in self.client.request(req):
                if resp['type'] == 'PRICE':
                    timestamp = datetime.timestamp(
                        dateutil.parser.parse(resp['time']))
                    instrument = resp['instrument']
                    bid = float(resp['bids'][0]['price'])
                    ask = float(resp['asks'][0]['price'])
                    volume = self.get_candle_volume()
                    ticker = Ticker(instrument, timestamp, bid, ask, volume)
                    callback(ticker)

        except V20Error as e:
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': u'oanda streaming stops',  # 通知内容
                'username': u'Market-Signal-Bot',  # ユーザー名
                'icon_emoji': u':smile_cat:',  # アイコン
                'link_names': 1,  # 名前をリンク化
            }))
            logger.error(f'action=get_realtime_ticker error={e}')
            raise

    def send_order(self, order: Order) -> Trade:
        if order.side == constants.BUY:
            units = order.units
        elif order.side == constants.SELL:
            units = -order.units
        order_data = {
            'order': {
                'type': order.order_type,
                'instrument': order.product_code,
                'units': units
            }
        }
        req = orders.OrderCreate(accountID=self.account_id, data=order_data)
        try:
            resp = self.client.request(req)
            logger.info(f'action=send_order resp={resp}')
        except V20Error as e:
            logger.error(f'action=send_order error={e}')
            raise
        order_id = resp['orderCreateTransaction']['id']
        order = self.wait_order_complete(order_id)
        if not order:
            logger.error('action=send_order error=timeout')
            raise OrderTimeoutError

        return self.trade_details(order.filling_transactionid)

    def wait_order_complete(self, order_id, timeout_count=5) -> Order:
        count = 0
        while True:
            order = self.get_order(order_id)
            if order.order_state == ORDER_FILLED:
                return order
            time.sleep(1)
            count += 1
            if count > timeout_count:
                return None

    def get_order(self, order_id) -> Order:
        req = orders.OrderDetails(accountID=self.account_id, orderID=order_id)
        try:
            resp = self.client.request(req)
            logger.info(f'action=get_order resp={resp}')
        except V20Error as e:
            logger.error(f'action=get_order error={e}')
            raise

        order = Order(
            product_code=resp['order']['instrument'],
            side=constants.BUY if float(resp['order']['units']) > 0 else constants.SELL,
            units=float(resp['order']['units']),
            order_type=resp['order']['type'],
            order_state=resp['order']['state'],
            filling_transaction_id=resp['order'].get('fillingTransactionID')
        )
        return order

    def trade_details(self, trade_id) -> Trade:
        req = trades.TradeDetails(self.account_id, trade_id)
        try:
            resp = self.client.request(req)
            logger.info(f'action=trade_details resp={resp}')
        except V20Error as e:
            logger.error(f'action=trade_details error={e}')
            raise

        trade = Trade(
            trade_id=trade_id,
            side=constants.BUY if float(resp['trade']['currentUnits']) > 0 else constants.SELL,
            units=float(resp['trade']['currentUnits']),
            price=float(resp['trade']['price'])
        )
        return trade

    def get_open_trade(self) -> list:
        req = trades.OpenTrades(self.account_id)
        try:
            resp = self.client.request(req)
            logger.info(f'action=get_open_trade resp={resp}')
        except V20Error as e:
            logger.error(f'action=get_open_trade error={e}')
            raise

        trades_list = []
        for trade in resp['trades']:
            trades_list.insert(0, Trade(
                trade_id=trade['id'],
                side=constants.BUY if float(trade['currentUnits']) > 0 else constants.SELL,
                units=float(trade['currentUnits']),
                price=float(trade['price'])
            ))
        return trades_list

    def trade_close(self, trade_id) -> Trade:
        req = trades.TradeClose(self.account_id, trade_id)
        try:
            resp = self.client.request(req)
            logger.info(f'action=trade_close resp={resp}')
        except V20Error as e:
            logger.error(f'action=trade_close error={e}')
            raise

        trade = Trade(
            trade_id=trade_id,
            side=constants.BUY if float(resp['orderFillTransaction']['units']) > 0 else constants.SELL,
            units=float(resp['orderFillTransaction']['units']),
            price=float(resp['orderFillTransaction']['price'])
        )
        return trade

    def send_stop_loss(self, order: Order) -> Trade:
        if order.side == constants.BUY:
            units = order.units
        elif order.side == constants.SELL:
            units = -order.units
        order_data = {
            'order': {
                'type': order.order_type,
                'instrument': order.product_code,
                'units': units,
                'price': order.price
            }
        }
        req = orders.OrderCreate(accountID=self.account_id, data=order_data)
        try:
            resp = self.client.request(req)
            logger.info(f'action=send_order resp={resp}')
        except V20Error as e:
            logger.error(f'action=send_order error={e}')
            raise ValueError
        order_id = resp['orderCreateTransaction']['id']
        price = order.price
        units = order.units
        side = order.side
        trade = Trade(trade_id=order_id, side=side, price=price, units=units)

        return trade

    def cancel_stop_loss(self, product_code, order_id):
        req = orders.OrderCancel(accountID=self.account_id, orderID=order_id)
        try:
            resp = self.client.request(req)
            logger.info(f'action=send_order resp={resp}')
            return True
        except V20Error as e:
            logger.error(f'action=send_order error={e}')
            return False

