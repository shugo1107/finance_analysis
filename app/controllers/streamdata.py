import datetime
from functools import partial
import logging
from threading import Lock
from threading import Thread
import time

from app.controllers.ai import AI
from app.models.candle import create_candle_with_duration
from platforms import Ticker

import constants
import settings

logger = logging.getLogger(__name__)


class StreamData(object):

    def __init__(self, client="oanda"):
        if client == "oanda":
            self.ai = AI(
                product_code=settings.product_code,
                use_percent=settings.use_percent,
                duration=settings.trade_duration,
                past_period=settings.past_period,
                stop_limit_percent=settings.stop_limit_percent,
                back_test=settings.back_test,
                live_practice=settings.live_practice,
                client="oanda")
        elif client == "bitflyer":
            self.ai = AI(
                product_code=settings.product_code,
                use_percent=settings.use_percent,
                duration=settings.trade_duration,
                past_period=settings.past_period,
                stop_limit_percent=settings.stop_limit_percent,
                back_test=settings.back_test,
                live_practice=settings.live_practice,
                client="bitflyer")
        self.trade_lock = Lock()
        # self.trade_duration = settings.trade_duration
        # self.change_time = None

    def stream_ingestion_data(self):
        trade_with_ai = partial(self.trade, ai=self.ai)
        self.ai.API.get_realtime_ticker(callback=trade_with_ai)

    def trade(self, ticker: Ticker, ai: AI):
        logger.info(f'action=trade ticker={ticker.__dict__}')
        for duration in constants.DURATIONS:
            is_created = create_candle_with_duration(ticker.product_code, duration, ticker)
            # if true_range > 2 * atr and self.trade_duration == "15m":
            #     self.trade_duration = "5m"
            #     self.change_time = time.time()
            # elif true_range > 2 * atr and self.trade_duration == "5m":
            #     self.trade_duration = "1m"
            #     self.change_time = time.time()
            # if self.trade_duration == "1m" and time.time() - self.change_time > 840:
            #     self.trade_duration = "5m"
            #     self.change_time = time.time()
            # elif self.trade_duration == "5m" and time.time() - self.change_time > 3200:
            #     self.trade_duration = "15m"
            if is_created and duration == settings.trade_duration:
                thread = Thread(target=self._trade, args=(ai, ticker,))
                thread.start()

    def _trade(self, ai: AI, ticker: Ticker):
        with self.trade_lock:
            ai.trade(ticker.product_code)


# singleton
# stream = StreamData()
