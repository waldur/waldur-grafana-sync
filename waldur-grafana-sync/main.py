from time import sleep
import logging

from sync import Sync

logging.getLogger("requests").setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(filename)s:%(lineno)d %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    while True:
        try:
            sync = Sync()
            logger.info(f'Start of Grafana sync.')
            sync.run()
            logger.info(f'End of Grafana sync.')

        except Exception as e:
            logger.exception(f"Grafana synchronization error. Message: {e}.")

        sleep(float(60 * 5))
