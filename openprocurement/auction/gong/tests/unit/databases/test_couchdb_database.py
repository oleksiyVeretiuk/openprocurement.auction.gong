import unittest
import mock
from copy import deepcopy

from couchdb.http import HTTPError

from openprocurement.auction.gong.database import CouchDB


class TestCouchDBDatabase(unittest.TestCase):
    database_class = CouchDB

    def setUp(self):
        self.config = {
            'COUCH_DATABASE': "http://admin:zaq1xsw2@0.0.0.0:9000/database"
        }


class TestInit(TestCouchDBDatabase):

    def setUp(self):
        super(TestInit, self).setUp()

        self.patch_couchdb_database = mock.patch('openprocurement.auction.gong.database.Database')
        self.patch_request_session = mock.patch('openprocurement.auction.gong.database.Session')

        self.couchdb_database = mock.MagicMock()
        self.mock_couchdb_database = self.patch_couchdb_database.start()
        self.mock_couchdb_database.return_value = self.couchdb_database

        self.request_session = mock.MagicMock()
        self.mocked_request_session = self.patch_request_session.start()
        self.mocked_request_session.return_value = self.request_session

    def tearDown(self):
        self.patch_couchdb_database.stop()
        self.patch_request_session.stop()

    def test_init(self):
        db = self.database_class(self.config)

        self.assertEqual(self.mock_couchdb_database.call_count, 1)
        self.mock_couchdb_database.assert_called_with(self.config['COUCH_DATABASE'], session=self.request_session)

        self.assertEqual(self.mocked_request_session.call_count, 1)
        self.mocked_request_session.assert_called_with(retry_delays=range(10))

        self.assertEqual(db._db, self.couchdb_database)


class TestGetDocument(TestCouchDBDatabase):

    def setUp(self):
        super(TestGetDocument, self).setUp()

        self.patch_couchdb_database = mock.patch('openprocurement.auction.gong.database.Database')
        self.patch_request_session = mock.patch('openprocurement.auction.gong.database.Session')

        self.couchdb_database = mock.MagicMock()
        self.mock_couchdb_database = self.patch_couchdb_database.start()
        self.mock_couchdb_database.return_value = self.couchdb_database

        self.mocked_request_session = self.patch_request_session.start()
        self.mocked_request_session.return_value = mock.MagicMock()

        self.database = self.database_class(self.config)

    def tearDown(self):
        self.patch_couchdb_database.stop()
        self.patch_request_session.stop()

    def test_getting_document(self):
        auction_document = {
            '_id': '1' * 32,
            '_rev': '111'
        }
        self.database._db.get.return_value = auction_document

        doc_id = auction_document['_id']

        doc_from_db = self.database.get_auction_document(doc_id)

        self.assertEqual(auction_document, doc_from_db)

        self.assertEqual(self.database._db.get.call_count, 1)
        self.database._db.get.assert_called_with(doc_id)

    def test_retrying_logic(self):
        auction_document = {
            '_id': '1' * 32,
            '_rev': '111'
        }
        self.database._db.get.side_effect = iter(
            [
                HTTPError,
                auction_document
            ]
        )

        doc_id = auction_document['_id']

        doc_from_db = self.database.get_auction_document(doc_id)

        self.assertEqual(auction_document, doc_from_db)

        self.assertEqual(self.database._db.get.call_count, 2)
        self.database._db.get.assert_called_with(doc_id)

    def test_all_retry_failed(self):
        auction_document = {
            '_id': '1' * 32,
            '_rev': '111'
        }

        self.database._db.get.return_value = HTTPError

        doc_id = auction_document['_id']

        doc_from_db = self.database.get_auction_document(doc_id)

        self.assertEqual(doc_from_db, None)

        self.assertEqual(self.database._db.get.call_count, 10)
        self.database._db.get.assert_called_with(doc_id)


