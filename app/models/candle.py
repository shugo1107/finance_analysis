from _datetime import datetime
import logging

from sqlalchemy import Column
from sqlalchemy import desc
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy.exc import IntegrityError

from app.models.base import Base
from app.models.base import session_scope

import constants
import settings


logger = logging.getLogger(__name__)


class BaseCandleMixin(object):
    time = Column(DateTime, primary_key=True, nullable=False)
    open = Column(Float)
    close = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Integer)

    @classmethod
    def create(cls, time, open, close, high, low, volume):
        candle = cls(time=time,
                     open=open,
                     close=close,
                     high=high,
                     low=low,
                     volume=volume)
        try:
            with session_scope() as session:
                session.add(candle)
            return candle
        except IntegrityError:
            return False

    @classmethod
    def get(cls, time):
        with session_scope() as session:
            candle = session.query(cls).filter(
                cls.time == time).first()
        if candle is None:
            return None
        return candle

    def save(self):
        with session_scope() as session:
            session.add(self)

    @classmethod
    def get_all_candles(cls, limit=100):
        with session_scope() as session:
            candles = session.query(cls).order_by(
                desc(cls.time)).limit(limit).all()

        if candles is None:
            return None

        candles.reverse()
        return candles

    @classmethod
    def get_fraction_candle(cls, product_code=settings.product_code):
        recent_time = cls.get_all_candles(limit=1)[0].time
        with session_scope() as session:
            table = factory_candle_class(
                product_code=product_code, duration=constants.DURATION_5S)
            candles = session.query(table).filter(
                table.time >= recent_time).order_by(desc(table.time)).all()

        if candles is None:
            return None

        time = candles[0].time
        high = candles[0].high
        low = candles[0].low
        close = candles[0].close
        open = candles[-1].open
        volume = 0
        for i in range(len(candles)):
            high = max(candles[i].high, high)
            low = min(candles[i].low, low)
            volume += candles[i].volume

        candle = cls(time=time,
                     open=open,
                     close=close,
                     high=high,
                     low=low,
                     volume=volume)
        return candle

    # @classmethod
    # def get_atr(cls):
    #     candles = cls.get_all_candles(15)
    #     range_sum = 0
    #     for i in range(1, len(candles)):
    #         range_sum += max(candles[i - 1].close, candles[i].high) - min(candles[i - 1].close, candles[i].low)
    #     true_range = range_sum / (len(candles) - 1)
    #
    #     return true_range

    @property
    def value(self):
        return {
            'time': self.time,
            'open': self.open,
            'close': self.close,
            'high': self.high,
            'low': self.low,
            'volume': self.volume,
        }


class UsdJpyBaseCandle1D(BaseCandleMixin, Base):
    __tablename__ = 'USD_JPY_1D'


class UsdJpyBaseCandle1H(BaseCandleMixin, Base):
    __tablename__ = 'USD_JPY_1H'


class UsdJpyBaseCandle30M(BaseCandleMixin, Base):
    __tablename__ = 'USD_JPY_30M'


class UsdJpyBaseCandle15M(BaseCandleMixin, Base):
    __tablename__ = 'USD_JPY_15M'


class UsdJpyBaseCandle5M(BaseCandleMixin, Base):
    __tablename__ = 'USD_JPY_5M'


class UsdJpyBaseCandle1M(BaseCandleMixin, Base):
    __tablename__ = 'USD_JPY_1M'


class UsdJpyBaseCandle5S(BaseCandleMixin, Base):
    __tablename__ = 'USD_JPY_5S'


class EurJpyBaseCandle1D(BaseCandleMixin, Base):
    __tablename__ = 'EUR_JPY_1D'


class EurJpyBaseCandle1H(BaseCandleMixin, Base):
    __tablename__ = 'EUR_JPY_1H'


class EurJpyBaseCandle30M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_JPY_30M'


class EurJpyBaseCandle15M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_JPY_15M'


class EurJpyBaseCandle5M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_JPY_5M'


class EurJpyBaseCandle1M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_JPY_1M'


class EurJpyBaseCandle5S(BaseCandleMixin, Base):
    __tablename__ = 'EUR_JPY_5S'


class EurUsdBaseCandle1D(BaseCandleMixin, Base):
    __tablename__ = 'EUR_USD_1D'


class EurUsdBaseCandle1H(BaseCandleMixin, Base):
    __tablename__ = 'EUR_USD_1H'


class EurUsdBaseCandle30M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_USD_30M'


