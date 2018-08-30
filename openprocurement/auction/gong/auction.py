import logging
import sys
from copy import deepcopy
from datetime import datetime, timedelta

from zope.component.globalregistry import getGlobalSiteManager
from couchdb import Database, Session
from gevent.event import Event
from gevent.lock import BoundedSemaphore

from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_SERVICE_AUCTION_RESCHEDULE,
    AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND,
    AUCTION_WORKER_SERVICE_AUCTION_STATUS_CANCELED,
    AUCTION_WORKER_SERVICE_AUCTION_CANCELED,
    AUCTION_WORKER_SERVICE_STOP_AUCTION_WORKER,
    AUCTION_WORKER_SERVICE_END_FIRST_PAUSE,
    AUCTION_WORKER_API_AUCTION_CANCEL,
    AUCTION_WORKER_API_AUCTION_NOT_EXIST,
)
from openprocurement.auction.utils import (
    delete_mapping,
    generate_request_id
)
from openprocurement.auction.worker_core.constants import TIMEZONE

from openprocurement.auction.gong import utils
from openprocurement.auction.gong.constants import (
    MULTILINGUAL_FIELDS,
    ADDITIONAL_LANGUAGES,
    PRESTARTED,
    DEADLINE_HOUR,
    ROUND_DURATION
)
from openprocurement.auction.gong.context import IContext
from openprocurement.auction.gong.datasource import IDataSource
from openprocurement.auction.gong.database import IDatabase
from openprocurement.auction.gong.scheduler import IJobService
from openprocurement.auction.gong.server import run_server
from openprocurement.auction.gong.scheduler import SCHEDULER

LOGGER = logging.getLogger('Auction Worker Gong')


