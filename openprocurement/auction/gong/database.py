# -*- coding: utf-8 -*-
import logging

from copy import deepcopy
from couchdb import Database, Session
from couchdb.http import HTTPError, RETRYABLE_ERRORS

from zope.interface import (
    Interface,
    implementer,
)

from openprocurement.auction.utils import generate_request_id

from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_DB_GET_DOC,
    AUCTION_WORKER_DB_GET_DOC_ERROR, AUCTION_WORKER_DB_GET_DOC_UNHANDLED_ERROR, AUCTION_WORKER_DB_SAVE_DOC,
    AUCTION_WORKER_DB_SAVE_DOC_ERROR, AUCTION_WORKER_DB_SAVE_DOC_UNHANDLED_ERROR)

LOGGER = logging.getLogger("Auction Worker")


class IDatabase(Interface):
    """
    Interface for objects which are responsible for work with database
    """
    def get_auction_document(self, auction_doc_id):
        """
        Retrieve auction document from database using provided identifier

        :param auction_doc_id: identifier of document in database
        :return: auction document object from database
        """
        raise NotImplementedError

    def save_auction_document(self, auction_document, auction_doc_id):
        """
        Save provided auction document to database

        :param auction_document: auction document object
        :param auction_doc_id: identifier of document in database
        :return:
        """
        raise NotImplementedError


@implementer(IDatabase)
class CouchDB(object):
    """
    This class is responsible for work with CouchDB

    Attributes:
        _db: Representation of a database to work with on a CouchDB server
        :type _db: couchdb.Database
        db_request_retries: Number of retries of database requesting in case
                            error occurred during getting or saving document
        :type db_request_retries: int
    """
    _db = None
    db_request_retries = 10

    def __init__(self, config):
        self._db = Database(str(config["COUCH_DATABASE"]),
                            session=Session(retry_delays=range(10)))

    def _update_revision(self, auction_document, auction_doc_id):
        """
        Check if document in couchdb database has same '_rev' field value
        with provided document object. If it differs, change '_rev' field value
        for provided auction document with one from couchdb database

        :param auction_document: auction document object
        :param auction_doc_id: identifier of document in database
        :return:
        """
        public_document = self.get_auction_document(auction_doc_id)
        if public_document.get('_rev') != auction_document['_rev']:
            auction_document["_rev"] = public_document["_rev"]

    def get_auction_document(self, auction_doc_id):
        """
        Retrieve auction document from couchdb database using provided identifier

        :param auction_doc_id: identifier of document in couchdb database
        :return: auction document object from couchdb database
        """
        request_id = generate_request_id()
        retries = self.db_request_retries
        while retries:
            try:
                public_document = self.db.get(auction_doc_id)
                if public_document:
                    LOGGER.info("Get auction document {0[_id]} with rev {0[_rev]}".format(public_document),
                                extra={"JOURNAL_REQUEST_ID": request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB_GET_DOC})
                    return public_document

            except HTTPError, e:
                LOGGER.error("Error while get document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_ERROR})
            except Exception, e:
                errcode = e.args[0]
                if errcode in RETRYABLE_ERRORS:
                    LOGGER.error("Error while get document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_ERROR})
                else:
                    LOGGER.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB_GET_DOC_UNHANDLED_ERROR})
            retries -= 1

    def save_auction_document(self, auction_document, auction_doc_id):
        """
        Save provided auction document to couchdb database

        :param auction_document: auction document object
        :param auction_doc_id: identifier of document in database
        :return:
        """
        request_id = generate_request_id()
        public_document = deepcopy(dict(auction_document))
        retries = self.db_request_retries
        while retries:
            try:
                self._update_revision(public_document, auction_doc_id)
                response = self._db.save(public_document)
                if len(response) == 2:
                    LOGGER.info("Saved auction document {0} with rev {1}".format(*response),
                                extra={"JOURNAL_REQUEST_ID": request_id,
                                       "MESSAGE_ID": AUCTION_WORKER_DB_SAVE_DOC})
                    auction_document['_rev'] = response[1]
                    return response
            except HTTPError, e:
                LOGGER.error("Error while save document: {}".format(e),
                             extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_ERROR})
            except Exception, e:
                errcode = e.args[0]
                if errcode in RETRYABLE_ERRORS:
                    LOGGER.error("Error while save document: {}".format(e),
                                 extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_ERROR})
                else:
                    LOGGER.critical("Unhandled error: {}".format(e),
                                    extra={'MESSAGE_ID': AUCTION_WORKER_DB_SAVE_DOC_UNHANDLED_ERROR})
            if "_rev" in public_document:
                LOGGER.debug("Retry save document changes")
            retries -= 1


DATABASE_MAPPING = {
    'couchdb': CouchDB,
}


def prepare_database(config):
    database_type = config.get('type')
    database_class = DATABASE_MAPPING.get(database_type, None)

    if database_class is None:
        raise AttributeError(
            'There is no database for such type {}. Available types {}'.format(
                database_type,
                DATABASE_MAPPING.keys()
            )
        )

    database = database_class(config)
    return database
