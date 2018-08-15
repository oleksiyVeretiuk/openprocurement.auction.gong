import logging
import json
from datetime import timedelta
from copy import deepcopy
from couchdb.http import HTTPError, RETRYABLE_ERRORS

from openprocurement.auction.utils import (
    get_tender_data,
    get_latest_bid_for_bidder,
    make_request
)
from openprocurement.auction.worker_core.utils import prepare_service_stage

from openprocurement.auction.gong.utils import (
    get_result_info,
    set_result_info
)
from openprocurement.auction.gong.constants import (
   BIDS_KEYS_FOR_COPY,
   MAIN_ROUND,
   END,
   AUCTION_DEADLINE,
   ROUND_DURATION,
   PAUSE_DURATION,
)
from openprocurement.auction.worker_core.mixins import (
    RequestIDServiceMixin, AuditServiceMixin
)
from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_DB_GET_DOC,
    AUCTION_WORKER_DB_GET_DOC_ERROR,
    AUCTION_WORKER_DB_GET_DOC_UNHANDLED_ERROR,
    AUCTION_WORKER_DB_SAVE_DOC,
    AUCTION_WORKER_DB_SAVE_DOC_ERROR,
    AUCTION_WORKER_DB_SAVE_DOC_UNHANDLED_ERROR,
    AUCTION_WORKER_API_APPROVED_DATA,
    AUCTION_WORKER_BIDS_LATEST_BID_CANCELLATION,
    AUCTION_WORKER_API_AUCTION_RESULT_NOT_APPROVED,
    AUCTION_WORKER_SERVICE_END_BID_STAGE,
    AUCTION_WORKER_SERVICE_START_STAGE,
    AUCTION_WORKER_SERVICE_START_NEXT_STAGE,
)


LOGGER = logging.getLogger("Auction Worker")


class DBServiceMixin(object):
    """ Mixin class to work with couchdb"""
    db_request_retries = 10
    db = None
    auction_document = None
    auction_doc_id = ''

    def get_auction_document(self, force=False):
        self.generate_request_id()
        retries = self.db_request_retries
        while retries:
            try:
                public_document = self.db.get(self.auction_doc_id)
                if public_document:
                    LOGGER.info("Get auction document {0[_id]} with rev {0[_rev]}".format(public_document),
                                extra={"JOURNAL_REQUEST_ID": self.request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB_GET_DOC})
                    if not hasattr(self, 'auction_document'):
                        self.auction_document = public_document
                    if force:
                        return public_document
                    elif public_document['_rev'] != self.auction_document['_rev']:
                        LOGGER.warning("Rev error")
                        self.auction_document["_rev"] = public_document["_rev"]
                    LOGGER.debug(json.dumps(self.auction_document, indent=4))
                return public_document

            except HTTPError, e:
                LOGGER.error("Error while get document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_ERROR})
            except Exception, e:
                ecode = e.args[0]
                if ecode in RETRYABLE_ERRORS:
                    LOGGER.error("Error while get document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_ERROR})
                else:
                    LOGGER.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_UNHANDLED_ERROR})
            retries -= 1

    def save_auction_document(self):
        self.generate_request_id()
        public_document = self.prepare_public_document()
        retries = self.db_request_retries
        while retries:
            try:
                response = self.db.save(public_document)
                if len(response) == 2:
                    LOGGER.info("Saved auction document {0} with rev {1}".format(*response),
                                extra={"JOURNAL_REQUEST_ID": self.request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB_SAVE_DOC})
                    self.auction_document['_rev'] = response[1]
                    return response
            except HTTPError, e:
                LOGGER.error("Error while save document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_ERROR})
            except Exception, e:
                ecode = e.args[0]
                if ecode in RETRYABLE_ERRORS:
                    LOGGER.error("Error while save document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_ERROR})
                else:
                    LOGGER.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_UNHANDLED_ERROR})
            if "_rev" in public_document:
                LOGGER.debug("Retry save document changes")
            saved_auction_document = self.get_auction_document(force=True)
            public_document["_rev"] = saved_auction_document["_rev"]
            retries -= 1

    def prepare_public_document(self):
        public_document = deepcopy(dict(self.auction_document))
        return public_document


