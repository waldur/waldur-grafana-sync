import logging
from time import sleep

from sync import Sync

logging.getLogger('requests').setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(filename)s:%(lineno)d %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)


if __name__ == '__main__':
    while True:
        try:
            sync = Sync()
            logger.info('Start of Grafana sync.')
            sync.run()
            logger.info('End of Grafana sync.')

        except Exception as e:
            logger.exception(f'Grafana synchronization error. Message: {e}.')

        sleep(float(60 * 5))
