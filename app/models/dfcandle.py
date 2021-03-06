from dict2obj import Dict2Obj
import numpy as np
import talib

from app.models.candle import factory_candle_class
from app.models.events import SignalEvents
import settings
from utils.utils import Serializer
from tradingalgo.algo import ichimoku_cloud, force_index


def nan_to_zero(values: np.asarray):
    values[np.isnan(values)] = 0
    return values


def empty_to_none(input_list):
    if not input_list:
        return None
    return input_list


class Sma(Serializer):
    def __init__(self, period: int, values: list):
        self.period = period
        self.values = values


class Ema(Serializer):
    def __init__(self, period: int, values: list):
        self.period = period
        self.values = values


class BBands(Serializer):
    def __init__(self, n: int, k: float, up: list, mid: list, down: list):
        self.n = n
        self.k = k
        self.up = up
        self.mid = mid
        self.down = down


class Atr(Serializer):
    def __init__(self, n: int, k: float, up: list, down: list):
        self.n = n
        self.k = k
        self.up = up
        # self.mid = mid
        self.down = down


class Di(Serializer):
    def __init__(self, n: int, plus_di: list, minus_di: list):
        self.n = n
        self.plus_di = plus_di
        self.minus_di = minus_di


class Adx(Serializer):
    def __init__(self, n: int, adx: list, adxr: list):
        self.n = n
        self.adx = adx
        self.adxr = adxr


class IchimokuCloud(Serializer):
    def __init__(self, tenkan: list, kijun: list, senkou_a: list,
                 senkou_b: list, chikou: list):
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou_a = senkou_a
        self.senkou_b = senkou_b
        self.chikou = chikou


class Rsi(Serializer):
    def __init__(self, period: int, values: list):
        self.period = period
        self.values = values


class Macd(Serializer):
    def __init__(self, fast_period: int, slow_period: int, signal_period: int, macd: list, macd_signal: list, macd_hist: list):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.macd = macd
        self.macd_signal = macd_signal
        self.macd_hist = macd_hist


class ForceIndex(Serializer):
    def __init__(self, n: int, force_idx: list):
        self.n = n
        self.force_idx = force_idx


