import numpy as np
import talib


def nan_to_zero(values: np.asarray):
    values[np.isnan(values)] = 0
    return values


def min_max(in_real):
    min_val = in_real[0]
    max_val = in_real[0]
    for price in in_real:
        if min_val > price:
            min_val = price
        if max_val < price:
            max_val = price
    return min_val, max_val


def ichimoku_cloud(in_real):
    length = len(in_real)
    tenkan = [0] * min(9, length)
    kijun = [0] * min(26, length)
    senkou_a = [0] * min(26, length)
    senkou_b = [0] * min(52, length)
    chikou = [0] * min(26, length)
    for i in range(len(in_real)):
        if i >= 9:
            min_val, max_val = min_max(in_real[i-9:i])
            tenkan.append((min_val + max_val) / 2)
        if i >= 26:
            min_val, max_val = min_max(in_real[i-26:i])
            kijun.append((min_val + max_val) / 2)
            senkou_a.append((tenkan[i] + kijun[i]) / 2)
            chikou.append(in_real[i-26])
        if i >= 52:
            min_val, max_val = min_max(in_real[i-52:i])
            senkou_b.append((min_val + max_val) / 2)

    senkou_a = ([0] * 26) + senkou_a[:-26]
    senkou_b = ([0] * 26) + senkou_b[:-26]
    return tenkan, kijun, senkou_a, senkou_b, chikou


def force_index(close, volume, period):
    force_idx = [0]

    for i in range(1, len(close)):
        force = (close[i] - close[i - 1]) * volume[i]
        force_idx.append(force)
    if period == 1:
        return force_idx
    else:
        ave_force_idx = talib.EMA(np.array(force_idx), period)
        return nan_to_zero(ave_force_idx).tolist()

