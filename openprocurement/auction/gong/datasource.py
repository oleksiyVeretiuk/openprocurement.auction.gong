# -*- coding: utf-8 -*-
import logging
import json

from urlparse import urljoin
from copy import deepcopy
from yaml import safe_dump as yaml_dump
from zope.interface import (
    Interface,
    implementer,
    Attribute
)
from requests import Session as RequestsSession

from openprocurement.auction.utils import (
    generate_request_id,
    get_tender_data,
    make_request,
    get_latest_bid_for_bidder
)
from openprocurement.auction.gong.utils import (
    get_active_bids,
    open_bidders_name
)
from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_API_APPROVED_DATA,
    AUCTION_WORKER_API_AUCTION_RESULT_NOT_APPROVED,
    AUCTION_WORKER_API_AUDIT_LOG_APPROVED,
    AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED,
)


LOGGER = logging.getLogger("Auction Worker")


class IDataSource(Interface):
    """
    Interface for objects that responsible for with external source of data
    """
    post_result = Attribute('Bool parameter that point if we need to post result of auction to external source')
    post_history_document = Attribute(
        'Bool parameter that point if we need to post audit(yaml document with history of auction) '
        'of auction to external source'
    )

    def get_data(self, public=True, with_credentials=False):
        raise NotImplementedError

    def update_source_object(self, external_data, db_document, history_data):
        """
        :argument external_data
        :argument db_document dict that is related to db
        :argument history_data dictinary with history of auction
        To succesfully change data in db this method must return True otherwise there is no data will be
        saved in db. If you need to change db after something was posted you should return copy of db_document object
        with changes that need to be saved in db.
        """
        raise NotImplementedError

    def upload_auction_history_document(self, external_data, db_document, history_data):
        raise NotImplementedError


@implementer(IDataSource)
class FileDataSource(object):
    """
    This class is responsible for working with file datasource
    :parameter path: path to folder where should be file with auction data and where will be saved document of auction history
    :parameter file_name: name of file which will be used to get and update auction data
    """
    path = ''
    file_name = ''
    post_result = False
    post_history_document = False

    def __init__(self, config):
        self.path = config['path'] if config['path'].endswith('/') else config['path'] + '/'
        self.file_name = 'auction_' + config['auction_id'] + '.json'

    def get_data(self, public=True, with_credentials=False):
        with open(self.path + self.file_name, 'r') as f:
            auction_data = json.load(f)
            return auction_data

    def update_source_object(self, external_data, db_document, history_data):
        return True

    def upload_auction_history_document(self, data):
        raise NotImplementedError


