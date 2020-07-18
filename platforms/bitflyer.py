from datetime import datetime
import simplejson as json
import logging
import requests
import time

import dateutil.parser
from bitflyer import private
from bitflyer import public
import websocket
from websocket import WebSocketProtocolException

import constants
from platforms import Balance
from platforms import Ticker
from platforms import Order
from platforms import OrderTimeoutError
from platforms import Trade

ORDER_FILLED = 'COMPLETED'

logger = logging.getLogger(__name__)

base_url = "https://api.bitflyer.jp/v1/"


class RealtimeAPI(object):

    def __init__(self, url, channel, callback):
        self.url = url
        self.channel = channel
        self.callback = callback

        # Define Websocket
        self.ws = websocket.WebSocketApp(self.url,header=None,on_open=self.on_open,
                                         on_message=self.on_message, on_error=self.on_error, on_close=self.on_close)
        websocket.enableTrace(True)

    def run(self):
        # ws has loop. To break this press ctrl + c to occur Keyboard Interruption Exception.
        self.ws.run_forever()
        logger.info('Web Socket process ended.')

    """
    Below are callback functions of websocket.
    """
    # when we get message
    def on_message(self, ws, message):
        output = json.loads(message)['params']
        logger.info(output)
        timestamp = datetime.timestamp(dateutil.parser.parse(output['message']['timestamp']))
        instrument = output['message']['product_code']
        bid = float(output['message']['best_bid'])
        ask = float(output['message']['best_ask'])
        volume = float(output['message']['volume'])
        ticker = Ticker(instrument, timestamp, bid, ask, volume)
        self.callback(ticker)

    # when error occurs
    def on_error(self, ws, error):
        logger.error(f'on_error={error}')

    # when websocket closed.
    def on_close(self, ws):
        logger.info('disconnected streaming server')

    # when websocket opened.
    def on_open(self, ws):
        logger.info('connected streaming server')
        output_json = json.dumps(
            {'method': 'subscribe',
             'params': {'channel': self.channel}
            }
        )
        ws.send(output_json)


class APIClient(object):
    def __init__(self, access_key, secret_key):
        self.access_key = access_key
        self.secret_key = secret_key
        self.public = public.Public()
        self.private = private.Private(access_key, secret_key)

    def get_balance(self) -> Balance:
        resp = self.private.getcollateral()
        if resp["status_code"] >= 400:
            logger.error(f'action=get_balance error={resp["response"]["error_message"]}')
            raise

        available = resp['response']['collateral']
        currency = "JPY"
        return Balance(currency, available)

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
        req = base_url + "getticker?product_code=" + product_code
        resp = json.loads(requests.get(req).text)
        if "error_message" in resp.keys():
            logger.error(f'action=get_ticker error={resp["error_message"]}')
            raise ValueError

        timestamp = datetime.timestamp(
            dateutil.parser.parse(resp['timestamp'])
        )
        instrument = resp['product_code']
        bid = float(resp['best_bid'])
        ask = float(resp['best_ask'])
        volume = float(resp['volume'])
        return Ticker(instrument, timestamp, bid, ask, volume)

    # def get_candle_volume(self, count=1,
    #                       granularity=constants.TRADE_MAP[settings.trade_duration]['granularity']):
    #     params = {
    #         'count': count,
    #         'granularity': granularity
    #     }
    #     req = instruments.InstrumentsCandles(instrument=settings.product_code,
    #                                          params=params)
    #     try:
    #         resp = self.client.request(req)
    #     except V20Error as e:
    #         logger.error(f'action=get_candle_volume error={e}')
    #         raise
    #
    #     return int(resp['candles'][0]['volume'])

    def get_realtime_ticker(self, callback, product_code=constants.PRODUCT_CODE_FX_BTC_JPY):
        url = 'wss://ws.lightstream.bitflyer.com/json-rpc'
        channel = 'lightning_ticker_' + product_code
        req = RealtimeAPI(url, channel, callback)
        count = 0
        try:
            req.run()
        except WebSocketProtocolException:
            time.sleep(1)
            count += 1
            req.run()
            if count > 60:
                raise WebSocketProtocolException

    def send_order(self, order: Order) -> Trade:
        resp = self.private.sendchildorder(product_code=order.product_code,
                                           child_order_type=order.order_type, side=order.side, size=order.units)
        if resp['status_code'] >= 400:
            logger.error(f'action=send_order error={resp["response"]["error_message"]}')
            raise ValueError
        else:
            logger.info(f'action=send_order resp={resp["response"]}')

        order_id = resp['response']['child_order_acceptance_id']
        order = self.wait_order_complete(order_id)
        if not order:
            logger.error('action=send_order error=timeout')
            raise OrderTimeoutError

        return self.trade_details(order.product_code, order_id)

    def wait_order_complete(self, order_id, timeout_count=5) -> Order:
        count = 0
        while True:
            time.sleep(1)
            order = self.get_order(order_id)
            if order.order_state == ORDER_FILLED:
                return order
            count += 1
            if count > timeout_count:
                return None

    def get_order(self, order_id) -> Order:
        path = '/v1/me/getchildorders' + "?product_code=FX_BTC_JPY&child_order_acceptance_id=" + order_id
        resp = self.private.base_get(path=path)
        if resp["status_code"] >= 400 or resp["response"] == []:
            logger.error(f'action=get_order error={resp}')
            return None
        else:
            response = resp["response"][0]
            logger.info(f'action=get_order resp={response}')

        order = Order(
            product_code=response['product_code'],
            side=response['side'],
            units=float(response['size']),
            order_type=response['child_order_type'],
            order_state=response['child_order_state']
        )
        return order

    def trade_details(self, product_code, order_id) -> Trade:
        path = '/v1/me/getexecutions' + '?product_code=' + product_code + '&child_order_acceptance_id=' + order_id
        resp = self.private.base_get(path=path)
        if resp["status_code"] >= 400 or resp["response"] == []:
            logger.error(f'action=trade_details error')
            raise
        else:
            response = resp["response"][0]
            logger.info(f'action=trade_details resp={response}')

        trade = Trade(
            trade_id=response['id'],
            side=response['side'],
            units=float(response['size']),
            price=float(response['price'])
        )
        return trade

    def get_open_trade(self, product_code=constants.PRODUCT_CODE_FX_BTC_JPY) -> list:
        path = '/v1/me/getpositions' + '?product_code=' + product_code
        resp = self.private.base_get(path=path)
        if resp["status_code"] >= 400:
            logger.error(f'action=get_open_trade error={resp["response"]["error_message"]}')
            return None
        else:
            response = resp["response"]
            logger.info(f'action=get_open_trade resp={response}')

        trades_list = []
        for i, trade in enumerate(response):
            trades_list.insert(0, Trade(
                trade_id=i,
                side=trade["side"],
                units=float(trade['size']),
                price=float(trade['price'])
            ))
        return trades_list

    #
    # def trade_close(self, trade_id) -> Trade:
    #     req = trades.TradeClose(self.account_id, trade_id)
    #     try:
    #         resp = self.client.request(req)
    #         logger.info(f'action=trade_close resp={resp}')
    #     except V20Error as e:
    #         logger.error(f'action=trade_close error={e}')
    #         raise
    #
    #     trade = Trade(
    #         trade_id=trade_id,
    #         side=constants.BUY if float(resp['orderFillTransaction']['units']) > 0 else constants.SELL,
    #         units=float(resp['orderFillTransaction']['units']),
    #         price=float(resp['orderFillTransaction']['price'])
    #     )
    #     return trade