class EurUsdBaseCandle15M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_USD_15M'


class EurUsdBaseCandle5M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_USD_5M'


class EurUsdBaseCandle1M(BaseCandleMixin, Base):
    __tablename__ = 'EUR_USD_1M'


class EurUsdBaseCandle5S(BaseCandleMixin, Base):
    __tablename__ = 'EUR_USD_5S'


class GbpJpyBaseCandle1D(BaseCandleMixin, Base):
    __tablename__ = 'GBP_JPY_1D'


class GbpJpyBaseCandle1H(BaseCandleMixin, Base):
    __tablename__ = 'GBP_JPY_1H'


class GbpJpyBaseCandle30M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_JPY_30M'


class GbpJpyBaseCandle15M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_JPY_15M'


class GbpJpyBaseCandle5M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_JPY_5M'


class GbpJpyBaseCandle1M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_JPY_1M'


class GbpJpyBaseCandle5S(BaseCandleMixin, Base):
    __tablename__ = 'GBP_JPY_5S'


class GbpUsdBaseCandle1D(BaseCandleMixin, Base):
    __tablename__ = 'GBP_USD_1D'


class GbpUsdBaseCandle1H(BaseCandleMixin, Base):
    __tablename__ = 'GBP_USD_1H'


class GbpUsdBaseCandle30M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_USD_30M'


class GbpUsdBaseCandle15M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_USD_15M'


class GbpUsdBaseCandle5M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_USD_5M'


class GbpUsdBaseCandle1M(BaseCandleMixin, Base):
    __tablename__ = 'GBP_USD_1M'


class GbpUsdBaseCandle5S(BaseCandleMixin, Base):
    __tablename__ = 'GBP_USD_5S'


class AudJpyBaseCandle1D(BaseCandleMixin, Base):
    __tablename__ = 'AUD_JPY_1D'


class AudJpyBaseCandle1H(BaseCandleMixin, Base):
    __tablename__ = 'AUD_JPY_1H'


class AudJpyBaseCandle30M(BaseCandleMixin, Base):
    __tablename__ = 'AUD_JPY_30M'


class AudJpyBaseCandle15M(BaseCandleMixin, Base):
    __tablename__ = 'AUD_JPY_15M'


class AudJpyBaseCandle5M(BaseCandleMixin, Base):
    __tablename__ = 'AUD_JPY_5M'


class AudJpyBaseCandle1M(BaseCandleMixin, Base):
    __tablename__ = 'AUD_JPY_1M'


class AudJpyBaseCandle5S(BaseCandleMixin, Base):
    __tablename__ = 'AUD_JPY_5S'


class FxBtcJpyBaseCandle1D(BaseCandleMixin, Base):
    __tablename__ = 'FX_BTC_JPY_1D'


class FxBtcJpyBaseCandle1H(BaseCandleMixin, Base):
    __tablename__ = 'FX_BTC_JPY_1H'


class FxBtcJpyBaseCandle30M(BaseCandleMixin, Base):
    __tablename__ = 'FX_BTC_JPY_30M'


class FxBtcJpyBaseCandle15M(BaseCandleMixin, Base):
    __tablename__ = 'FX_BTC_JPY_15M'


class FxBtcJpyBaseCandle5M(BaseCandleMixin, Base):
    __tablename__ = 'FX_BTC_JPY_5M'


class FxBtcJpyBaseCandle1M(BaseCandleMixin, Base):
    __tablename__ = 'FX_BTC_JPY_1M'


class FxBtcJpyBaseCandle5S(BaseCandleMixin, Base):
    __tablename__ = 'FX_BTC_JPY_5S'


