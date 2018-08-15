import logging
import sys

from datetime import timedelta
from yaml import safe_dump as yaml_dump
from copy import deepcopy

from urlparse import urljoin
from datetime import datetime
from couchdb import Database, Session

from gevent.event import Event
from gevent.lock import BoundedSemaphore

from requests import Session as RequestsSession
from dateutil.tz import tzlocal
from apscheduler.schedulers.gevent import GeventScheduler

from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_SERVICE_AUCTION_RESCHEDULE,
    AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND,
    AUCTION_WORKER_SERVICE_AUCTION_STATUS_CANCELED,
    AUCTION_WORKER_SERVICE_AUCTION_CANCELED,
    AUCTION_WORKER_SERVICE_END_AUCTION,
    AUCTION_WORKER_SERVICE_STOP_AUCTION_WORKER,
    AUCTION_WORKER_SERVICE_END_FIRST_PAUSE,
    AUCTION_WORKER_API_AUCTION_CANCEL,
    AUCTION_WORKER_API_AUCTION_NOT_EXIST,
    AUCTION_WORKER_SERVICE_START_NEXT_STAGE
)
from openprocurement.auction.executor import AuctionsExecutor
from openprocurement.auction.utils import (
    get_tender_data,
    delete_mapping
)
from openprocurement.auction.worker_core.constants import TIMEZONE
from openprocurement.auction.gong.mixins import\
    DBServiceMixin,\
    BiddersServiceMixin, AuctionAPIServiceMixin,\
    StagesServiceMixin
from openprocurement.auction.worker_core.mixins import (
    RequestIDServiceMixin,
    DateTimeServiceMixin
)
from openprocurement.auction.gong.utils import (
    get_result_info,
    set_result_info,
    update_auction_document,
    prepare_audit,
    lock_bids
)
from openprocurement.auction.gong.server import run_server
from openprocurement.auction.gong.constants import (
    MULTILINGUAL_FIELDS,
    ADDITIONAL_LANGUAGES,
    PRESTARTED,
    END,
    DEADLINE_HOUR,
    ROUND_DURATION
)


LOGGER = logging.getLogger('Auction Worker')
SCHEDULER = GeventScheduler(job_defaults={"misfire_grace_time": 100},
                            executors={'default': AuctionsExecutor()},
                            logger=LOGGER)
SCHEDULER.timezone = TIMEZONE