@implementer(IDataSource)
class OpenProcurementAPIDataSource(object):
    """
    This class is responsible for working with openprocurement.api
    :parameter source_id: id under which auction is saved
    :parameter api_url: url to external api
    :parameter document_service_url: url to document service
    :parameter with_document_service: parameter which point if auction should use DS or not
    :parameter ds_credential credential for working with document service
    """
    source_id = ''
    api_url = ''
    api_token = ''
    with_document_service = False
    document_service_url = ''
    ds_credential = {
        'username': '',
        'password': ''
    }
    post_result = True
    post_history_document = True

    def __init__(self, config):
        self.api_url = urljoin(
            config['resource_api_server'],
            '/api/{0}/{1}/{2}'.format(
                config['resource_api_version'],
                config['resource_name'],
                config['auction_id']
            )
        )

        self.api_token = config["resource_api_token"]

        self.with_document_service = self.worker_defaults.get('with_document_service', False)
        self.session = RequestsSession()
        if self.worker_defaults.get('with_document_service', False):
            self.session_ds = RequestsSession()

    def get_data(self, public=True, with_credentials=False):
        request_id = generate_request_id()

        if not public:
            auction_data = get_tender_data(
                self.api_url + '/auction',
                user=self.api_token,
                request_id=request_id,
                session=self.session
            )
            return auction_data
        else:
            credentials = self.api_token if with_credentials else ''
            auction_data = get_tender_data(
                self.api_url,
                request_id=request_id,
                user=credentials,
                session=self.session
            )

        return auction_data

    def update_source_object(self, external_data, db_document, history_data):
        """
        :param external_data: data that has been gotten from api
        :param db_document:  data that has been gotten from auction module db
        :param history_data: audit of auction
        :return:
        """
        request_id = generate_request_id()

        doc_id = self.upload_auction_history_document(history_data)

        results = self._post_results_data(external_data, db_document)

        if results:
            bids_information = get_active_bids(results)
            new_db_document = open_bidders_name(db_document, bids_information)

            if doc_id and bids_information:
                self.upload_auction_history_document(history_data, doc_id)
                return new_db_document
        else:
            LOGGER.info(
                "Auctions results not approved",
                extra={"JOURNAL_REQUEST_ID": request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUCTION_RESULT_NOT_APPROVED}
            )

    def _post_results_data(self, external_data, db_document):
        """
        :param auction_data: data from api
        :param auction_document: data from auction module couchdb
        :return: response from api where data is posted
        """
        request_id = generate_request_id()
        result_bids = deepcopy(db_document["results"])
        posted_result_data = deepcopy(external_data["data"]["bids"])

        for index, bid_info in enumerate(external_data["data"]["bids"]):
            if bid_info.get('status', 'active') == 'active':
                auction_bid_info = get_latest_bid_for_bidder(result_bids, bid_info["id"])
                posted_result_data[index]["value"]["amount"] = auction_bid_info["amount"]
                posted_result_data[index]["date"] = auction_bid_info["time"]

        data = {'data': {'bids': posted_result_data}}
        LOGGER.info(
            "Approved data: {}".format(data),
            extra={"JOURNAL_REQUEST_ID": request_id,
                   "MESSAGE_ID": AUCTION_WORKER_API_APPROVED_DATA}
        )
        return make_request(
            self.api_url + '/auction', data=data,
            user=self.api_token,
            method='post',
            request_id=request_id, session=self.session
        )

    def upload_auction_history_document(self, history_data, doc_id=None):
        if self.with_document_service:
            doc_id = self._upload_audit_file_with_document_service(history_data, doc_id)
        else:
            doc_id = self._upload_audit_file_without_document_service(history_data, doc_id)
        return doc_id

    def _upload_audit_file_with_document_service(self, history_data, doc_id=None):
        request_id = generate_request_id()
        files = {'file': ('audit_{}.yaml'.format(self.source_id),
                          yaml_dump(history_data, default_flow_style=False))}
        ds_response = make_request(self.document_service_url,
                                   files=files, method='post',
                                   user=self.ds_credential["username"],
                                   password=self.ds_credential["password"],
                                   session=self.session_ds, retry_count=3)

        if doc_id:
            method = 'put'
            path = self.api_url + '/documents/{}'.format(doc_id)
        else:
            method = 'post'
            path = self.api_url + '/documents'

        response = make_request(path, data=ds_response,
                                user=self.api_token,
                                method=method, request_id=request_id, session=self.session,
                                retry_count=2
                                )
        if response:
            doc_id = response["data"]['id']
            LOGGER.info(
                "Audit log approved. Document id: {}".format(doc_id),
                extra={"JOURNAL_REQUEST_ID": request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_APPROVED}
            )
            return doc_id
        else:
            LOGGER.warning(
                "Audit log not approved.",
                extra={"JOURNAL_REQUEST_ID": request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED})

    def _upload_audit_file_without_document_service(self, history_data, doc_id=None):
        request_id = generate_request_id()
        files = {'file': ('audit_{}.yaml'.format(self.source_id),
                          yaml_dump(history_data, default_flow_style=False))}
        if doc_id:
            method = 'put'
            path = self.api_url + '/documents/{}'.format(doc_id)
        else:
            method = 'post'
            path = self.api_url + '/documents'

        response = make_request(path, files=files,
                                user=self.api_token,
                                method=method, request_id=request_id, session=self.session,
                                retry_count=2
                                )
        if response:
            doc_id = response["data"]['id']
            LOGGER.info(
                "Audit log approved. Document id: {}".format(doc_id),
                extra={"JOURNAL_REQUEST_ID": request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_APPROVED}
            )
            return doc_id
        else:
            LOGGER.warning(
                "Audit log not approved.",
                extra={"JOURNAL_REQUEST_ID": request_id,
                       "MESSAGE_ID": AUCTION_WORKER_API_AUDIT_LOG_NOT_APPROVED})


DATASOURCE_MAPPING = {
    'file': FileDataSource,
    'openprocurement.api': OpenProcurementAPIDataSource
}


def prepare_datasource(config):
    datasource_type = config.get('type')
    datasource_class = DATASOURCE_MAPPING.get(datasource_type, None)

    if datasource_class is None:
        raise AttributeError(
            'There is no datasource for such type {}. Available types {}'.format(
                datasource_type,
                DATASOURCE_MAPPING.keys()
            )
        )

    datasource = datasource_class(config)
    return datasource