def factory_candle_class(product_code, duration):
    if product_code == constants.PRODUCT_CODE_USD_JPY:
        if duration == constants.DURATION_5S:
            return UsdJpyBaseCandle5S
        if duration == constants.DURATION_1M:
            return UsdJpyBaseCandle1M
        if duration == constants.DURATION_5M:
            return UsdJpyBaseCandle5M
        if duration == constants.DURATION_15M:
            return UsdJpyBaseCandle15M
        if duration == constants.DURATION_30M:
            return UsdJpyBaseCandle30M
        if duration == constants.DURATION_1H:
            return UsdJpyBaseCandle1H
        if duration == constants.DURATION_1D:
            return UsdJpyBaseCandle1D

    if product_code == constants.PRODUCT_CODE_EUR_JPY:
        if duration == constants.DURATION_5S:
            return EurJpyBaseCandle5S
        if duration == constants.DURATION_1M:
            return EurJpyBaseCandle1M
        if duration == constants.DURATION_5M:
            return EurJpyBaseCandle5M
        if duration == constants.DURATION_15M:
            return EurJpyBaseCandle15M
        if duration == constants.DURATION_30M:
            return EurJpyBaseCandle30M
        if duration == constants.DURATION_1H:
            return EurJpyBaseCandle1H
        if duration == constants.DURATION_1D:
            return EurJpyBaseCandle1D

    if product_code == constants.PRODUCT_CODE_EUR_USD:
        if duration == constants.DURATION_5S:
            return EurUsdBaseCandle5S
        if duration == constants.DURATION_1M:
            return EurUsdBaseCandle1M
        if duration == constants.DURATION_5M:
            return EurUsdBaseCandle5M
        if duration == constants.DURATION_15M:
            return EurUsdBaseCandle15M
        if duration == constants.DURATION_30M:
            return EurUsdBaseCandle30M
        if duration == constants.DURATION_1H:
            return EurUsdBaseCandle1H
        if duration == constants.DURATION_1D:
            return EurUsdBaseCandle1D

    if product_code == constants.PRODUCT_CODE_GBP_JPY:
        if duration == constants.DURATION_5S:
            return GbpJpyBaseCandle5S
        if duration == constants.DURATION_1M:
            return GbpJpyBaseCandle1M
        if duration == constants.DURATION_5M:
            return GbpJpyBaseCandle5M
        if duration == constants.DURATION_15M:
            return GbpJpyBaseCandle15M
        if duration == constants.DURATION_30M:
            return GbpJpyBaseCandle30M
        if duration == constants.DURATION_1H:
            return GbpJpyBaseCandle1H
        if duration == constants.DURATION_1D:
            return GbpJpyBaseCandle1D

    if product_code == constants.PRODUCT_CODE_GBP_USD:
        if duration == constants.DURATION_5S:
            return GbpUsdBaseCandle5S
        if duration == constants.DURATION_1M:
            return GbpUsdBaseCandle1M
        if duration == constants.DURATION_5M:
            return GbpUsdBaseCandle5M
        if duration == constants.DURATION_15M:
            return GbpUsdBaseCandle15M
        if duration == constants.DURATION_30M:
            return GbpUsdBaseCandle30M
        if duration == constants.DURATION_1H:
            return GbpUsdBaseCandle1H
        if duration == constants.DURATION_1D:
            return GbpUsdBaseCandle1D

    if product_code == constants.PRODUCT_CODE_AUD_JPY:
        if duration == constants.DURATION_5S:
            return AudJpyBaseCandle5S
        if duration == constants.DURATION_1M:
            return AudJpyBaseCandle1M
        if duration == constants.DURATION_5M:
            return AudJpyBaseCandle5M
        if duration == constants.DURATION_15M:
            return AudJpyBaseCandle15M
        if duration == constants.DURATION_30M:
            return AudJpyBaseCandle30M
        if duration == constants.DURATION_1H:
            return AudJpyBaseCandle1H
        if duration == constants.DURATION_1D:
            return AudJpyBaseCandle1D

    if product_code == constants.PRODUCT_CODE_FX_BTC_JPY:
        if duration == constants.DURATION_5S:
            return FxBtcJpyBaseCandle5S
        if duration == constants.DURATION_1M:
            return FxBtcJpyBaseCandle1M
        if duration == constants.DURATION_5M:
            return FxBtcJpyBaseCandle5M
        if duration == constants.DURATION_15M:
            return FxBtcJpyBaseCandle15M
        if duration == constants.DURATION_30M:
            return FxBtcJpyBaseCandle30M
        if duration == constants.DURATION_1H:
            return FxBtcJpyBaseCandle1H
        if duration == constants.DURATION_1D:
            return FxBtcJpyBaseCandle1D


def create_candle_with_duration(product_code, duration, ticker):
    cls = factory_candle_class(product_code, duration)
    ticker_time = ticker.truncate_date_time(duration)
    current_candle = cls.get(ticker_time)
    price = ticker.mid_price
    if current_candle is None:
        cls.create(ticker_time, price, price, price, price, ticker.volume)
        return True

    if current_candle.high <= price:
        current_candle.high = price
    elif current_candle.low >= price:
        current_candle.low = price
    current_candle.volume += ticker.volume
    current_candle.close = price
    current_candle.save()
    return False