class Auction(DBServiceMixin,
              RequestIDServiceMixin,
              BiddersServiceMixin,
              DateTimeServiceMixin,
              StagesServiceMixin,
              AuctionAPIServiceMixin):
    """Auction Worker Class"""

    def __init__(self, tender_id,
                 worker_defaults={},
                 auction_data={},
                 ):
        super(Auction, self).__init__()
        self.generate_request_id()
        self.tender_id = tender_id
        self.auction_doc_id = tender_id
        self.tender_url = urljoin(
            worker_defaults["resource_api_server"],
            '/api/{0}/{1}/{2}'.format(
                worker_defaults["resource_api_version"],
                worker_defaults["resource_name"],
                tender_id
            )
        )
        if auction_data:
            self.debug = True
            LOGGER.setLevel(logging.DEBUG)
            self._auction_data = auction_data
        else:
            self.debug = False
        self._end_auction_event = Event()
        self.bids_actions = BoundedSemaphore()
        self.session = RequestsSession()
        self.worker_defaults = worker_defaults
        if self.worker_defaults.get('with_document_service', False):
            self.session_ds = RequestsSession()
        self._bids_data = {}
        self.db = Database(str(self.worker_defaults["COUCH_DATABASE"]),
                           session=Session(retry_delays=range(10)))
        self.audit = {}
        self.retries = 10
        self.bidders_count = 0
        self.bidders_data = []
        self.mapping = {}
        self.use_api = False

    def add_ending_main_round_job(self, start):
        # Add job that should end auction
        SCHEDULER.add_job(
            self.end_auction,
            'date',
            run_date=start,
            name='End of Auction',
            id='auction:{}'.format(END)
        )

    def add_pause_job(self, start):
        SCHEDULER.add_job(
            self.switch_to_next_stage,
            'date',
            run_date=start,
            name='End of Pause',
            id='auction:pause'
        )

    def switch_to_next_stage(self):
        self.generate_request_id()

        with lock_bids(self):
            self.get_auction_document()
            self.auction_document["current_stage"] += 1
            self.save_auction_document()

        LOGGER.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"]),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_START_NEXT_STAGE}
        )

    def schedule_auction(self):
        with update_auction_document(self):
            if self.debug:
                LOGGER.info("Get _auction_data from auction_document")
                self._auction_data = self.auction_document.get(
                    'test_auction_data', {}
                )
            self.synchronize_auction_info()
            self.audit = prepare_audit()

        # Add job that starts auction server
        SCHEDULER.add_job(
            self.start_auction,
            'date',
            run_date=self.convert_datetime(
                self.auction_document['stages'][0]['start']
            ),
            name="Start of Auction",
            id="auction:start"
        )

        # Add job that switch current_stage to round stage
        self.add_pause_job(self.auction_document['stages'][1]['start'])

        # Add job that end auction
        self.add_ending_main_round_job(self.auction_document['stages'][1]['start'] + timedelta(seconds=ROUND_DURATION))

        self.server = run_server(
            self,
            LOGGER
        )

    def wait_to_end(self):
        self._end_auction_event.wait()
        LOGGER.info("Stop auction worker",
                    extra={"JOURNAL_REQUEST_ID": self.request_id,
                           "MESSAGE_ID": AUCTION_WORKER_SERVICE_STOP_AUCTION_WORKER})

    def start_auction(self):
        self.generate_request_id()
        self.audit['timeline']['auction_start']['time'] = datetime.now(tzlocal()).isoformat()
        LOGGER.info(
            '---------------- Start auction  ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_FIRST_PAUSE}
        )
        self.synchronize_auction_info()
        with lock_bids(self), update_auction_document(self):
            self.auction_document["current_stage"] = 0
            self.auction_document['current_phase'] = PRESTARTED
            LOGGER.info("Switched current stage to {}".format(
                self.auction_document['current_stage']
            ))

    def end_auction(self):
        LOGGER.info(
            '---------------- End auction ----------------',
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_AUCTION}
        )

        LOGGER.debug(
            "Stop server", extra={"JOURNAL_REQUEST_ID": self.request_id}
        )
        if self.server:
            self.server.stop()

        delete_mapping(self.worker_defaults, self.auction_doc_id)
        LOGGER.debug(
            "Clear mapping", extra={"JOURNAL_REQUEST_ID": self.request_id}
        )

        self.auction_document["current_stage"] = len(self.auction_document["stages"]) - 1

        # TODO: work with audit
        LOGGER.info(
            'Audit data: \n {}'.format(yaml_dump(self.audit)),
            extra={"JOURNAL_REQUEST_ID": self.request_id}
        )
        LOGGER.info(self.audit)

        self.auction_document['endDate'] = datetime.now(tzlocal()).isoformat()
        if self.put_auction_data(self._auction_data, self.auction_document):
            self.save_auction_document()

        self._end_auction_event.set()

    def cancel_auction(self):
        self.generate_request_id()
        if self.get_auction_document():
            LOGGER.info("Auction {} canceled".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_CANCELED})
            self.auction_document["current_stage"] = -100
            self.auction_document["endDate"] = datetime.now(tzlocal()).isoformat()
            LOGGER.info("Change auction {} status to 'canceled'".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_STATUS_CANCELED})
            self.save_auction_document()
        else:
            LOGGER.info("Auction {} not found".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND})

    def reschedule_auction(self):
        self.generate_request_id()
        if self.get_auction_document():
            LOGGER.info("Auction {} has not started and will be rescheduled".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_RESCHEDULE})
            self.auction_document["current_stage"] = -101
            self.save_auction_document()
        else:
            LOGGER.info("Auction {} not found".format(self.auction_doc_id),
                        extra={'MESSAGE_ID': AUCTION_WORKER_SERVICE_AUCTION_NOT_FOUND})

    def post_audit(self):
        pass

    def post_announce(self):
        if not self.use_api:
            return

        self.auction_document = self.get_auction_document()

        auction = self.get_auction_data()

        bids_information = get_result_info(auction)
        set_result_info(self.auction_document, bids_information)

        self.generate_request_id()
        self.save_auction_document()

    def prepare_auction_document(self):
        self.generate_request_id()
        public_document = self.get_auction_document()

        self.auction_document = {}
        if public_document:
            self.auction_document = {"_rev": public_document["_rev"]}
        if self.debug:
            self.auction_document['mode'] = 'test'
            self.auction_document['test_auction_data'] = deepcopy(
                self._auction_data
            )

        self.synchronize_auction_info(prepare=True)

        self._prepare_auction_document_data()

        if self.worker_defaults.get('sandbox_mode', False):
            self.auction_document['stages'] = self.prepare_auction_stages(
                self.startDate,
                deepcopy(self.auction_document),
                fast_forward=True
            )
        else:
            self.auction_document['stages'] = self.prepare_auction_stages(
                self.startDate,
                deepcopy(self.auction_document)
            )

        self.save_auction_document()

    def _prepare_auction_document_data(self):
        self.auction_document.update({
            "_id": self.auction_doc_id,
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
                    self.auction_document[lang_key] = self._auction_data["data"][lang_key]
            self.auction_document[key] = self._auction_data["data"].get(
                key, ""
            )

    def synchronize_auction_info(self, prepare=False):
        if self.use_api:
            self._set_auction_data(prepare)

        self._set_start_date()
        self._set_bidders_data()
        self._set_mapping()

    def _set_auction_data(self, prepare=False):
        # Get auction from api and set it to _auction_data
        if not self.debug:
            if prepare:
                self._auction_data = get_tender_data(
                    self.tender_url,
                    request_id=self.request_id,
                    session=self.session
                )
            else:
                self._auction_data = {'data': {}}

            auction_data = get_tender_data(
                self.tender_url + '/auction',
                user=self.worker_defaults["resource_api_token"],
                request_id=self.request_id,
                session=self.session
            )

            if auction_data:
                self._auction_data['data'].update(auction_data['data'])
                self.startDate = self.convert_datetime(
                    self._auction_data['data']['auctionPeriod']['startDate']
                )
                del auction_data
            else:
                self.get_auction_document()
                if self.auction_document:
                    self.auction_document["current_stage"] = -100
                    self.save_auction_document()
                    LOGGER.warning("Cancel auction: {}".format(
                        self.auction_doc_id
                    ), extra={"JOURNAL_REQUEST_ID": self.request_id,
                              "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_CANCEL})
                else:
                    LOGGER.error("Auction {} not exists".format(
                        self.auction_doc_id
                    ), extra={
                        "JOURNAL_REQUEST_ID": self.request_id,
                        "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_NOT_EXIST
                    })
                    self._end_auction_event.set()
                    sys.exit(1)

    def _set_start_date(self):
        self.startDate = self.convert_datetime(
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
            if bid['id'] not in self.mapping:
                self.mapping[self.bidders_data[index]['id']] = len(self.mapping.keys()) + 1
