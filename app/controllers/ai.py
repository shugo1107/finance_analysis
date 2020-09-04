from collections import defaultdict
import datetime
import json
import logging
import math
import requests
import time

import numpy as np
import talib

from app.models.candle import factory_candle_class
from app.models.dfcandle import DataFrameCandle
from app.models.events import SignalEvents
from platforms import OandaClient
from platforms import BitflyerClient
from platforms import Order
from platforms import Position
from tradingalgo.algo import ichimoku_cloud

import constants
import settings

logger = logging.getLogger(__name__)


def duration_seconds(duration: str) -> int:
    if duration == constants.DURATION_5S:
        return 5
    if duration == constants.DURATION_1M:
        return 60
    if duration == constants.DURATION_5M:
        return 300
    if duration == constants.DURATION_15M:
        return 900
    if duration == constants.DURATION_30M:
        return 1800
    if duration == constants.DURATION_1H:
        return 60 * 60
    if duration == constants.DURATION_1D:
        return 60 * 60 * 24
    else:
        return 0


class AI(object):

    def __init__(self, product_code, use_percent, duration, past_period,
                 stop_limit_percent, back_test, live_practice, client="oanda"):
        if client.lower() == "oanda":
            self.API = OandaClient(settings.oanda_access_token, settings.oanda_account_id, environment=live_practice)
            self.leverage = 25
            self.product_codes = constants.TRADABLE_PAIR
            self.signals = {constants.PRODUCT_CODE_USD_JPY: 0, constants.PRODUCT_CODE_EUR_JPY: 0,
                            constants.PRODUCT_CODE_EUR_USD: 0, constants.PRODUCT_CODE_GBP_USD: 0}
            self.position = {constants.PRODUCT_CODE_USD_JPY: {"ATR": [], "EMA": [], "ADX": []},
                             constants.PRODUCT_CODE_EUR_JPY: {"ATR": [], "EMA": [], "ADX": []},
                             constants.PRODUCT_CODE_EUR_USD: {"ATR": [], "EMA": [], "ADX": []},
                             constants.PRODUCT_CODE_GBP_USD: {"ATR": [], "EMA": [], "ADX": []}}
        elif client.lower() == "bitflyer":
            self.API = BitflyerClient(settings.bitflyer_access_key, settings.bitflyer_secret_key)
            self.leverage = 4
            self.position = {constants.PRODUCT_CODE_FX_BTC_JPY: {"ATR": [], "EMA": [], "ADX": []}}

        if back_test:
            self.signal_events = SignalEvents()
        else:
            self.signal_events = SignalEvents.get_signal_events_by_count(1)

        self.product_code = product_code
        self.use_percent = use_percent
        self.duration = duration
        self.past_period = past_period
        self.optimized_trade_params = dict()
        self.params = {'ema_period_1': 5, 'ema_period_2': 25, 'ema_period_3': 50, 'adx_n': 14,
                       'atr_n': 14, 'atr_k_1': 2.0, 'atr_k_2': 0.3}
        # self.stop_limit = 0
        # self.atr_buy_stop_limit = 0
        # self.atr_sell_stop_limit = 1000000000
        self.stop_limit_percent = stop_limit_percent
        self.back_test = back_test
        self.start_trade = datetime.datetime.utcnow()
        self.candle_cls = factory_candle_class(self.product_code, self.duration)
        # self.update_optimize_params(False, self.product_code)
        # self.in_atr_trade = False
        # self.atr_trade = None
        self.client = client
        self.trade_list = []
        self.balance = self.API.get_balance()
        # self.position = self.get_current_position()
        self.position_list = []
        self.tradable_products = constants.TRADABLE_PAIR
        self.default_trail_offset = {constants.PRODUCT_CODE_USD_JPY: 0.20,
                                     constants.PRODUCT_CODE_EUR_JPY: 0.20,
                                     constants.PRODUCT_CODE_EUR_USD: 0.0020,
                                     constants.PRODUCT_CODE_GBP_USD: 0.0020,
                                     constants.PRODUCT_CODE_FX_BTC_JPY: 3000}
    #
    # def update_optimize_params(self, is_continue: bool, product_code=None):
    #     if product_code is None:
    #         product_code = self.product_code
    #     if product_code not in self.optimized_trade_params.keys():
    #         self.optimized_trade_params[product_code] = None
    #     logger.info('action=update_optimize_params status=run')
    #     df = DataFrameCandle(product_code, self.duration)
    #     df.set_all_candles(self.past_period)
    #     if df.candles:
    #         self.optimized_trade_params[product_code] = df.optimize_params()
    #     if self.optimized_trade_params[product_code] is not None:
    #         logger.info(f'action=update_optimize_params params={self.optimized_trade_params[
    #             product_code].__dict__}, product_code={product_code}')
    #         requests.post(settings.WEB_HOOK_URL, data=json.dumps({
    #             'text': f"optimized_params={self.optimized_trade_params[
    #                 product_code].__dict__}, product_code={product_code}",
    #         }))
    #
    #     if is_continue and self.optimized_trade_params is None:
    #         time.sleep(10 * duration_seconds(self.duration))
    #         self.update_optimize_params(is_continue)

    def reset_position_list(self):
        for product_code in self.product_codes:
            self.position[product_code] = {"ATR": [], "EMA": [], "ADX": []}

    def get_current_position(self):
        # if product_code is None:
        #     product_code = self.product_code
        self.balance = self.API.get_balance()
        self.trade_list = self.API.get_open_trade()
        self.reset_position_list()
        trade_id_list = []
        for trade in self.trade_list:
            trade_id_list.append(int(trade.trade_id))
        logger.info(trade_id_list)

        position_list = []

        for position in self.position_list:
            logger.info(position.trade_id)
            if int(position.trade_id) in trade_id_list:
                position_list.append(position)

        self.position_list = position_list
        if len(self.position_list) != len(self.trade_list):
            logger.warning(f'position_list: {self.position_list}, trade_list: {self.trade_list}')
            logger.warning('position list is not complete')
        for position in self.position_list:
            self.position[position.product_code][position.trade_signal].append(position)

        for product_code in self.product_codes:
            for signal in ['ADX', 'ATR', 'EMA']:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'product_code={product_code}, signal={signal}, has_position={bool(self.position[product_code][signal])}',  # 通知内容
                }))
        # buy_unit = 0
        # sell_unit = 0
        # for i in range(len(self.trade_list)):
        #     if self.trade_list[i].side == constants.BUY:
        #         buy_unit += abs(self.trade_list[i].units)
        #     elif self.trade_list[i].side == constants.SELL:
        #         sell_unit += abs(self.trade_list[i].units)
        # units = abs(buy_unit - sell_unit)
        # if product_code == constants.PRODUCT_CODE_FX_BTC_JPY:
        #     units = math.ceil(units * 10000) / 10000
        # else:
        #     units = math.ceil(units)
        # if buy_unit >= sell_unit:
        #     position = Position(product_code=product_code, side=constants.BUY, leverage=self.leverage,
        #                         units=units, require_collateral=self.balance.require_collateral)
        # else:
        #     position = Position(product_code=product_code, side=constants.SELL, leverage=self.leverage,
        #                         units=units, require_collateral=self.balance.require_collateral)
        # requests.post(settings.WEB_HOOK_URL, data=json.dumps({
        #     'text': f"current position product code: {position.product_code}, units: {position.units}, side: {position.side}",  # 通知内容
        # }))
        #
        # return position

    def can_buy(self, candle, units, product_code=None):
        if product_code is None:
            product_code = self.product_code
        if product_code not in constants.TRADABLE_PAIR:
            logger.warning('action=can_buy status=false error=not_tradable_product')
            return False
        if self.start_trade > candle.time:
            logger.warning('action=can_buy status=false error=old_time')
            return False
        # if self.in_atr_trade:
        #     logger.warning('action=can_buy status=false error=in_ATR_trade')
        #     return False
        # if self.position.side == constants.SELL:
        #     return True
        elif float(self.balance.available) * 0.8 <\
                units * candle.close / self.leverage + float(self.balance.require_collateral):
            logger.warning('action=can_buy status=false error=too much position')
            return False
        else:
            logger.warning('action=can_buy status=true')
            return True

    def can_sell(self, candle, units, product_code=None):
        if product_code is None:
            product_code = self.product_code
        if product_code not in constants.TRADABLE_PAIR:
            logger.warning('action=can_sell status=false error=not_tradable_product')
        if self.start_trade > candle.time:
            logger.warning('action=can_sell status=false error=old_time')
            return False
        # if self.in_atr_trade:
        #     logger.warning('action=can_sell status=false error=in_ATR_trade')
        #     return False
        # if self.position.side == constants.BUY:
        #     return True
        elif float(self.balance.available) * 0.8 < \
                units * candle.close / self.leverage + float(self.balance.require_collateral):
            logger.warning('action=can_sell status=false error=too much position')
            return False
        # elif self.position.units < units * 0.8:
        #     return True
        else:
            logger.warning('action=can_sell status=true')
            return True

    def buy(self, candle, units, back_test=False, product_code=None):
        logger.info('action=buy status=run')
        if product_code is None:
            product_code = self.product_code
        close_trade = False
        if back_test or self.back_test:
            logger.info('action=buy status=back_test')
            could_buy, close_trade = self.signal_events.buy(
                product_code, candle.time, candle.close, 1.0, save=False)
            return could_buy, close_trade

        if self.start_trade > candle.time:
            logger.warning('action=buy status=false error=old_time')
            return False, close_trade

        if not self.can_buy(candle, units, product_code):
            logger.warning('action=buy status=false error=cannot buy')
            return False, close_trade

        sum_price = 0
        closed_units = 0
        for trade in self.trade_list:
            if trade.side == constants.SELL:
                close_trade = True
                if self.client == "oanda":
                    closed_trade = self.API.trade_close(trade.trade_id)
                    sum_price += closed_trade.price * abs(closed_trade.units)
                    closed_units += abs(closed_trade.units)
                elif self.client == 'bitflyer':
                    closed_units += trade.units

        if self.client == 'bitflyer':
            closed_units = round(closed_units, 4)
            close_order = Order(product_code, constants.BUY, closed_units)
            close_trade = self.API.send_order(close_order)
            self.signal_events.buy(product_code, candle.time, close_trade, closed_units, save=True)
            sum_price = close_trade.price * closed_units
            new_units = round(units - closed_units, 4)
        else:
            new_units = round(units - closed_units)

        order = Order(product_code, constants.BUY, new_units)
        logger.info(f'action=buy order={order.__dict__}')
        trade = self.API.send_order(order)
        self.signal_events.buy(product_code, candle.time,
                               (trade.price * (units - closed_units) + sum_price) / units, units, save=True)
        return True, close_trade

    def sell(self, candle, units, back_test=False, product_code=None):
        logger.info('action=sell status=run')
        if product_code is None:
            product_code = self.product_code
        close_trade = False
        if back_test or self.back_test:
            logger.info('action=sell status=back_test')
            could_sell, close_trade = self.signal_events.sell(
                product_code, candle.time, candle.close, 1.0, save=False)
            return could_sell, close_trade

        if self.start_trade > candle.time:
            logger.warning('action=sell status=false error=old_time')
            return False, close_trade

        if not self.can_sell(candle, units, product_code):
            logger.warning('action=sell status=false error=cannot sell')
            return False, close_trade

        sum_price = 0
        closed_units = 0
        for trade in self.trade_list:
            if trade.side == constants.BUY:
                close_trade = True
                if self.client == "oanda":
                    closed_trade = self.API.trade_close(trade.trade_id)
                    sum_price += closed_trade.price * abs(closed_trade.units)
                    closed_units += abs(closed_trade.units)
                elif self.client == 'bitflyer':
                    closed_units += trade.units

        if self.client == 'bitflyer':
            closed_units = round(closed_units, 4)
            close_order = Order(product_code, constants.SELL, closed_units)
            close_trade = self.API.send_order(close_order)
            self.signal_events.sell(product_code, candle.time, close_trade, closed_units, save=True)
            sum_price = close_trade.price * closed_units
            new_units = round(units - closed_units, 4)

        else:
            new_units = round(units - closed_units)

        order = Order(product_code, constants.SELL, new_units)
        logger.info(f'action=sell order={order.__dict__}')
        trade = self.API.send_order(order)
        self.signal_events.sell(product_code, candle.time,
                                (trade.price * (units - closed_units) + sum_price) / units, units, save=True)
        return True, close_trade

    def trail_buy(self, candle, units, product_code=None, trade_signal=None, fx_adjustment=1, stop_loss=None,
                  trail_offset=None, back_test=False):
        logger.info('action=trail_buy status=run')
        if product_code is None:
            product_code = self.product_code

        if trail_offset is None:
            trail_offset = self.default_trail_offset[product_code]

        if back_test or self.back_test:
            logger.info('action=trail_buy status=back_test')
            could_buy, close_trade = self.signal_events.buy(
                product_code, candle.time, candle.close, 1.0, save=False)
            return could_buy

        if self.start_trade > candle.time:
            logger.warning('action=trail_buy status=false error=old_time')
            return False

        if not self.can_buy(candle, units, product_code):
            logger.warning('action=trail_buy status=false error=cannot buy')
            return False

        if self.position[product_code][trade_signal]:
            logger.info('action=trail_buy status=false error=already_has_the_same_position')
            return False

        order = Order(product_code, constants.BUY, units, price=trail_offset, order_type='TRAIL')
        logger.info(f'action=trail_buy order={order.__dict__}')
        trade = self.API.send_trail_stop(order)
        if not trade:
            return False
        require_collateral = self.leverage * units * float(trade.price) * fx_adjustment
        position = Position(product_code=product_code, side=trade.side, units=trade.units,
                            require_collateral=require_collateral, trade_id=trade.trade_id, trade_signal=trade_signal,
                            stop_loss=stop_loss)
        self.balance.require_collateral += require_collateral
        logger.info(f'position={position.__dict__}')
        self.position_list.append(position)
        logger.info(f'position_list={self.position_list}')
        self.position[product_code][trade_signal].append(position)
        logger.info(f'position={self.position}')
        logger.info(f'position[{product_code}][{trade_signal}]={self.position[product_code][trade_signal]}')
        # self.signal_events.buy(product_code, candle.time, trade.price, units, save=True)
        return True

    def trail_sell(self, candle, units, trade_signal=None, fx_adjustment=1, stop_loss=None,
                   trail_offset=None, back_test=False, product_code=None):
        logger.info('action=trail_sell status=run')
        if product_code is None:
            product_code = self.product_code
        if trail_offset is None:
            trail_offset = self.default_trail_offset[product_code]
        if back_test or self.back_test:
            logger.info('action=trail_sell status=back_test')
            could_sell, close_trade = self.signal_events.sell(
                product_code, candle.time, candle.close, 1.0, save=False)
            return could_sell

        if self.start_trade > candle.time:
            logger.warning('action=trail_sell status=false error=old_time')
            return False

        if not self.can_sell(candle, units, product_code):
            logger.warning('action=trail_sell status=false error=cannot buy')
            return False

        if self.position[product_code][trade_signal]:
            logger.info('action=trail_sell status=false error=already_has_the_same_position')
            return False

        order = Order(product_code, constants.SELL, units, price=trail_offset, order_type='TRAIL')
        logger.info(f'action=trail_sell order={order.__dict__}')
        trade = self.API.send_trail_stop(order)
        if not trade:
            return False
        require_collateral = self.leverage * units * float(trade.price) * fx_adjustment
        position = Position(product_code=product_code, side=trade.side, units=trade.units,
                            require_collateral=require_collateral, trade_id=trade.trade_id, trade_signal=trade_signal,
                            stop_loss=stop_loss)
        self.balance.require_collateral += require_collateral
        logger.info(f'position={position.__dict__}')
        self.position_list.append(position)
        logger.info(f'position_list={self.position_list}')
        self.position[product_code][trade_signal].append(position)
        logger.info(f'position={self.position}')
        logger.info(f'position[{product_code}][{trade_signal}]={self.position[product_code][trade_signal]}')
        # self.signal_events.sell(product_code, candle.time, trade.price, units, save=True)
        return True

    def send_stop_loss(self, units, side, price, product_code=None):
        if product_code is None:
            product_code = self.product_code
        order = Order(product_code, side, units, order_type="STOP", price=price)
        trade = self.API.send_stop_loss(order)
        return trade

    def cancel_stop_loss(self, product_code, order_id):
        if not self.API.cancel_stop_loss(product_code, order_id):
            logger.error("action=cancel_stop_loss error=can't send a cancel order")
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': "Can't send a cancel order! Hurry to check it!",  # 通知内容
            }))
            return False
        return True

    def trade(self):
        # if product_code is None:
        #     product_code = self.product_code
        logger.info('action=trade status=run')
        # self.alert_signal(product_code)
        cnt = 0
        while True:
            if cnt % 180 == 0:
                self.get_current_position()
                cnt = 0
                logger.info('action=trade status=run')
            # logger.info(f"position units: {self.position.units}")
            # if self.in_atr_trade and self.position.units <= 0.01:
            #     self.in_atr_trade = False
            #     self.atr_trade = None
            #     self.atr_buy_stop_limit = 0
            #     self.atr_sell_stop_limit = 1000000000
            #     self.update_optimize_params(is_continue=True, product_code=product_code)
            # if product_code not in self.optimized_trade_params.keys():
            #     self.optimized_trade_params[product_code] = None
            # params = self.optimized_trade_params[product_code]
            # if params is None:
            #     self.update_optimize_params(False, product_code)
            #     return

            fx_adjustments = defaultdict(float)
            indicators = defaultdict(dict)

            # 各indicatorを計算し、signalの数を記録
            for product_code in self.product_codes:
                if product_code[-3:] == "JPY":
                    fx_adjustment = 1
                elif product_code[-3:] == "USD":
                    usd_jpy = DataFrameCandle("USD_JPY", self.duration)
                    usd_jpy.set_recent_candles(1)
                    fx_adjustment = usd_jpy.candles[-1].close
                elif product_code[-3:] == "EUR":
                    eur_jpy = DataFrameCandle("EUR_JPY", self.duration)
                    eur_jpy.set_recent_candles(1)
                    fx_adjustment = eur_jpy.candles[-1].close
                else:
                    fx_adjustment = 1
                fx_adjustments[product_code] = fx_adjustment

                df = DataFrameCandle(product_code, self.duration)
                df.set_recent_candles(self.past_period)

                ema_values_1 = talib.EMA(np.array(df.closes), self.params['ema_period_1'])
                ema_values_2 = talib.EMA(np.array(df.closes), self.params['ema_period_2'])
                ema_values_3 = talib.EMA(np.array(df.closes), self.params['ema_period_3'])

                di_plus = talib.PLUS_DI(np.array(df.highs), np.array(df.lows),
                                        np.array(df.closes), self.params['adx_n'])
                di_minus = talib.MINUS_DI(np.array(df.highs), np.array(df.lows),
                                          np.array(df.closes), self.params['adx_n'])
                adx = talib.ADX(np.array(df.highs), np.array(df.lows),
                                np.array(df.closes), self.params['adx_n'])
                adxr = talib.ADXR(np.array(df.highs), np.array(df.lows),
                                  np.array(df.closes), self.params['adx_n'])
                atr = talib.ATR(np.array(df.highs), np.array(df.lows),
                                np.array(df.closes), self.params['atr_n'])
                mid_list = talib.EMA(np.array(df.closes), self.params['atr_n'])
                atr_up = (mid_list + atr * self.params['atr_k_1']).tolist()
                atr_down = (mid_list - atr * self.params['atr_k_1']).tolist()
                atr_up_2 = (mid_list + atr * self.params['atr_k_2']).tolist()
                atr_down_2 = (mid_list - atr * self.params['atr_k_2']).tolist()
                indicator = {'df': df.candles[-2:], 'ema_values_1': ema_values_1[-2:], 'ema_values_2': ema_values_2[-2:],
                             'ema_values_3': ema_values_3[-2:], 'di_plus': di_plus[-4:], 'di_minus': di_minus[-4:],
                             'adx': adx[-4:], 'adxr': adxr[-4:], 'atr_up': atr_up[-2:], 'atr_down': atr_down[-2:],
                             'atr_up_2': atr_up_2[-2:], 'atr_down_2': atr_down_2[-2:]}
                indicators[product_code] = indicator
                # self.signals[product_code] = self.count_signals(indicator)

            for product_code in self.product_codes:
                fx_adjustment = fx_adjustments[product_code]
                self.ema_trade(indicators[product_code], product_code, fx_adjustment)
                self.atr_trade(indicators[product_code], product_code, fx_adjustment)
                self.adx_trade(indicators[product_code], product_code, fx_adjustment)

            cnt += 1
            time.sleep(5)

            # if params.ema_enable:
            #     ema_values_1 = talib.EMA(np.array(df.closes), params.ema_period_1)
            #     ema_values_2 = talib.EMA(np.array(df.closes), params.ema_period_2)
            #
            # if params.bb_enable:
            #     bb_up, _, bb_down = talib.BBANDS(np.array(df.closes), params.bb_n, params.bb_k, params.bb_k, 0)
            #
            # atr = talib.ATR(
            #     np.array(df.highs), np.array(df.lows),
            #     np.array(df.closes), params.atr_n)
            # mid_list = talib.EMA(np.array(df.closes), params.atr_n)
            # atr_up = (mid_list + atr * params.atr_k_1).tolist()
            # atr_down = (mid_list - atr * params.atr_k_1).tolist()
            # atr_up_2 = (mid_list + atr * params.atr_k_2).tolist()
            # atr_down_2 = (mid_list - atr * params.atr_k_2).tolist()
            # # mid_atr = math.floor((atr_up[-1] + atr_down[-1]) / 2 / constants.MIN_TRADE_PRICE_MAP[product_code])\
            # #           * constants.MIN_TRADE_PRICE_MAP[product_code]
            # if atr_down_2[-1] < self.atr_sell_stop_limit:
            #     self.atr_sell_stop_limit = math.floor(atr_down_2[-1] / constants.MIN_TRADE_PRICE_MAP[product_code])\
            #                                * constants.MIN_TRADE_PRICE_MAP[product_code]
            #     if self.in_atr_trade and self.atr_trade.side == constants.BUY:
            #         if self.cancel_stop_loss(product_code, self.atr_trade.trade_id):
            #             trade = self.send_stop_loss(
            #                 self.position.units, self.atr_trade.side, self.atr_sell_stop_limit, product_code)
            #             self.atr_trade = trade
            #             logger.info('stop loss is updated!')
            # if atr_up_2[-1] > self.atr_buy_stop_limit:
            #     self.atr_buy_stop_limit = math.floor(atr_up_2[-1] / constants.MIN_TRADE_PRICE_MAP[product_code])\
            #                               * constants.MIN_TRADE_PRICE_MAP[product_code]
            #     if self.in_atr_trade and self.atr_trade.side == constants.SELL:
            #         if self.cancel_stop_loss(product_code, self.atr_trade.trade_id):
            #             trade = self.send_stop_loss(
            #                 self.position.units, self.atr_trade.side, self.atr_buy_stop_limit, product_code)
            #             self.atr_trade = trade
            #             logger.info('stop loss is updated!')
            # logger.info(f'sell _stop: {self.atr_sell_stop_limit}, buy_stop: {self.atr_buy_stop_limit}')
            # if self.atr_trade is not None:
            #     logger.info(f"in atr: {self.in_atr_trade}, atr trade side: {self.atr_trade.side}")
            # else:
            #     logger.info("atr trade is None!")
            #
            # if params.ichimoku_enable:
            #     tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku_cloud(df.closes)
            #
            # if params.rsi_enable:
            #     rsi_values = talib.RSI(np.array(df.closes), params.rsi_period)
            #
            # if params.macd_enable:
            #     macd, macd_signal, _ = talib.MACD(
            #         np.array(df.closes), params.macd_fast_period, params.macd_slow_period, params.macd_signal_period)
            #
            # atr_buy_point, atr_sell_point = 0, 0
            #
            #
            # logger.info(f"atr_buy_point: {atr_buy_point}, atr_sell_point; {atr_sell_point}")
            # if atr_buy_point > 0:
            #     if product_code == constants.PRODUCT_CODE_FX_BTC_JPY:
            #         can_buy_units = math.floor(
            #             float(self.balance.available) * self.leverage * 0.8 / df.candles[-1].close * 10000) / 10000
            #         want_to_buy_units = math.floor(
            #             float(self.balance.available) * (1 - self.stop_limit_percent) / (
            #                         df.candles[-1].close - atr_up_2[-1]) * 10000) / 10000
            #     else:
            #         can_buy_units = math.floor(
            #             float(self.balance.available) * self.leverage * 0.8 / (df.candles[-1].close * fx_adjustment))
            #         want_to_buy_units = math.floor(
            #             float(self.balance.available) * (1 - self.stop_limit_percent) / ((df.candles[-1].close - atr_up_2[-1]) * fx_adjustment))
            #
            #     if self.position.side == constants.BUY:
            #         current_units = self.position.units
            #     else:
            #         current_units = -self.position.units
            #     max_units = min(want_to_buy_units, can_buy_units)
            #     units = max_units - current_units
            #     if units < 0:
            #         units = 0
            #     logger.info("ATR breaks up")
            #     if units < constants.MIN_TRADE_SIZE_MAP[product_code]:
            #         logger.info(f"action=atr_buy error=units is too little units={units}, max units={max_units}, current units={current_units}")
            #     else:
            #         logger.info(f"ATR trade units: {units}, max units: {max_units}, current units: {current_units}")
            #         requests.post(settings.WEB_HOOK_URL, data=json.dumps({
            #             'text': f"ATR trade units: {units}, max units: {max_units}, current units: {current_units}",  # 通知内容
            #         }))
            #         could_buy, _ = self.buy(df.candles[-1], units, product_code=product_code)
            #
            #         if could_buy:
            #             self.in_atr_trade = True
            #             self.atr_buy_stop_limit = math.floor(
            #                 atr_up_2[-1] / constants.MIN_TRADE_PRICE_MAP[product_code])\
            #                                       * constants.MIN_TRADE_PRICE_MAP[product_code]
            #             logger.info(f'stop limit={self.atr_buy_stop_limit}')
            #
            #             self.atr_trade = self.send_stop_loss(max_units, constants.SELL, self.atr_buy_stop_limit, product_code)
            #             requests.post(settings.WEB_HOOK_URL, data=json.dumps({
            #                 'text': f"stop loss units: {max_units}, side: {constants.SELL}, price: {self.atr_buy_stop_limit}",
            #                 # 通知内容
            #             }))
            #
            # if atr_sell_point > 0:
            #     if product_code == constants.PRODUCT_CODE_FX_BTC_JPY:
            #         can_sell_units = math.floor(
            #             float(self.balance.available) * self.leverage * 0.8 / df.candles[-1].close * 10000) / 10000
            #     else:
            #         can_sell_units = math.floor(
            #             float(self.balance.available) * self.leverage * 0.8 / (df.candles[-1].close * fx_adjustment))
            #
            #     if self.position.side == constants.SELL:
            #         current_units = self.position.units
            #     else:
            #         current_units = -self.position.units
            #     if product_code == constants.PRODUCT_CODE_FX_BTC_JPY:
            #         want_to_sell_units = math.floor(
            #             float(self.balance.available) * (1 - self.stop_limit_percent) / (atr_down_2[-1] - df.candles[-1].close) * 10000) / 10000
            #     else:
            #         want_to_sell_units = math.floor(
            #             float(self.balance.available) * (1 - self.stop_limit_percent) / ((atr_down_2[-1] - df.candles[-1].close) * fx_adjustment))
            #     max_units = min(want_to_sell_units, can_sell_units)
            #     units = max_units - current_units
            #     if units < 0:
            #         units = 0
            #     logger.info("ATR breaks down")
            #     if units < constants.MIN_TRADE_SIZE_MAP[product_code]:
            #         logger.info(f"action=atr_buy error=units is too little units={units}, max units={max_units}, current units={current_units}")
            #     else:
            #         logger.info(f"ATR trade units: {units}, max units: {max_units}, current units: {current_units}")
            #         requests.post(settings.WEB_HOOK_URL, data=json.dumps({
            #             'text': f"ATR trade units: {units}, max units: {max_units}, current units: {current_units}, product code: {product_code}",  # 通知内容
            #         }))
            #         could_sell, _ = self.sell(df.candles[-1], units, product_code=product_code)
            #         logger.info(f'action=sell could_sell={could_buy}')
            #
            #         if could_sell:
            #             self.in_atr_trade = True
            #             self.atr_sell_stop_limit = math.floor(
            #                 atr_down_2[-1] / constants.MIN_TRADE_PRICE_MAP[product_code])\
            #                                        * constants.MIN_TRADE_PRICE_MAP[product_code]
            #             logger.info(f'stop limit={self.atr_sell_stop_limit}')
            #
            #             self.atr_trade = self.send_stop_loss(
            #                 max_units, constants.BUY, self.atr_sell_stop_limit, product_code)
            #             requests.post(settings.WEB_HOOK_URL, data=json.dumps({
            #                 'text': f"stop loss units: {max_units}, side: {constants.BUY}, price: {self.atr_sell_stop_limit}",
            #                 # 通知内容
            #             }))
            #
            # buy_point, sell_point = 0, 0
            #
            # if params.ema_enable and params.ema_period_1 <= len(df.candles) and params.ema_period_2 <= len(df.candles):
            #     if ema_values_1[-2] < ema_values_2[-2] and ema_values_1[-1] >= ema_values_2[-1]:
            #         logger.info("ema buy signal")
            #         buy_point += 1
            #
            #     if ema_values_1[-2] > ema_values_2[-2] and ema_values_1[-1] <= ema_values_2[-1]:
            #         logger.info("ema sell signal")
            #         sell_point += 1
            #
            # if params.bb_enable and params.bb_n <= len(df.candles):
            #     if bb_down[-2] > df.candles[-2].close and bb_down[-1] <= df.candles[-1].close:
            #         logger.info("bb buy signal")
            #         buy_point += 1
            #
            #     if bb_up[-2] < df.candles[-2].close and bb_up[-1] >= df.candles[-1].close:
            #         logger.info("bb sell signal")
            #         sell_point += 1
            #
            # if params.ichimoku_enable:
            #     if (chikou[-2] < df.candles[-2].high and
            #             chikou[-1] >= df.candles[-1].high and
            #             senkou_a[-1] < df.candles[-1].low and
            #             senkou_b[-1] < df.candles[-1].low and
            #             tenkan[-1] > kijun[-1]):
            #         logger.info("ichimoku buy signal")
            #         buy_point += 1
            #
            #     if (chikou[-2] > df.candles[-2].low and
            #             chikou[-1] <= df.candles[-1].low and
            #             senkou_a[-1] > df.candles[-1].high and
            #             senkou_b[-1] > df.candles[-1].high and
            #             tenkan[-1] < kijun[-1]):
            #         logger.info("ichimoku sell signal")
            #         sell_point += 1
            #
            # if params.macd_enable:
            #     if macd[-1] < 0 and macd_signal[-1] < 0 and macd[-2] < macd_signal[-2] and macd[-1] >= macd_signal[-1]:
            #         logger.info("MACD buy signal")
            #         buy_point += 1
            #
            #     if macd[-1] > 0 and macd_signal[-1] > 0 and macd[-2] > macd_signal[-2] and macd[-1] <= macd_signal[-1]:
            #         logger.info("MACD sell signal")
            #         sell_point += 1
            #
            # if params.rsi_enable and rsi_values[-2] != 0 and rsi_values[-1] != 100:
            #     if rsi_values[-2] < params.rsi_buy_thread and rsi_values[-1] >= params.rsi_buy_thread:
            #         logger.info("RSI buy signal")
            #         buy_point += 1
            #
            #     if rsi_values[-2] > params.rsi_sell_thread and rsi_values[-1] <= params.rsi_sell_thread:
            #         logger.info("RSI sell signal")
            #         sell_point += 1
            #
            # logger.info(f'buy_point: {buy_point}, sell_point: {sell_point}')
            # if not self.in_atr_trade and (buy_point > 0 or
            #                               (len(self.trade_list) > 1 and self.stop_limit < df.candles[-1].close)):
            #
            #     if product_code == "FX_BTC_JPY":
            #         use_balance = self.balance.available * settings.use_percent
            #         units = math.floor((use_balance / df.candles[-1].close) * 10000) / 10000
            #     else:
            #         units = int(float(self.balance.available) * self.use_percent / (df.candles[-1].close * fx_adjustment))
            #     could_buy, close_trade = self.buy(df.candles[-1], units, product_code=product_code)
            #     if could_buy:
            #         self.stop_limit = df.candles[-1].close * self.stop_limit_percent
            #         logger.info(f"stop limit is {self.stop_limit}")
            #         if close_trade:
            #             self.update_optimize_params(is_continue=True, product_code=product_code)
            #
            # if not self.in_atr_trade and (sell_point > 0 or
            #                               (len(self.trade_list) > 1 and self.stop_limit > df.candles[-1].close)):
            #     if product_code == "FX_BTC_JPY":
            #         use_balance = self.balance.available * settings.use_percent
            #         units = math.floor((use_balance / df.candles[-1].close) * 10000) / 10000
            #     else:
            #         units = int(float(self.balance.available) * self.use_percent / (df.candles[-1].close * fx_adjustment))
            #     could_sell, close_trade = self.sell(df.candles[-1], units, product_code=product_code)
            #     if could_sell:
            #         self.stop_limit = df.candles[-1].close * (2 - self.stop_limit_percent)
            #         logger.info(f"stop limit is {self.stop_limit}")
            #         if close_trade:
            #             self.update_optimize_params(is_continue=True, product_code=product_code)

    # def count_signals(self, indicator):
    #     cnt = 0
    #     if indicator['ema_values_1'][-1] > indicator['ema_values_3'][-1]\
    #             and indicator['ema_values_2'][-1] > indicator['ema_values_3'][-1]:
    #         cnt += 1
    #     if indicator['atr_up'][-1] < indicator['df'][-1]:
    #         cnt += 1
    #     if indicator['adx'][-1] > indicator['adxr'][-1] and indicator['di_plus'][-1] > indicator['di_minus'][-1]:
    #         cnt += 1
    #     if indicator['ema_values_1'][-1] < indicator['ema_values_3'][-1]\
    #             and indicator['ema_values_2'][-1] < indicator['ema_values_3'][-1]:
    #         cnt -= 1
    #     if indicator['atr_down'][-1] > indicator['df'][-1]:
    #         cnt -= 1
    #     if indicator['adx'][-1] > indicator['adxr'][-1] and indicator['di_plus'][-1] < indicator['di_minus'][-1]:
    #         cnt -= 1
    #     return cnt

    def ema_trade(self, indicator, product_code, fx_adjustment):
        # logger.info(f'action=ema_trade product_code={product_code} status=run')
        positions = self.position[product_code]['EMA']
        # position closeの確認
        if positions and positions[0].side == "BUY" and indicator['ema_values_1'][-1] < indicator['ema_values_2'][-1]:
            logger.info(f'action=ema_close product_code={product_code}')
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'ema_close_trade product_code={product_code}',  # 通知内容
            }))
            for position in positions:
                self.API.trade_close(position.trade_id)
            self.position[product_code]['EMA'] = []
        if positions and positions[0].side == "SELL" and indicator['ema_values_1'][-1] > indicator['ema_values_2'][-1]:
            logger.info(f'action=ema_close product_code={product_code}')
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'ema_close_trade product_code={product_code}',  # 通知内容
            }))
            for position in positions:
                self.API.trade_close(position.trade_id)
            self.position[product_code]['EMA'] = []

        # 新規EMAトレード
        if not positions \
                and indicator['ema_values_3'][-2] > indicator['ema_values_1'][-2] > indicator['ema_values_2'][-2] \
                and indicator['ema_values_1'][-1] > indicator['ema_values_3'][-1] > indicator['ema_values_2'][-1]:
            logger.info(f'action=new_trade signal=EMA product_code={product_code}')
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'ema_new_trade product_code={product_code}',  # 通知内容
            }))
            units = self.calc_units(self.default_trail_offset[product_code], fx_adjustment)
            self.trail_buy(indicator['df'][-1], units=units, product_code=product_code, trade_signal='EMA',
                           fx_adjustment=fx_adjustment)

        if not positions \
                and indicator['ema_values_3'][-2] < indicator['ema_values_1'][-2] < indicator['ema_values_2'][-2] \
                and indicator['ema_values_1'][-1] < indicator['ema_values_3'][-1] < indicator['ema_values_2'][-1]:
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'ema_new_trade product_code={product_code}',  # 通知内容
            }))
            units = self.calc_units(self.default_trail_offset[product_code], fx_adjustment)
            self.trail_sell(indicator['df'][-1], units=units, product_code=product_code, trade_signal='EMA',
                            fx_adjustment=fx_adjustment)

    def atr_trade(self, indicator, product_code, fx_adjustment):
        logger.info(f'action=atr_trade product_code={product_code} status=run')
        positions = self.position[product_code]['ATR']
        # Loss cutの確認
        if positions and positions[0].side == "BUY" and indicator['df'][-1].close < positions[0].stop_loss:
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'atr_close_trade product_code={product_code}',  # 通知内容
            }))
            for position in positions:
                self.API.trade_close(position.trade_id)
            self.position[product_code]['ATR'] = []
        if positions and positions[0].side == "SELL" and indicator['df'][-1].close > positions[0].stop_loss:
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'atr_close_trade product_code={product_code}',  # 通知内容
            }))
            for position in positions:
                self.API.trade_close(position.trade_id)
            self.position[product_code]['ATR'] = []

        # 買いのときの手動で出すSLの更新
        if positions and position.side == "BUY" and indicator['atr_up_2'][-1] > positions[0].stop_loss:
            stop_loss = math.floor(indicator['atr_up_2'][-1] / constants.MIN_TRADE_PRICE_MAP[product_code]) \
                        * constants.MIN_TRADE_PRICE_MAP[product_code]
            logger.info('action=atr_trade status=updated_stop_loss')
            for position in positions:
                position.stop_loss = stop_loss

        # 売りのときの手動で出すSLの更新
        if position and position.side == "SELL" and indicator['atr_down_2'][-1] < position.stop_loss:
            stop_loss = math.floor(indicator['atr_down_2'][-1] / constants.MIN_TRADE_PRICE_MAP[product_code]) \
                        * constants.MIN_TRADE_PRICE_MAP[product_code]
            logger.info('action=atr_trade status=updated_stop_loss')
            for position in positions:
                position.stop_loss = stop_loss

        # 新規ATRトレード
        if not positions and indicator['atr_up'][-2] > indicator['df'][-2].close \
                and indicator['atr_up'][-1] < indicator['df'][-1].close:
            units = self.calc_units(self.default_trail_offset[product_code], fx_adjustment)
            stop_loss = math.floor(indicator['atr_up_2'][-1] / constants.MIN_TRADE_PRICE_MAP[product_code]) \
                        * constants.MIN_TRADE_PRICE_MAP[product_code]
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'atr_new_trade product_code={product_code}',  # 通知内容
            }))
            self.trail_buy(indicator['df'][-1], units=units, product_code=product_code, trade_signal='ATR',
                           fx_adjustment=fx_adjustment, stop_loss=stop_loss)

        if not position and indicator['atr_down'][-2] < indicator['df'][-2].close \
                and indicator['atr_down'][-1] > indicator['df'][-1].close:
            units = self.calc_units(self.default_trail_offset[product_code], fx_adjustment)
            stop_loss = math.floor(indicator['atr_down_2'][-1] / constants.MIN_TRADE_PRICE_MAP[product_code]) \
                        * constants.MIN_TRADE_PRICE_MAP[product_code]
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'atr_new_trade product_code={product_code}',  # 通知内容
            }))
            self.trail_sell(indicator['df'][-1], units=units, product_code=product_code, trade_signal='ATR',
                            fx_adjustment=fx_adjustment, stop_loss=stop_loss)

    def adx_trade(self, indicator, product_code, fx_adjustment):
        logger.info(f'action=adx_trade product_code={product_code} status=run')
        positions = self.position[product_code]['ADX']
        # position closeの確認
        if positions and positions[0].side == "BUY" \
                and (indicator['di_plus'][-1] < indicator['di_minus'][-1]
                     or indicator['adx'][-4] > indicator['adx'][-3] > indicator['adx'][-2] > indicator['adx'][-1]):
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'adx_close_trade product_code={product_code}',  # 通知内容
            }))
            for position in positions:
                self.API.trade_close(position.trade_id)
            self.position[product_code]['ADX'] = []
        if positions and positions[0].side == "SELL" \
                and (indicator['di_plus'][-1] > indicator['di_minus'][-1]
                     or indicator['adx'][-4] > indicator['adx'][-3] > indicator['adx'][-2] > indicator['adx'][-1]):
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'adx_close_trade product_code={product_code}',  # 通知内容
            }))
            for position in positions:
                self.API.trade_close(position.trade_id)
            self.position[product_code]['ADX'] = []

        # 新規ADXトレード
        if not positions \
                and indicator['adxr'][-2] > indicator['adx'][-2] and indicator['adxr'][-1] < indicator['adx'][-1] \
                and indicator['di_plus'][-1] > indicator['di_minus'][-1]:
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'adx_new_trade product_code={product_code}',  # 通知内容
            }))
            units = self.calc_units(self.default_trail_offset[product_code], fx_adjustment)
            self.trail_buy(indicator['df'][-1], units=units, product_code=product_code, trade_signal='ADX',
                           fx_adjustment=fx_adjustment)

        if not positions \
                and indicator['adxr'][-2] > indicator['adx'][-2] and indicator['adxr'][-1] < indicator['adx'][-1] \
                and indicator['di_plus'][-1] < indicator['di_minus'][-1]:
            requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                'text': f'adx_new_trade product_code={product_code}',  # 通知内容
            }))
            units = self.calc_units(self.default_trail_offset[product_code], fx_adjustment)
            self.trail_sell(indicator['df'][-1], units=units, product_code=product_code, trade_signal='ADX',
                            fx_adjustment=fx_adjustment)

    def calc_units(self, offset, fx_adjustment):
        units = math.floor(float(self.balance.available) * (1 - self.stop_limit_percent) / (offset * fx_adjustment))
        return units

    def trade_back_test(self, product_code=None):
        if product_code is None:
            product_code = self.product_code
        logger.info('action=back_test status=run')
        back_test_stop_limit = 0
        back_test_atr_buy_stop_limit = 0
        back_test_atr_sell_stop_limit = 1000000000
        in_atr_trade = False

        params = self.optimized_trade_params[product_code]
        if params is None:
            self.update_optimize_params(False, product_code)
            return

        df = DataFrameCandle(product_code, self.duration)
        df.set_all_candles(self.past_period)

        if params.ema_enable:
            ema_values_1 = talib.EMA(np.array(df.closes), params.ema_period_1)
            ema_values_2 = talib.EMA(np.array(df.closes), params.ema_period_2)

        if params.bb_enable:
            bb_up, _, bb_down = talib.BBANDS(np.array(df.closes), params.bb_n, params.bb_k, params.bb_k, 0)

        atr = talib.ATR(
            np.array(df.highs), np.array(df.lows),
            np.array(df.closes), params.atr_n)
        mid_list = talib.EMA(np.array(df.closes), params.atr_n)
        atr_up = (mid_list + atr * params.atr_k_1).tolist()
        atr_down = (mid_list - atr * params.atr_k_1).tolist()
        atr_up_2 = (mid_list + atr * params.atr_k_2).tolist()
        atr_down_2 = (mid_list - atr * params.atr_k_2).tolist()
        if atr_up_2[-1] > back_test_atr_buy_stop_limit:
            back_test_atr_buy_stop_limit = atr_up_2[-1]
        if atr_down_2[-1] > back_test_atr_sell_stop_limit:
            back_test_atr_sell_stop_limit = atr_down_2[-1]

        if params.ichimoku_enable:
            tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku_cloud(df.closes)

        if params.rsi_enable:
            rsi_values = talib.RSI(np.array(df.closes), params.rsi_period)

        if params.macd_enable:
            macd, macd_signal, _ = talib.MACD(np.array(df.closes), params.macd_fast_period, params.macd_slow_period,
                                              params.macd_signal_period)

        for i in range(1, len(df.candles)):
            atr_buy_point, atr_sell_point = 0, 0
            if params.atr_n <= i:
                if atr_up[i - 1] > df.candles[i - 1].close and atr_up[i] <= df.candles[i].close:
                    atr_buy_point += 1

                if atr_down[i - 1] < df.candles[i - 1].close and atr_down[i] >= df.candles[i].close:
                    atr_sell_point += 1

            if atr_buy_point > 0 or back_test_atr_sell_stop_limit < df.candles[i].close:
                units = 1
                could_buy, close_trade = self.buy(df.candles[i], units, True, product_code)
                if not could_buy:
                    continue
                in_atr_trade = True
                back_test_atr_buy_stop_limit = atr_down[i]
                if close_trade:
                    in_atr_trade = False
                    self.update_optimize_params(is_continue=True, product_code=product_code)

            if atr_sell_point > 0 or back_test_atr_buy_stop_limit > df.candles[i].close:
                units = 1
                could_sell, close_trade = self.sell(df.candles[i], units, True, product_code=product_code)
                if not could_sell:
                    continue

                in_atr_trade = True
                back_test_atr_sell_stop_limit = atr_up[i]
                if close_trade:
                    in_atr_trade = False
                    self.update_optimize_params(is_continue=True, product_code=product_code)

        for i in range(1, len(df.candles)):
            buy_point, sell_point = 0, 0

            if params.ema_enable and params.ema_period_1 <= i and params.ema_period_2 <= i:
                if ema_values_1[i - 1] < ema_values_2[i - 1] and ema_values_1[i] >= ema_values_2[i]:
                    buy_point += 1

                if ema_values_1[i - 1] > ema_values_2[i - 1] and ema_values_1[i] <= ema_values_2[i]:
                    sell_point += 1

            if params.bb_enable and params.bb_n <= i:
                if bb_down[i - 1] > df.candles[i - 1].close and bb_down[i] <= df.candles[i].close:
                    buy_point += 1

                if bb_up[i - 1] < df.candles[i - 1].close and bb_up[i] >= df.candles[i].close:
                    sell_point += 1

            if params.ichimoku_enable:
                if (chikou[i - 1] < df.candles[i - 1].high and
                        chikou[i] >= df.candles[i].high and
                        senkou_a[i] < df.candles[i].low and
                        senkou_b[i] < df.candles[i].low and
                        tenkan[i] > kijun[i]):
                    buy_point += 1

                if (chikou[i - 1] > df.candles[i - 1].low and
                        chikou[i] <= df.candles[i].low and
                        senkou_a[i] > df.candles[i].high and
                        senkou_b[i] > df.candles[i].high and
                        tenkan[i] < kijun[i]):
                    sell_point += 1

            if params.macd_enable:
                if macd[i] < 0 and macd_signal[i] < 0 and macd[i - 1] < macd_signal[i - 1] and macd[i] >= macd_signal[
                    i]:
                    buy_point += 1

                if macd[i] > 0 and macd_signal[i] > 0 and macd[i - 1] > macd_signal[i - 1] and macd[i] <= macd_signal[
                    i]:
                    sell_point += 1

            if params.rsi_enable and rsi_values[i - 1] != 0 and rsi_values[i - 1] != 100:
                if rsi_values[i - 1] < params.rsi_buy_thread and rsi_values[i] >= params.rsi_buy_thread:
                    buy_point += 1

                if rsi_values[i - 1] > params.rsi_sell_thread and rsi_values[i] <= params.rsi_sell_thread:
                    sell_point += 1

            if not in_atr_trade and (buy_point > 0 or
                                     (self.signal_events.has_short and back_test_stop_limit < df.candles[i].close)):

                units = 1
                could_buy, close_trade = self.buy(df.candles[i], units, True, product_code)
                if not could_buy:
                    continue

                back_test_stop_limit = df.candles[i].close * self.stop_limit_percent
                if close_trade:
                    self.update_optimize_params(is_continue=True, product_code=product_code)

            if not in_atr_trade and (sell_point > 0 or
                                     (self.signal_events.has_long and back_test_stop_limit > df.candles[i].close)):
                units = 1
                could_sell, close_trade = self.sell(df.candles[i], units, True, product_code)
                if not could_sell:
                    continue

                back_test_stop_limit = df.candles[i].close * (2 - self.stop_limit_percent)
                if close_trade:
                    self.update_optimize_params(is_continue=True, product_code=product_code)

    def alert_signal(self, product_code=None):
        if product_code is None:
            product_code = self.product_code
        logger.info('action=alert_signal status=run')
        for duration in [constants.DURATION_5M, constants.DURATION_15M, constants.DURATION_30M,
                         constants.DURATION_1H, constants.DURATION_1D]:
            df = DataFrameCandle(product_code, duration)
            df.set_all_candles(self.past_period)

            ema_values_1 = talib.EMA(np.array(df.closes), 5)
            ema_values_2 = talib.EMA(np.array(df.closes), 25)
            ema_values_3 = talib.EMA(np.array(df.closes), 75)

            bb_up, _, bb_down = talib.BBANDS(np.array(df.closes), 20, 2, 2, 0)

            atr = talib.ATR(np.array(df.highs), np.array(df.lows),
                            np.array(df.closes), 14)
            mid_list = talib.EMA(np.array(df.closes), 14)
            atr_up = (mid_list + atr * 2).tolist()
            atr_down = (mid_list - atr * 2).tolist()

            tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku_cloud(df.closes)

            rsi_values = talib.RSI(np.array(df.closes), 14)

            macd, macd_signal, _ = talib.MACD(np.array(df.closes), 12, 26, 9)

            if 75 <= len(df.candles):
                if ema_values_1[-2] < ema_values_2[-2] and ema_values_1[-1] >= ema_values_2[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA5 surpassed EMA25; duration: {duration}, product_code: {product_code}',  # 通知内容
                    }))

                if ema_values_1[-2] > ema_values_2[-2] and ema_values_1[-1] <= ema_values_2[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA5 went below EMA25; duration: {duration}, product_code: {product_code}',  # 通知内容
                    }))

                if ema_values_1[-2] < ema_values_3[-2] and ema_values_1[-1] >= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA5 surpassed EMA75; duration: {duration}, product_code: {product_code}',  # 通知内容
                    }))

                if ema_values_1[-2] > ema_values_3[-2] and ema_values_1[-1] <= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA5 went below EMA75; duration: {duration}, product_code: {product_code}',  # 通知内容
                    }))

                if ema_values_2[-2] < ema_values_3[-2] and ema_values_2[-1] >= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA25 surpassed EMA75; duration: {duration}, product_code: {product_code}',  # 通知内容
                    }))

                if ema_values_2[-2] > ema_values_3[-2] and ema_values_2[-1] <= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA25 went below EMA75; duration: {duration}, product_code: {product_code}',  # 通知内容
                    }))

            # if 20 <= len(df.candles):
            #     if bb_down[-2] > df.candles[-2].close and bb_down[-1] <= df.candles[-1].close:
            #         requests.post(settings.WEB_HOOK_URL, data=json.dumps({
            #             'text': f'candle stick surpassed BB_Down; duration: {duration}, product_code: {product_code}',  # 通知内容
            #         }))
            #
            #     if bb_up[-2] < df.candles[-2].close and bb_up[-1] >= df.candles[-1].close:
            #         requests.post(settings.WEB_HOOK_URL, data=json.dumps({
            #             'text': f'candle stick went below BB_Up; duration: {duration}, product_code: {product_code}', # 通知内容
            #         }))

            if (chikou[-2] < df.candles[-2].high and
                    chikou[-1] >= df.candles[-1].high and
                    senkou_a[-1] < df.candles[-1].low and
                    senkou_b[-1] < df.candles[-1].low and
                    tenkan[-1] > kijun[-1]):
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'三役好転; duration: {duration}, product_code: {product_code}',  # 通知内容
                }))

            if (chikou[-2] > df.candles[-2].low and
                    chikou[-1] <= df.candles[-1].low and
                    senkou_a[-1] > df.candles[-1].high and
                    senkou_b[-1] > df.candles[-1].high and
                    tenkan[-1] < kijun[-1]):
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'三役逆転; duration: {duration}, product_code: {product_code}',  # 通知内容
                }))

            if macd[-1] < 0 and macd_signal[-1] < 0 and macd[-2] < macd_signal[-2] and macd[-1] >= macd_signal[-1]:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'MACD surpassed MACD signal; duration: {duration}, product_code: {product_code}',  # 通知内容
                }))

            if macd[-1] > 0 and macd_signal[-1] > 0 and macd[-2] > macd_signal[-2] and macd[-1] <= macd_signal[-1]:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'MACD went below MACD signal; duration: {duration}, product_code: {product_code}',  # 通知内容
                }))

            if rsi_values[-2] != 0 and rsi_values[-2] != 100:
                if rsi_values[-2] < 30 and rsi_values[-1] >= 30:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'candle stick surpassed RSI 30; duration: {duration}, product_code: {product_code}',
                        # 通知内容
                    }))

                if rsi_values[-2] > 70 and rsi_values[-1] <= 70:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'candle stick went below RSI 70; duration: {duration}, product_code: {product_code}',
                        # 通知内容
                    }))

            if atr_up[-2] > df.candles[-2].close and atr_up[-1] <= df.candles[-1].close:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'candle stick broke ATR Up; duration: {duration}, product_code: {product_code}',  # 通知内容
                }))

            if atr_down[-2] < df.candles[-2].close and atr_down[-1] >= df.candles[-1].close:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'candle stick broke ATR Down; duration: {duration}, product_code: {product_code}',  # 通知内容
                }))