class DataFrameCandle(object):

    def __init__(self, product_code=settings.product_code, duration=settings.trade_duration):
        self.product_code = product_code
        self.duration = duration
        self.candle_cls = factory_candle_class(self.product_code, self.duration)
        self.candles = []
        self.fraction_candle = None
        self.smas = []
        self.emas = []
        self.bbands = BBands(0, 0, [], [], [])
        self.atr = Atr(0, 0, [], [])
        self.di = Di(0, [], [])
        self.adx = Adx(0, [], [])
        self.ichimoku_cloud = IchimokuCloud([], [], [], [], [])
        self.rsi = Rsi(0, [])
        self.macd = Macd(0, 0, 0, [], [], [])
        self.force_idx = []
        self.events = SignalEvents()

    def set_all_candles(self, limit=1000):
        self.candles = self.candle_cls.get_all_candles(limit)
        self.fraction_candle = self.candle_cls.get_fraction_candle(self.product_code)
        return self.candles

    def set_recent_candles(self, limit=1000):
        self.set_all_candles(limit)
        self.candles = self.candles.append(self.fraction_candle)
        return self.candles

    @property
    def value(self):
        return {
            'product_code': self.product_code,
            'duration': self.duration,
            'candles': [c.value for c in self.candles],
            'smas': empty_to_none([s.value for s in self.smas]),
            'emas': empty_to_none([s.value for s in self.emas]),
            'bbands': self.bbands.value,
            'atr': self.atr.value,
            'ichimoku': self.ichimoku_cloud.value,
            'di': self.di.value,
            'adx': self.adx.value,
            'rsi': self.rsi.value,
            'macd': self.macd.value,
            'force_idx': empty_to_none([s.value for s in self.force_idx]),
            'events': self.events.value,
        }

    @property
    def opens(self):
        values = []
        for candle in self.candles:
            values.append(candle.open)
        return values

    @property
    def closes(self):
        values = []
        for candle in self.candles:
            values.append(candle.close)
        return values

    @property
    def highs(self):
        values = []
        for candle in self.candles:
            values.append(candle.high)
        return values

    @property
    def lows(self):
        values = []
        for candle in self.candles:
            values.append(candle.low)
        return values

    @property
    def volumes(self):
        values = []
        for candle in self.candles:
            values.append(candle.volume)
        return values

    def add_sma(self, period: int):

        if len(self.closes) > period:
            values = talib.SMA(np.asarray(self.closes), period)
            sma = Sma(
                period,
                nan_to_zero(values).tolist()
            )
            self.smas.append(sma)
            return True
        return False

    def add_ema(self, period: int):

        if len(self.closes) > period:
            values = talib.EMA(np.asarray(self.closes), period)
            ema = Ema(
                period,
                nan_to_zero(values).tolist()
            )
            self.emas.append(ema)
            return True
        return False

    def add_bbands(self, n: int, k: float):
        if n <= len(self.closes):
            up, mid, down = talib.BBANDS(np.array(self.closes), n, k, k, 0)
            up_list = nan_to_zero(up).tolist()
            mid_list = nan_to_zero(mid).tolist()
            down_list = nan_to_zero(down).tolist()
            self.bbands = BBands(n, k, up_list, mid_list, down_list)
            return True
        return False

    def add_atr(self, n: int, k: float):
        if n <= len(self.closes):
            atr = talib.ATR(
                np.array(self.highs), np.array(self.lows),
                np.array(self.closes), n)
            mid_list = nan_to_zero(talib.EMA(np.array(self.closes), n))
            up_list = (mid_list + nan_to_zero(atr) * k).tolist()
            down_list = (mid_list - nan_to_zero(atr) * k).tolist()
            self.atr = Atr(n, k, up_list, down_list)
            return True
        return False

    def add_di(self, n: int):
        if n <= len(self.closes):
            plus_di = nan_to_zero(talib.PLUS_DI(
                np.array(self.highs), np.array(self.lows),
                np.array(self.closes), n)).tolist()
            minus_di = nan_to_zero(talib.MINUS_DI(
                np.array(self.highs), np.array(self.lows),
                np.array(self.closes), n)).tolist()
            self.di = Di(n, plus_di, minus_di)
            return True
        return False

    def add_adx(self, n: int):
        if n <= len(self.closes):
            adx = nan_to_zero(talib.ADX(
                np.array(self.highs), np.array(self.lows),
                np.array(self.closes), n)).tolist()
            adxr = nan_to_zero(talib.ADXR(
                np.array(self.highs), np.array(self.lows),
                np.array(self.closes), n)).tolist()
            self.adx = Adx(n, adx, adxr)
            return True
        return False

    def add_ichimoku(self):
        if len(self.closes) >= 9:
            tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku_cloud(self.closes)
            self.ichimoku_cloud = IchimokuCloud(
                tenkan, kijun, senkou_a, senkou_b, chikou)
            return True
        return False

    def add_rsi(self, period: int):

        if len(self.closes) > period:
            values = talib.RSI(np.asarray(self.closes), period)
            rsi = Rsi(
                period,
                nan_to_zero(values).tolist()
            )
            self.rsi = rsi
            return True
        return False

    def add_macd(self, fast_period: int, slow_period: int, signal_period: int):
        if len(self.candles) > 1:
            macd, macd_signal, macd_hist = talib.MACD(
                np.asarray(self.closes), fast_period, slow_period, signal_period)
            macd_list = nan_to_zero(macd).tolist()
            macd_signal_list = nan_to_zero(macd_signal).tolist()
            macd_hist_list = nan_to_zero(macd_hist).tolist()
            self.macd = Macd(
                fast_period, slow_period, signal_period, macd_list, macd_signal_list, macd_hist_list)
            return True
        return False

    def add_force_index(self, period: int):
        if len(self.closes) > period:
            values = force_index(self.closes, self.volumes, period)
            force_idx = ForceIndex(period, values)
            self.force_idx.append(force_idx)
            return True
        return False
        # if len(self.candles) > period:
        #     force_idx = force_index(self.closes, self.volumes, period)
        #     self.force_idx = ForceIndex(period, force_idx)
        #     return True
        # return False

    def add_events(self, time):
        signal_events = SignalEvents.get_signal_events_after_time(time)
        if len(signal_events.signals) > 0:
            self.events = signal_events
            return True
        return False

    def back_test_ema(self, period_1: int, period_2: int):
        if len(self.candles) <= period_1 or len(self.candles) <= period_2:
            return None

        signal_events = SignalEvents()
        ema_value_1 = talib.EMA(np.array(self.closes), period_1)
        ema_value_2 = talib.EMA(np.array(self.closes), period_2)

        for i in range(1, len(self.candles)):
            if i < period_1 or i < period_2:
                continue

            if ema_value_1[i-1] < ema_value_2[i-1] and ema_value_1[i] >= ema_value_2[i]:
                signal_events.buy(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

            if ema_value_1[i-1] > ema_value_2[i-1] and ema_value_1[i] <= ema_value_2[i]:
                signal_events.sell(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

        return signal_events

    def optimize_ema(self):
        performance = 0
        best_period_1 = 7
        best_period_2 = 14

        for period_1 in range(5, 12):
            for period_2 in range(12, 20):
                signal_events = self.back_test_ema(period_1, period_2)
                if signal_events is None:
                    continue
                profit = signal_events.profit
                if performance < profit:
                    performance = profit
                    best_period_1 = period_1
                    best_period_2 = period_2

        return performance, best_period_1, best_period_2

    def back_test_bb(self, n: int, k: float):
        if len(self.candles) <= n:
            return None

        signal_events = SignalEvents()
        bb_up, _, bb_down = talib.BBANDS(np.array(self.closes), n, k, k, 0)

        for i in range(1, len(self.candles)):
            if i < n:
                continue

            if bb_down[i-1] > self.candles[i-1].close and bb_down[i] <= self.candles[i].close:
                signal_events.buy(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

            if bb_up[i-1] < self.candles[i-1].close and bb_up[i] >= self.candles[i].close:
                signal_events.sell(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

        return signal_events

    def optimize_bb(self):
        performance = 0
        best_n = 20
        best_k = 2.0

        for n in range(10, 20):
            for k in np.arange(1.9, 2.1, 0.1):
                signal_events = self.back_test_bb(n, k)
                if signal_events is None:
                    continue
                profit = signal_events.profit
                if performance < profit:
                    performance = profit
                    best_n = n
                    best_k = k

        return performance, best_n, best_k

    def back_test_atr(self, n: int, k_1: float, k_2: float):
        if len(self.candles) <= n:
            return None

        signal_events = SignalEvents()
        atr = talib.ATR(
            np.array(self.highs), np.array(self.lows), np.array(self.closes), n)
        mid_list = nan_to_zero(talib.EMA(np.asarray(self.closes), n))
        up_list = (mid_list + nan_to_zero(atr) * k_1).tolist()
        down_list = (mid_list - nan_to_zero(atr) * k_1).tolist()
        up_list_2 = (mid_list + nan_to_zero(atr) * k_2).tolist()
        down_list_2 = (mid_list - nan_to_zero(atr) * k_2).tolist()
        has_long_position = False
        has_short_position = False
        buy_stop_loss = 0
        sell_stop_loss = 1000000000

        for i in range(1, len(self.candles)):
            if i < n:
                continue

            if has_long_position and self.candles[i].low < buy_stop_loss:
                signal_events.sell(product_code=self.product_code, time=self.candles[i].time, price=buy_stop_loss, units=1.0, save=False)
                has_long_position = False
                buy_stop_loss = 0

            if has_short_position and self.candles[i].high > sell_stop_loss:
                signal_events.buy(product_code=self.product_code, time=self.candles[i].time, price=sell_stop_loss, units=1.0, save=False)
                has_short_position = False
                sell_stop_loss = 1000000000

            if has_long_position:
                buy_stop_loss = max(buy_stop_loss, up_list_2[i])

            if has_short_position:
                sell_stop_loss = min(sell_stop_loss, down_list_2[i])

            if up_list[i-1] > self.candles[i-1].close and up_list[i] <= self.candles[i].close:
                signal_events.buy(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)
                has_long_position = True
                buy_stop_loss = up_list_2[i]

            if down_list[i-1] < self.candles[i-1].close and down_list[i] >= self.candles[i].close:
                signal_events.sell(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)
                has_short_position = True
                sell_stop_loss = down_list_2[i]

        return signal_events

    def optimize_atr(self):
        performance = 0
        best_n = 14
        best_k_1 = 2.0
        best_k_2 = 0.0

        for n in range(7, 17):
            for k_1 in np.arange(1.0, 3.0, 0.2):
                for k_2 in np.arange(-1.0, 1.0, 0.2):
                    signal_events = self.back_test_atr(n, k_1, k_2)
                    if signal_events is None:
                        continue
                    profit = signal_events.profit
                    if performance < profit:
                        performance = profit
                        best_n = n
                        best_k_1 = k_1
                        best_k_2 = k_2

        return performance, best_n, best_k_1, best_k_2

    def back_test_ichimoku(self):
        if len(self.candles) <= 52:
            return None

        signal_events = SignalEvents()
        tenkan, kijun, senkou_a, senkou_b, chikou = ichimoku_cloud(self.closes)

        for i in range(1, len(self.candles)):
            if (chikou[i-1] < self.candles[i-1].high and
                    chikou[i] >= self.candles[i].high and
                    senkou_a[i] < self.candles[i].low and
                    senkou_b[i] < self.candles[i].low and
                    tenkan[i] > kijun[i]):
                signal_events.buy(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

            if (chikou[i-1] > self.candles[i-1].low and
                    chikou[i] <= self.candles[i].low and
                    senkou_a[i] > self.candles[i].high and
                    senkou_b[i] > self.candles[i].high and
                    tenkan[i] < kijun[i]):
                signal_events.sell(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

        return signal_events

    def optimize_ichimoku(self):
        signal_events = self.back_test_ichimoku()
        if signal_events is None:
            return 0.0
        return signal_events.profit

    def back_test_rsi(self, period: int, buy_thread: float, sell_thread: float):
        if len(self.candles) <= period:
            return None

        signal_events = SignalEvents()
        values = talib.RSI(np.array(self.closes), period)

        for i in range(1, len(self.candles)):
            if values[i-1] == 0 or values[i-1] == 100:
                continue

            if values[i-1] < buy_thread and values[i] >= buy_thread:
                signal_events.buy(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

            if values[i-1] > sell_thread and values[i] <= sell_thread:
                signal_events.sell(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

        return signal_events

    def optimize_rsi(self):
        performance = 0
        best_period = 14
        best_buy_thread = 30.0
        best_sell_thread = 70.0

        for period in range(10, 20):
            for buy_thread in np.arange(29.9, 30.1, 0.1):
                for sell_thread in np.arange(69.9, 70.1, 0.1):
                    signal_events = self.back_test_rsi(period, buy_thread, sell_thread)
                    if signal_events is None:
                        continue
                    profit = signal_events.profit
                    if performance < profit:
                        performance = profit
                        best_period = period
                        best_buy_thread = buy_thread
                        best_sell_thread = sell_thread

        return performance, best_period, best_buy_thread, best_sell_thread

    def back_test_macd(self, macd_fast_period: int, macd_slow_period: int, macd_signal_period: int):
        if len(self.candles) <= macd_fast_period or len(self.candles) <= macd_slow_period or len(self.candles) <= macd_signal_period:
            return None

        signal_events = SignalEvents()
        macd, macd_signal, _ = talib.MACD(np.array(self.closes), macd_slow_period, macd_fast_period, macd_signal_period)

        for i in range(1, len(self.candles)):
            if macd[i] < 0 and macd_signal[i] < 0 and macd[i-1] < macd_signal[i-1] and macd[i] >= macd_signal[i]:
                signal_events.buy(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

            if macd[i] > 0 and macd_signal[i] > 0 and macd[i-1] > macd_signal[i-1] and macd[i] <= macd_signal[i]:
                signal_events.sell(product_code=self.product_code, time=self.candles[i].time, price=self.candles[i].close, units=1.0, save=False)

        return signal_events

    def optimize_macd(self):
        performance = 0
        best_macd_fast_period = 12
        best_macd_slow_period = 26
        best_macd_signal_period = 9

        for fast_period in range(10, 19):
            for slow_period in range(20, 30):
                for signal_period in range(5, 15):
                    signal_events = self.back_test_macd(fast_period, slow_period, signal_period)
                    if signal_events is None:
                        continue
                    profit = signal_events.profit
                    if performance < profit:
                        performance = profit
                        best_macd_fast_period = fast_period
                        best_macd_slow_period = slow_period
                        best_macd_signal_period = signal_period

        return performance, best_macd_fast_period, best_macd_slow_period, best_macd_signal_period

    def optimize_params(self):
        ema_performance, ema_period_1, ema_period_2 = self.optimize_ema()
        bb_performance, bb_n, bb_k = self.optimize_bb()
        atr_performance, atr_n, atr_k_1, atr_k_2 = self.optimize_atr()
        ichimoku_performance = self.optimize_ichimoku()
        rsi_performance, rsi_period, rsi_buy_thread, rsi_sell_thread = self.optimize_rsi()
        macd_performance, macd_fast_period, macd_slow_period, macd_signal_period = self.optimize_macd()

        ema_ranking = Dict2Obj({'performance': ema_performance, 'enable': False})
        bb_ranking = Dict2Obj({'performance': bb_performance, 'enable': False})
        atr_ranking = Dict2Obj({'performance': atr_performance, 'enable': True})
        ichimoku_ranking = Dict2Obj({'performance': ichimoku_performance, 'enable': False})
        rsi_ranking = Dict2Obj({'performance': rsi_performance, 'enable': False})
        macd_ranking = Dict2Obj({'performance': macd_performance, 'enable': False})

        rankings = [ema_ranking, bb_ranking, ichimoku_ranking, rsi_ranking, macd_ranking]
        rankings = sorted(rankings, key=lambda o: o.performance, reverse=True)

        for i, ranking in enumerate(rankings):
            if i >= settings.num_ranking:
                break

            if ranking.performance > 0:
                ranking.enable = True

        return Dict2Obj({
            'ema_enable': ema_ranking.enable,
            'ema_period_1': ema_period_1,
            'ema_period_2': ema_period_2,
            'bb_enable': bb_ranking.enable,
            'bb_n': bb_n,
            'bb_k': bb_k,
            'atr_enable': atr_ranking.enable,
            'atr_n': atr_n,
            'atr_k_1': atr_k_1,
            'atr_k_2': atr_k_2,
            'ichimoku_enable': ichimoku_ranking.enable,
            'rsi_enable': rsi_ranking.enable,
            'rsi_period': rsi_period,
            'rsi_buy_thread': rsi_buy_thread,
            'rsi_sell_thread': rsi_sell_thread,
            'macd_enable': macd_ranking.enable,
            'macd_fast_period': macd_fast_period,
            'macd_slow_period': macd_slow_period,
            'macd_signal_period': macd_signal_period,
        })
