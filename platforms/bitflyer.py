from datetime import datetime
import json
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
import settings

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
        requests.post(settings.WEB_HOOK_URL, data=json.dumps({
            'text': u'bitflyer websocket closed',  # 通知内容
            'username': u'Market-Signal-Bot',  # ユーザー名
            'icon_emoji': u':smile_cat:',  # アイコン
            'link_names': 1,  # 名前をリンク化
        }))
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
        require_collateral = resp['response']['require_collateral']
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
            while True:
                if not req.run():
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': u'bitflyer websocket is temporarily closed',  # 通知内容
                    }))
                    time.sleep(1)
        except WebSocketProtocolException:
            time.sleep(1)
            count += 1
            req.run()
            if count > 60:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': u'bitflyer websocket closed',  # 通知内容
                }))
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
            return Order("", "", 0)
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

    def send_stop_loss(self, order: Order) -> Trade:
        path = '/v1/me/sendparentorder'
        resp = self.private.base_post(path=path, parameters=[{
            "product_code": order.product_code, "condition_type": order.order_type, "side": order.side,
            "trigger_price": order.price, "size": order.units}])
        if resp['status_code'] >= 400:
            logger.error(f'action=send_stop error={resp["response"]["error_message"]}')
            raise ValueError
        else:
            logger.info(f'action=send_stop resp={resp["response"]}')

        order_id = resp['response']['parent_order_acceptance_id']
        side = order.side
        price = order.price
        units = order.units
        trade = Trade(trade_id=order_id, side=side, price=price, units=units)

        return trade

    def cancel_stop_loss(self, product_code, order_id):
        path = '/v1/me/cancelparentorder'
        resp = self.private.base_post(path=path, product_code=product_code, parent_order_acceptance_id=order_id)
        if resp['status_code'] >= 400:
            logger.error(f'action=cancel_stop_loss error={resp["response"]["error_message"]}')
            return False
        else:
            logger.info('action=cancel_stop_loss')
            return True
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
