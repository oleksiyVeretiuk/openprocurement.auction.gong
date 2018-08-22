import logging

from apscheduler.schedulers.gevent import GeventScheduler
from openprocurement.auction.worker_core.constants import TIMEZONE
from openprocurement.auction.executor import AuctionsExecutor


LOGGER = logging.getLogger('Auction Worker')

SCHEDULER = GeventScheduler(job_defaults={"misfire_grace_time": 100},
                            executors={'default': AuctionsExecutor()},
                            logger=LOGGER)
SCHEDULER.timezone = TIMEZONE