class TestUpdateRevision(TestCouchDBDatabase):

    def setUp(self):
        super(TestUpdateRevision, self).setUp()

        self.patch_couchdb_database = mock.patch('openprocurement.auction.gong.database.Database')
        self.patch_request_session = mock.patch('openprocurement.auction.gong.database.Session')

        self.couchdb_database = mock.MagicMock()
        self.mock_couchdb_database = self.patch_couchdb_database.start()
        self.mock_couchdb_database.return_value = self.couchdb_database

        self.mocked_request_session = self.patch_request_session.start()
        self.mocked_request_session.return_value = mock.MagicMock()

        self.database = self.database_class(self.config)
        self.database.get_auction_document = mock.MagicMock()

        self.new_rev = 'new rev'
        self.database.get_auction_document.return_value = {'_rev': self.new_rev}

    def tearDown(self):
        self.patch_couchdb_database.stop()
        self.patch_request_session.stop()

    def test_update_revision(self):
        auction_document = {'_rev': '111', '_id': '1' * 32}
        doc_id = auction_document['_id']

        self.database._update_revision(auction_document, doc_id)

        self.assertEqual(self.database.get_auction_document.call_count, 1)
        self.database.get_auction_document.assert_called_with(doc_id)

        self.assertEqual(auction_document['_rev'], self.new_rev)


class TestSaveDocument(TestCouchDBDatabase):

    def setUp(self):
        super(TestSaveDocument, self).setUp()

        self.patch_couchdb_database = mock.patch('openprocurement.auction.gong.database.Database')
        self.patch_request_session = mock.patch('openprocurement.auction.gong.database.Session')

        self.couchdb_database = mock.MagicMock()
        self.mock_couchdb_database = self.patch_couchdb_database.start()
        self.mock_couchdb_database.return_value = self.couchdb_database

        self.mocked_request_session = self.patch_request_session.start()
        self.mocked_request_session.return_value = mock.MagicMock()

        self.database = self.database_class(self.config)

        self.database._update_revision = mock.MagicMock()

    def tearDown(self):
        self.patch_couchdb_database.stop()
        self.patch_request_session.stop()

    def test_save_document(self):
        auction_document = {
            '_id': '1' * 32,
            '_rev': '111'
        }
        initial_auction_document = deepcopy(auction_document)
        doc_id = auction_document['_id']

        db_response = [
            {
                '_id': '1' * 32,
            },
            '222'
        ]
        self.database._db.save.return_value = db_response

        response = self.database.save_auction_document(auction_document, doc_id)

        self.assertEqual(db_response, response)

        self.assertEqual(auction_document['_rev'], db_response[1])

        self.assertEqual(self.database._db.save.call_count, 1)
        self.database._db.save.assert_called_with(initial_auction_document)

        self.assertEqual(self.database._update_revision.call_count, 1)
        self.database._update_revision.assert_called_with(initial_auction_document, doc_id)

    def test_retrying_logic(self):
        auction_document = {
            '_id': '1' * 32,
            '_rev': '111'
        }
        initial_auction_document = deepcopy(auction_document)
        doc_id = auction_document['_id']

        db_response = [
            {
                '_id': '1' * 32,
            },
            '222'
        ]
        self.database._db.save.side_effect = iter([
            HTTPError,
            db_response
        ]
        )

        response = self.database.save_auction_document(auction_document, doc_id)

        self.assertEqual(db_response, response)

        self.assertEqual(auction_document['_rev'], db_response[1])

        self.assertEqual(self.database._db.save.call_count, 2)
        self.database._db.save.assert_called_with(initial_auction_document)

        self.assertEqual(self.database._update_revision.call_count, 2)
        self.database._update_revision.assert_called_with(initial_auction_document, doc_id)

    def test_all_retry_failed(self):
        auction_document = {
            '_id': '1' * 32,
            '_rev': '111'
        }
        doc_id = auction_document['_id']

        self.database._db.save.return_value = HTTPError

        doc_from_db = self.database.save_auction_document(deepcopy(auction_document), doc_id)

        self.assertEqual(doc_from_db, None)

        self.assertEqual(self.database._db.save.call_count, 10)
        self.database._db.save.assert_called_with(auction_document)

        self.assertEqual(self.database._update_revision.call_count, 10)
        self.database._update_revision.assert_called_with(auction_document, doc_id)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestInit))
    suite.addTest(unittest.makeSuite(TestGetDocument))
    suite.addTest(unittest.makeSuite(TestUpdateRevision))
    suite.addTest(unittest.makeSuite(TestSaveDocument))
    return suite