class BiddersServiceMixin(object):
    """Mixin class to work with bids data"""
    _bids_data = {}

    def add_bid(self, round_id, bid):
        if round_id not in self._bids_data:
            self._bids_data[round_id] = []
        self._bids_data[round_id].append(bid)

    def filter_bids_keys(self, bids):
        filtered_bids_data = []
        for bid_info in bids:
            bid_info_result = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            bid_info_result["bidder_name"] = self.mapping[bid_info_result['bidder_id']]
            filtered_bids_data.append(bid_info_result)
        return filtered_bids_data

    def approve_bids_information(self):
        pass


class AuctionAPIServiceMixin(
    AuditServiceMixin
):
    auction_doc_id = ''
    with_document_service = False
    tender_url = ''
    api_token = ''
    session = None

    def put_auction_data(self, auction_data, auction_document):
        """
        :param auction_data: data from api
        :param auction_document: data from auction module couchdb
        :return: True if auctions result was successfully patched or None if smth wrong
        """

        if self.with_document_service:
            doc_id = self.upload_audit_file_with_document_service()
        else:
            doc_id = self.upload_audit_file_without_document_service()

        results = self.post_results_data(auction_data)

        if results:
            bids_information = get_result_info(results)
            set_result_info(auction_document, bids_information)

            if doc_id and bids_information:
                self.approve_audit_info_on_announcement(approved=bids_information)
                if self.with_document_service:
                    self.upload_audit_file_with_document_service(doc_id)
                else:
                    self.upload_audit_file_without_document_service(doc_id)

                return True
        else:
            LOGGER.info(
                "Auctions results not approved",
                extra={"JOURNAL_REQUEST_ID": self.request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_RESULT_NOT_APPROVED}
            )

    def post_results_data(self, auction_data, auction_document):
        """
        :param auction_data: data from api
        :param auction_document: data from auction module couchdb
        :return: response from api where data is posted
        """
        result_bids = deepcopy(auction_document["results"])
        posted_result_data = deepcopy(auction_data["data"]["bids"])

        for index, bid_info in enumerate(auction_data["data"]["bids"]):
            if bid_info.get('status', 'active') == 'active':
                auction_bid_info = get_latest_bid_for_bidder(result_bids, bid_info["id"])
                posted_result_data[index]["value"]["amount"] = auction_bid_info["amount"]
                posted_result_data[index]["date"] = auction_bid_info["time"]

        data = {'data': {'bids': posted_result_data}}
        LOGGER.info(
            "Approved data: {}".format(data),
            extra={"JOURNAL_REQUEST_ID": self.request_id,
                   "MESSAGE_ID": AUCTION_WORKER_API_APPROVED_DATA}
        )
        return make_request(
            self.tender_url + '/auction', data=data,
            user=self.api_token,
            method='post',
            request_id=self.request_id, session=self.session
        )

    def get_auction_data(self):
        self.generate_request_id()
        results = get_tender_data(
            self.tender_url,
            user=self.api_token,
            request_id=self.request_id,
            session=self.session
        )

        return results


class StagesServiceMixin(object):

    def prepare_auction_stages(self, stage_start, deadline, auction_data, fast_forward=False):
        stages = [
            prepare_service_stage(start=stage_start.isoformat())
        ]

        stage_start += timedelta(seconds=PAUSE_DURATION)
        stage = {
            'start': stage_start.isoformat(),
            'type': MAIN_ROUND,
            'amount': auction_data['value']['amount'] + auction_data['minimalStep']['amount'],
            'time': ''
        }
        stages.append(stage)
        return stages
