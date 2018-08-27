# -*- coding: utf-8 -*-
import logging
from datetime import datetime
from copy import deepcopy
from yaml import safe_dump as yaml_dump

from zope.interface import (
    Interface,
    implementer,
)
from zope.component import getGlobalSiteManager as gsm

from apscheduler.schedulers.gevent import GeventScheduler
from openprocurement.auction.worker_core.constants import TIMEZONE
from openprocurement.auction.executor import AuctionsExecutor
from openprocurement.auction.utils import (
    generate_request_id,
    delete_mapping
)
from openprocurement.auction.gong.constants import (
    END
)
from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_SERVICE_START_NEXT_STAGE,
    AUCTION_WORKER_SERVICE_END_AUCTION
)
from openprocurement.auction.gong.context import IContext
from openprocurement.auction.gong.database import IDatabase
from openprocurement.auction.gong.datasource import IDataSource
from openprocurement.auction.gong.utils import (
    lock_server,
    update_auction_document,
    prepare_end_stage
)

LOGGER = logging.getLogger('Auction Worker')

SCHEDULER = GeventScheduler(job_defaults={"misfire_grace_time": 100},
                            executors={'default': AuctionsExecutor()},
                            logger=LOGGER)
SCHEDULER.timezone = TIMEZONE


class IJobService(Interface):
    pass


@implementer(IJobService)
class JobService(object):

    def __init__(self):
        self.context = gsm.queryUtility(IContext)
        self.database = gsm.queryUtility(IDatabase)
        self.datasource = gsm.queryUtility(IDataSource)

    def add_pause_job(self, job_start_date):
        SCHEDULER.add_job(
            self.end_auction,
            'date',
            run_date=job_start_date,
            name='End of Auction',
            id='auction:{}'.format(END)
        )

    def add_ending_main_round_job(self, job_start_date):
        SCHEDULER.add_job(
            self.switch_to_next_stage,
            'date',
            run_date=job_start_date,
            name='End of Pause',
            id='auction:pause'
        )

    def switch_to_next_stage(self):
        request_id = generate_request_id()

        with lock_server(self.context['server_actions']):
            with update_auction_document(self.context, self.database) as auction_document:
                auction_document["current_stage"] += 1

        LOGGER.info('---------------- Start stage {0} ----------------'.format(
            self.context['auction_document']["current_stage"]),
            extra={"JOURNAL_REQUEST_ID": request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_START_NEXT_STAGE}
        )

    def end_auction(self):
        request_id = generate_request_id()
        LOGGER.info(
            '---------------- End auction ----------------',
            extra={"JOURNAL_REQUEST_ID": request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_AUCTION}
        )

        LOGGER.debug(
            "Stop server", extra={"JOURNAL_REQUEST_ID": request_id}
        )
        if self.context.get('server'):
            self.context['server'].stop()

        delete_mapping(self.context['worker_defaults'], self.context['auction_do_id'])
        LOGGER.debug(
            "Clear mapping", extra={"JOURNAL_REQUEST_ID": request_id}
        )

        auction_end = datetime.now(TIMEZONE)
        stage = prepare_end_stage(auction_end)
        auction_document = deepcopy(self.context['auction_document'])
        auction_document["stages"].append(stage)
        auction_document["current_stage"] = len(self.context['auction_document']["stages"]) - 1

        # TODO: work with audit
        LOGGER.info(
            'Audit data: \n {}'.format(yaml_dump(self.audit)),
            extra={"JOURNAL_REQUEST_ID": request_id}
        )
        LOGGER.info(self.audit)

        auction_document['endDate'] = auction_end.isoformat()
        result = self.datasource.update_source_object(self._auction_data, auction_document, self.audit)
        if result:
            if isinstance(result, dict):
                self.context['auction_document'] = result
            self.database.save_auction_document(self.context['auction_document'], self.context['auction_doc_id'])

        self.context['end_auction_event'].set()
