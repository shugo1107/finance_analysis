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
        elif client.lower() == "bitflyer":
            self.API = BitflyerClient(settings.bitflyer_access_key, settings.bitflyer_secret_key)

        if back_test:
            self.signal_events = SignalEvents()
        else:
            self.signal_events = SignalEvents.get_signal_events_by_count(1)

        self.product_code = product_code
        self.use_percent = use_percent
        self.duration = duration
        self.past_period = past_period
        self.optimized_trade_params = None
        self.stop_limit = 0
        self.atr_buy_stop_limit = 0
        self.atr_sell_stop_limit = 1000000000
        self.stop_limit_percent = stop_limit_percent
        self.back_test = back_test
        self.start_trade = datetime.datetime.utcnow()
        self.candle_cls = factory_candle_class(self.product_code, self.duration)
        self.update_optimize_params(False)
        self.in_atr_trade = False
        self.client = client
        self.trade_list = []

    def update_optimize_params(self, is_continue: bool):
        logger.info('action=update_optimize_params status=run')
        df = DataFrameCandle(self.product_code, self.duration)
        df.set_all_candles(self.past_period)
        if df.candles:
            self.optimized_trade_params = df.optimize_params()
        if self.optimized_trade_params is not None:
            logger.info(f'action=update_optimize_params params={self.optimized_trade_params.__dict__}')

        if is_continue and self.optimized_trade_params is None:
            time.sleep(10 * duration_seconds(self.duration))
            self.update_optimize_params(is_continue)

    def buy(self, candle, units):
        close_trade = False
        if self.back_test:
            could_buy = self.signal_events.buy(self.product_code, candle.time, candle.close, 1.0, save=False)
            return could_buy, close_trade

        if self.start_trade > candle.time:
            logger.warning('action=buy status=false error=old_time')
            return False, close_trade

        if not self.signal_events.can_buy(candle.time):
            logger.warning('action=buy status=false error=previous_was_buy')
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

        order = Order(self.product_code, constants.BUY, units - closed_units)
        trade = self.API.send_order(order)
        could_buy = self.signal_events.buy(
            self.product_code, candle.time,
            (trade.price * (units - closed_units) + sum_price) / units, units, save=True)
        return could_buy, close_trade

    def sell(self, candle, units):
        close_trade = False
        if self.back_test:
            could_sell = self.signal_events.sell(self.product_code, candle.time, candle.close, 1.0, save=False)
            return could_sell, close_trade

        if self.start_trade > candle.time:
            logger.warning('action=sell status=false error=old_time')
            return False, close_trade

        if not self.signal_events.can_sell(candle.time):
            logger.warning('action=sell status=false error=previous_was_sell')
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

        order = Order(self.product_code, constants.SELL, units - closed_units)
        trade = self.API.send_order(order)
        could_sell = self.signal_events.sell(
            self.product_code, candle.time,
            (trade.price * (units - closed_units) + sum_price) / units, units, save=True)
        return could_sell, close_trade

    def trade(self):
        logger.info('action=trade status=run')
        self.alert_signal()
        balance = self.API.get_balance()
        params = self.optimized_trade_params
        if params is None:
            self.update_optimize_params(False)
            return

        df = DataFrameCandle(self.product_code, self.duration)
        df.set_all_candles(self.past_period)

        if params.ema_enable:
            ema_values_1 = talib.EMA(np.array(df.closes), params.ema_period_1)
            ema_values_2 = talib.EMA(np.array(df.closes), params.ema_period_2)

        if params.bb_enable:
            bb_up, _, bb_down = talib.BBANDS(np.array(df.closes), params.bb_n, params.bb_k, params.bb_k, 0)

        if params.atr_enable:
            atr = talib.ATR(
                np.array(df.highs), np.array(df.lows),
                np.array(df.closes), params.atr_n)
            mid_list = talib.EMA(np.array(df.closes), params.atr_n)
            atr_up = (mid_list + atr * params.atr_k).tolist()
            atr_down = (mid_list - atr * params.atr_k).tolist()
            if atr_up[-1] < self.atr_sell_stop_limit:
                self.atr_sell_stop_limit = atr_up[-1]
            if atr_down[-1] > self.atr_buy_stop_limit:
                self.atr_buy_stop_limit = atr_down[-1]

        if params.ichimoku_enable:
            tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku_cloud(df.closes)

        if params.rsi_enable:
            rsi_values = talib.RSI(np.array(df.closes), params.rsi_period)

        if params.macd_enable:
            macd, macd_signal, _ = talib.MACD(np.array(df.closes), params.macd_fast_period, params.macd_slow_period, params.macd_signal_period)

        for i in range(1, len(df.candles)):
            buy_point, sell_point = 0, 0

            if params.ema_enable and params.ema_period_1 <= i and params.ema_period_2 <= i:
                if ema_values_1[i - 1] < ema_values_2[i - 1] and ema_values_1[i] >= ema_values_2[i]:
                    logger.info("ema buy signal")
                    buy_point += 1

                if ema_values_1[i - 1] > ema_values_2[i - 1] and ema_values_1[i] <= ema_values_2[i]:
                    logger.info("ema sell signal")
                    sell_point += 1

            if params.bb_enable and params.bb_n <= i:
                if bb_down[i - 1] > df.candles[i - 1].close and bb_down[i] <= df.candles[i].close:
                    logger.info("bb buy signal")
                    buy_point += 1

                if bb_up[i - 1] < df.candles[i - 1].close and bb_up[i] >= df.candles[i].close:
                    logger.info("bb sell signal")
                    sell_point += 1

            if params.ichimoku_enable:
                if (chikou[i-1] < df.candles[i-1].high and
                        chikou[i] >= df.candles[i].high and
                        senkou_a[i] < df.candles[i].low and
                        senkou_b[i] < df.candles[i].low and
                        tenkan[i] > kijun[i]):
                    logger.info("ichimoku buy signal")
                    buy_point += 1

                if (chikou[i - 1] > df.candles[i - 1].low and
                        chikou[i] <= df.candles[i].low and
                        senkou_a[i] > df.candles[i].high and
                        senkou_b[i] > df.candles[i].high and
                        tenkan[i] < kijun[i]):
                    logger.info("ichimoku sell signal")
                    sell_point += 1

            if params.macd_enable:
                if macd[i] < 0 and macd_signal[i] < 0 and macd[i - 1] < macd_signal[i - 1] and macd[i] >= macd_signal[i]:
                    logger.info("MACD buy signal")
                    buy_point += 1

                if macd[i] > 0 and macd_signal[i] > 0 and macd[i-1] > macd_signal[i - 1] and macd[i] <= macd_signal[i]:
                    logger.info("MACD sell signal")
                    sell_point += 1

            if params.rsi_enable and rsi_values[i-1] != 0 and rsi_values[i-1] != 100:
                if rsi_values[i-1] < params.rsi_buy_thread and rsi_values[i] >= params.rsi_buy_thread:
                    logger.info("RSI buy signal")
                    buy_point += 1

                if rsi_values[i-1] > params.rsi_sell_thread and rsi_values[i] <= params.rsi_sell_thread:
                    logger.info("RSI sell signal")
                    sell_point += 1

            if not self.in_atr_trade and (buy_point > 0 or
                                          (len(self.trade_list) > 1 and self.stop_limit < df.candles[i].close)):

                if self.product_code == "FX_BTC_JPY":
                    use_balance = balance.available * settings.use_percent
                    units = math.floor((use_balance / df.candles[i].close) * 10000) / 10000
                else:
                    units = int(float(balance.available) * self.use_percent)
                could_buy, close_trade = self.buy(df.candles[i], units)
                if not could_buy:
                    continue

                self.stop_limit = df.candles[i].close * self.stop_limit_percent
                logger.info(f"stop limit is {self.stop_limit}")
                self.trade_list = self.API.get_open_trade()
                if close_trade:
                    self.update_optimize_params(is_continue=True)

            if not self.in_atr_trade and (sell_point > 0 or
                                          (len(self.trade_list) > 1 and self.stop_limit > df.candles[i].close)):
                if self.product_code == "FX_BTC_JPY":
                    use_balance = balance.available * settings.use_percent
                    units = math.floor((use_balance / df.candles[i].close) * 10000) / 10000
                else:
                    units = int(float(balance.available) * self.use_percent)
                could_sell, close_trade = self.sell(df.candles[i], units)
                if not could_sell:
                    continue

                self.stop_limit = df.candles[i].close * (2 - self.stop_limit_percent)
                logger.info(f"stop limit is {self.stop_limit}")
                self.trade_list = self.API.get_open_trade()
                if close_trade:
                    self.update_optimize_params(is_continue=True)

        if params.atr_enable:
            for i in range(1, len(df.candles)):
                atr_buy_point, atr_sell_point = 0, 0
                if params.atr_enable and params.atr_n <= i:
                    if atr_up[i - 1] > df.candles[i - 1].close and atr_up[i] <= df.candles[i].close:
                        atr_buy_point += 1

                    if atr_down[i - 1] < df.candles[i - 1].close and atr_down[i] >= df.candles[i].close:
                        atr_sell_point += 1

                if atr_buy_point > 0 or self.atr_sell_stop_limit < df.candles[i].close:
                    balance = self.API.get_balance()
                    if self.product_code == "FX_BTC_JPY":
                        logger.info(f"balance: {balance.available}, atr:{atr_up[i]}, {atr_down[i]}")
                        units = math.floor(
                            balance.available * self.stop_limit_percent / (atr_up[i] - atr_down[i]) * 10000) / 10000
                    else:
                        units = int(balance.available * self.stop_limit_percent / (atr_up[i] - atr_down[i]))
                    logger.info("ATR breaks")
                    could_buy, close_trade = self.buy(df.candles[i], units)
                    if not could_buy:
                        continue
                    self.in_atr_trade = True
                    self.trade_list = self.API.get_open_trade()
                    self.atr_buy_stop_limit = atr_down[i]
                    if close_trade:
                        self.in_atr_trade = False
                        self.update_optimize_params(is_continue=True)

                if atr_sell_point > 0 or self.atr_buy_stop_limit > df.candles[i].close:
                    balance = self.API.get_balance()
                    if self.product_code == "FX_BTC_JPY":
                        logger.info(f"balance: {balance.available}, atr:{atr_up[i]} - {atr_down[i]}")
                        units = math.floor(
                            balance.available * self.stop_limit_percent / (atr_up[i] - atr_down[i]) * 10000) / 10000
                    else:
                        units = int(balance.available * self.stop_limit_percent / (atr_up[i] - atr_down[i]))
                    logger.info("ATR breaks")
                    could_sell, close_trade = self.sell(df.candles[i], units)
                    if not could_sell:
                        continue

                    self.in_atr_trade = True
                    self.trade_list = self.API.get_open_trade()
                    self.atr_sell_stop_limit = atr_up[i]
                    if close_trade:
                        self.in_atr_trade = False
                        self.update_optimize_params(is_continue=True)

    def alert_signal(self):
        logger.info('action=alert_signal status=run')
        for duration in [constants.DURATION_5M, constants.DURATION_15M, constants.DURATION_30M,
                         constants.DURATION_1H, constants.DURATION_1D]:
            df = DataFrameCandle(self.product_code, duration)
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
                        'text': f'EMA5 surpassed EMA25; duration: {duration}, product_code: {self.product_code}', # 通知内容
                    }))

                if ema_values_1[-2] > ema_values_2[-2] and ema_values_1[-1] <= ema_values_2[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA5 went below EMA25; duration: {duration}, product_code: {self.product_code}', # 通知内容
                    }))

                if ema_values_1[-2] < ema_values_3[-2] and ema_values_1[-1] >= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA5 surpassed EMA75; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                    }))

                if ema_values_1[-2] > ema_values_3[-2] and ema_values_1[-1] <= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA5 went below EMA75; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                    }))

                if ema_values_2[-2] < ema_values_3[-2] and ema_values_2[-1] >= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA25 surpassed EMA75; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                    }))

                if ema_values_2[-2] > ema_values_3[-2] and ema_values_2[-1] <= ema_values_3[-1]:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'EMA25 went below EMA75; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                    }))

            if 20 <= len(df.candles):
                if bb_down[-2] > df.candles[-2].close and bb_down[-1] <= df.candles[-1].close:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'candle stick surpassed BB_Down; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                    }))

                if bb_up[-2] < df.candles[-2].close and bb_up[-1] >= df.candles[-1].close:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'candle stick went below BB_Up; duration: {duration}, product_code: {self.product_code}', # 通知内容
                    }))

            if (chikou[-2] < df.candles[-2].high and
                    chikou[-1] >= df.candles[-1].high and
                    senkou_a[-1] < df.candles[-1].low and
                    senkou_b[-1] < df.candles[-1].low and
                    tenkan[-1] > kijun[-1]):
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'三役好転; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                }))

            if (chikou[-2] > df.candles[-2].low and
                    chikou[-1] <= df.candles[-1].low and
                    senkou_a[-1] > df.candles[-1].high and
                    senkou_b[-1] > df.candles[-1].high and
                    tenkan[-1] < kijun[-1]):
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'三役逆転; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                }))

            if macd[-1] < 0 and macd_signal[-1] < 0 and macd[-2] < macd_signal[-2] and macd[-1] >= macd_signal[-1]:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'MACD surpassed MACD signal; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                }))

            if macd[-1] > 0 and macd_signal[-1] > 0 and macd[-2] > macd_signal[-2] and macd[-1] <= macd_signal[-1]:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'MACD went below MACD signal; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                }))

            if rsi_values[-2] != 0 and rsi_values[-2] != 100:
                if rsi_values[-2] < 30 and rsi_values[-1] >= 30:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'candle stick surpassed RSI 30; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                    }))

                if rsi_values[-2] > 70 and rsi_values[-1] <= 70:
                    requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                        'text': f'candle stick went below RSI 70; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                    }))

            if atr_up[-2] > df.candles[-2].close and atr_up[-1] <= df.candles[-1].close:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'candle stick broke ATR Up; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                }))

            if atr_down[-2] < df.candles[-2].close and atr_down[-1] >= df.candles[-1].close:
                requests.post(settings.WEB_HOOK_URL, data=json.dumps({
                    'text': f'candle stick broke ATR Down; duration: {duration}, product_code: {self.product_code}',  # 通知内容
                }))
