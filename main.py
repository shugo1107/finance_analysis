import logging
import sys
from threading import Thread

from app.controllers.streamdata import StreamData
from app.controllers.webserver import start
import settings

from app.models.dfcandle import DataFrameCandle


# logging.basicConfig(filename='logfile/logger.log', level=logging.INFO)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)


if __name__ == "__main__":
    stream = StreamData(client=settings.client)
    streamThread = Thread(target=stream.stream_ingestion_data)
    serverThread = Thread(target=start)

    streamThread.start()
    serverThread.start()

    streamThread.join()
    serverThread.join()
