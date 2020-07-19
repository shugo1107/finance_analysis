from datetime import datetime
import logging
import math

import constants

logger = logging.getLogger(__name__)


class Balance(object):
    def __init__(self, currency, available):
        self.currency = currency
        self.available = available


class Ticker(object):
    def __init__(self, product_code, timestamp, bid, ask, volume):
        self.product_code = product_code
        self.timestamp = timestamp
        self.bid = bid
        self.ask = ask
        self.volume = volume

    @property
    def mid_price(self):
        return (self.bid + self.ask) / 2

    @property
    def time(self):
        return datetime.utcfromtimestamp(self.timestamp)

    def truncate_date_time(self, duration):
        ticker_time = self.time
        if duration == constants.DURATION_5S:
            new_sec = math.floor(self.time.second / 5) * 5
            ticker_time = datetime(
                self.time.year, self.time.month, self.time.day,
                self.time.hour, self.time.minute, new_sec
            )
            time_format = '%Y-%m-%d %H:%M:%S'
        elif duration == constants.DURATION_1M:
            time_format = '%Y-%m-%d %H:%M'
        elif duration == constants.DURATION_5M:
            new_min = math.floor(self.time.minute / 5) * 5
            ticker_time = datetime(
                self.time.year, self.time.month, self.time.day,
                self.time.hour, new_min
            )
            time_format = '%Y-%m-%d %H:%M'
        elif duration == constants.DURATION_15M:
            new_min = math.floor(self.time.minute / 15) * 15
            ticker_time = datetime(
                self.time.year, self.time.month, self.time.day,
                self.time.hour, new_min
            )
            time_format = '%Y-%m-%d %H:%M'
        elif duration == constants.DURATION_30M:
            new_min = math.floor(self.time.minute / 30) * 30
            ticker_time = datetime(
                self.time.year, self.time.month, self.time.day,
                self.time.hour, new_min
            )
            time_format = '%Y-%m-%d %H:%M'
        elif duration == constants.DURATION_1H:
            time_format = '%Y-%m-%d %H'
        elif duration == constants.DURATION_1D:
            time_format = '%Y-%m-%d'
        else:
            logger.warning('action=truncate_date_time error=no_datetime_format')
            return None

        str_date = datetime.strftime(ticker_time, time_format)
        return datetime.strptime(str_date, time_format)


class Order(object):
    def __init__(self, product_code, side, units, price=None, order_type='MARKET',
                 order_state=None, filling_transaction_id=None):
        self.product_code = product_code
        self.side = side
        self.units = units
        self.price = price
        self.order_type = order_type
        self.order_state = order_state
        self.filling_transactionid = filling_transaction_id


class OrderTimeoutError(Exception):
    """Order timeout error"""


class Trade(object):
    def __init__(self, trade_id, side, price, units):
        self.trade_id = trade_id
        self.side = side
        self.price = price
        self.units = units