class Auction(object):
    """Auction Worker Class"""

    def __init__(self, tender_id, worker_defaults={}, debug=False):
        super(Auction, self).__init__()
        self.tender_id = tender_id
        self.debug = debug
        self._end_auction_event = Event()
        self.bids_actions = BoundedSemaphore()
        self.worker_defaults = worker_defaults
        self.db = Database(str(self.worker_defaults["COUCH_DATABASE"]),
                           session=Session(retry_delays=range(10)))
        self.audit = {}
        self.retries = 10
        self.bidders_count = 0
        self.bidders_data = []
        self.bids_mapping = {}

        gsm = getGlobalSiteManager()

        self.datasource = gsm.queryUtility(IDataSource)
        self.database = gsm.queryUtility(IDatabase)
        self.context = gsm.queryUtility(IContext)
        self.job_service = gsm.queryUtility(IJobService)

        self.context['end_auction_event'] = self._end_auction_event

    def schedule_auction(self):
        self.context['auction_document'] = self.database.get_auction_document(
            self.context['auction_doc_id']
        )
        with utils.update_auction_document(self.context, self.database) as auction_document:
            if self.debug:
                LOGGER.info("Get _auction_data from auction_document")
                self._auction_data = auction_document.get(
                    'test_auction_data', {}
                )
            self.synchronize_auction_info()
            self.audit = utils.prepare_audit()
            self.context['audit'] = deepcopy(self.audit)
            self.context['auction_data'] = deepcopy(self._auction_data)
            self.context['bidders_data'] = deepcopy(self.bidders_data)
            self.context['bids_mapping'] = deepcopy(self.bids_mapping)

        # Add job that starts auction server
        SCHEDULER.add_job(
            self.start_auction,
            'date',
            run_date=utils.convert_datetime(
                self.context['auction_document']['stages'][0]['start']
            ),
            name="Start of Auction",
            id="auction:start"
        )

        # Add job that switch current_stage to round stage
        start = utils.convert_datetime(self.context['auction_document']['stages'][1]['start'])
        self.job_service.add_pause_job(start)

        # Add job that end auction
        start = utils.convert_datetime(self.context['auction_document']['stages'][1]['start']) + timedelta(seconds=ROUND_DURATION)
        self.job_service.add_ending_main_round_job(start)

        self.server = run_server(
            self,
            None,  # TODO: add mapping expire
            LOGGER
        )
        self.context['server'] = self.server

    def wait_to_end(self):
        request_id = generate_request_id()

        self._end_auction_event.wait()
        LOGGER.info("Stop auction worker",
                    extra={"JOURNAL_REQUEST_ID": request_id,
                           "MESSAGE_ID": AUCTION_WORKER_SERVICE_STOP_AUCTION_WORKER})

    def start_auction(self):
        request_id = generate_request_id()
        self.audit['timeline']['auction_start']['time'] = datetime.now(TIMEZONE).isoformat()
        self.context['audit'] = deepcopy(self.audit)

        LOGGER.info(
            '---------------- Start auction  ----------------',
            extra={"JOURNAL_REQUEST_ID": request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_FIRST_PAUSE}
        )
        self.synchronize_auction_info()
        with utils.lock_server(self.context['server_actions']), utils.update_auction_document(self.context, self.database) as auction_document:
            auction_document["current_stage"] = 0
            auction_document['current_phase'] = PRESTARTED
            LOGGER.info("Switched current stage to {}".format(
                auction_document['current_stage']
            ))

    def cancel_auction(self):
        self.context['auction_document'] = self.database.get_auction_document(
            self.context['auction_doc_id']
        )
        if self.context['auction_document']:
            with utils.update_auction_document(self.context, self.database) as auction_document:
                LOGGER.info("Auction {} canceled".format(self.context['auction_doc_id']),
                            extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_CANCELED})
                auction_document["current_stage"] = -100
                auction_document["endDate"] = datetime.now(TIMEZONE).isoformat()
                LOGGER.info("Change auction {} status to 'canceled'".format(self.context['auction_doc_id']),
                            extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_STATUS_CANCELED})
        else:
            LOGGER.info("Auction {} not found".format(self.context['auction_doc_id']),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND})

    def reschedule_auction(self):
        self.context['auction_document'] = self.database.get_auction_document(
            self.context['auction_doc_id']
        )
        if self.context['auction_document']:
            with utils.update_auction_document(self.context, self.database) as auction_document:
                LOGGER.info("Auction {} has not started and will be rescheduled".format(self.context['auction_doc_id']),
                            extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_RESCHEDULE})
                auction_document["current_stage"] = -101
                self.database.save_auction_document(auction_document, self.context['auction_doc_id'])
        else:
            LOGGER.info("Auction {} not found".format(self.context['auction_doc_id']),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND})

    def post_audit(self):
        pass

    def post_announce(self):
        self.context['auction_document'] = self.database.get_auction_document(
            self.context['auction_doc_id']
        )
        auction = self.datasource.get_data(with_credentials=True)

        bids_information = utils.get_active_bids(auction)
        with utils.update_auction_document(self.context, self.database) as auction_document:
            utils.open_bidders_name(auction_document, bids_information)

    def prepare_auction_document(self):
        public_document = self.database.get_auction_document(self.context['auction_doc_id'])

        auction_document = {}
        if public_document:
            auction_document = {"_rev": public_document["_rev"]}
        if self.debug:
            auction_document['mode'] = 'test'
            auction_document['test_auction_data'] = deepcopy(
                self._auction_data
            )

        self.synchronize_auction_info(prepare=True)

        self._prepare_auction_document_data(auction_document)

        if self.worker_defaults.get('sandbox_mode', False):
            auction_document['stages'] = utils.prepare_auction_stages(
                self.startDate,
                deepcopy(auction_document),
                fast_forward=True
            )
        else:
            auction_document['stages'] = utils.prepare_auction_stages(
                self.startDate,
                deepcopy(auction_document)
            )
        self.database.save_auction_document(
            auction_document, self.context['auction_doc_id']
        )
        self.datasource.set_participation_urls(self._auction_data)

    def _prepare_auction_document_data(self, auction_document):
        auction_document.update({
            "_id": self.context['auction_doc_id'],
            "stages": [],
            "auctionID": self._auction_data["data"].get("auctionID", ""),
            "procurementMethodType": self._auction_data["data"].get(
                "procurementMethodType", "default"),
            "TENDERS_API_VERSION": self.worker_defaults["resource_api_version"],
            "current_stage": -1,
            "current_phase": "",
            "results": [],
            "procuringEntity": self._auction_data["data"].get(
                "procuringEntity", {}
            ),
            "items": self._auction_data["data"].get("items", []),
            "value": self._auction_data["data"].get("value", {}),
            "minimalStep": self._auction_data["data"].get("minimalStep", {}),
            "initial_value": self._auction_data["data"].get(
                "value", {}
            ).get('amount'),
            "auction_type": "kadastral",
        })

        for key in MULTILINGUAL_FIELDS:
            for lang in ADDITIONAL_LANGUAGES:
                lang_key = "{}_{}".format(key, lang)
                if lang_key in self._auction_data["data"]:
                    auction_document[lang_key] = self._auction_data["data"][lang_key]
            auction_document[key] = self._auction_data["data"].get(key, "")

    def synchronize_auction_info(self, prepare=False):
        self._set_auction_data(prepare)

        self._set_start_date()
        self._set_bidders_data()
        self._set_mapping()

    def _set_auction_data(self, prepare=False):
        # Get auction from api and set it to _auction_data
        request_id = generate_request_id()
        if prepare:
            self._auction_data = self.datasource.get_data()
        else:
            self._auction_data = {'data': {}}

        auction_data = self.datasource.get_data(public=False)

        if auction_data:
            self._auction_data['data'].update(auction_data['data'])
            self.startDate = utils.convert_datetime(
                self._auction_data['data']['auctionPeriod']['startDate']
            )
            del auction_data
        else:
            auction_document = self.database.get_auction_document(self.context['auction_doc_id'])
            if auction_document:
                auction_document["current_stage"] = -100
                self.database.save_auction_document(auction_document, self.context['auction_doc_id'])
                LOGGER.warning("Cancel auction: {}".format(
                    self.context['auction_doc_id']
                ), extra={"JOURNAL_REQUEST_ID": request_id,
                          "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_CANCEL})
            else:
                LOGGER.error("Auction {} not exists".format(
                    self.context['auction_doc_id']
                ), extra={
                    "JOURNAL_REQUEST_ID": request_id,
                    "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_NOT_EXIST
                })
                self._end_auction_event.set()
                sys.exit(1)

    def _set_start_date(self):
        self.startDate = utils.convert_datetime(
            self._auction_data['data'].get('auctionPeriod', {}).get('startDate', '')
        )
        self.deadline_time = datetime(
            self.startDate.year,
            self.startDate.month,
            self.startDate.day,
            DEADLINE_HOUR
        )

    def _set_bidders_data(self):
        self.bidders_data = [
            {
                'id': bid['id'],
                'date': bid['date'],
                'owner': bid.get('owner', '')
            }
            for bid in self._auction_data['data'].get('bids', [])
            if bid.get('status', 'active') == 'active'
        ]

    def _set_mapping(self):
        for index, bid in enumerate(self.bidders_data):
            if bid['id'] not in self.bids_mapping:
                self.bids_mapping[self.bidders_data[index]['id']] = len(self.bids_mapping.keys()) + 1
