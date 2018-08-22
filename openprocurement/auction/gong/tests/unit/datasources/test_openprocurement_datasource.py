import unittest
import mock

from uuid import uuid4

from openprocurement.auction.gong.datasource import OpenProcurementAPIDataSource


class TestOpenProcurementAPIDataSource(unittest.TestCase):
    datasource_class = OpenProcurementAPIDataSource

    def setUp(self):
        self.config = {
            'resource_api_server': 'https://lb.api-sandbox.ea.openprocurement.org/',
            'resource_api_version': '2.4',
            'resource_name': 'auction',
            'auction_id': '1' * 32,
            'resource_api_token': 'api_token',
        }


class TestInit(TestOpenProcurementAPIDataSource):

    def setUp(self):
        super(TestInit, self).setUp()
        self.request_session = mock.MagicMock()

        self.patch_request_session = mock.patch('openprocurement.auction.gong.datasource.RequestsSession')
        self.mocked_request_session = self.patch_request_session.start()
        self.mocked_request_session.return_value = self.request_session

    def tearDown(self):
        self.patch_request_session.stop()

    def test_init_with_docservice(self):
        self.config['with_document_service'] = True
        ds_service_config = {
            'username': 'username',
            'password': 'password',
            'url': 'http://docservice_url'
        }

        self.config['DOCUMENT_SERVICE'] = ds_service_config

        datasource = self.datasource_class(self.config)

        self.assertEqual(datasource.api_token, self.config['resource_api_token'])

        url = '{}api/{}/{}/{}'.format(
            self.config['resource_api_server'],
            self.config['resource_api_version'],
            self.config['resource_name'],
            self.config['auction_id']
        )
        self.assertEqual(datasource.api_url, url)
        self.assertIs(datasource.session, self.request_session)
        self.assertIs(datasource.session_ds, self.request_session)
        self.assertEqual(self.mocked_request_session.call_count, 2)

    def test_init_without_docservice(self):
        self.config['with_document_service'] = False

        datasource = self.datasource_class(self.config)

        self.assertEqual(datasource.api_token, self.config['resource_api_token'])

        url = '{}api/{}/{}/{}'.format(
            self.config['resource_api_server'],
            self.config['resource_api_version'],
            self.config['resource_name'],
            self.config['auction_id']
        )
        self.assertEqual(datasource.api_url, url)
        self.assertIs(datasource.session, self.request_session)
        self.assertIs(hasattr(datasource, 'session_ds'), False)
        self.assertEqual(self.mocked_request_session.call_count, 1)


class TestUpdateSourceObject(TestOpenProcurementAPIDataSource):

    def setUp(self):
        super(TestUpdateSourceObject, self).setUp()
        self.datasource = self.datasource_class(self.config)
        self.external_data = {'external': 'data'}
        self.db_document = {'db': 'document'}
        self.history_document = {'auction': 'protocol'}

        self.request_session = mock.MagicMock()

        self.patch_get_active_bids = mock.patch('openprocurement.auction.gong.datasource.get_active_bids')
        self.patch_open_bidders_name = mock.patch('openprocurement.auction.gong.datasource.open_bidders_name')

        self.patch_upload_history = mock.patch.object(self.datasource, 'upload_auction_history_document')
        self.patch_post_results = mock.patch.object(self.datasource, '_post_results_data')

        self.mocked_get_active_bids = self.patch_get_active_bids.start()
        self.mocked_open_bidders_name = self.patch_open_bidders_name.start()
        self.mocked_upload_history = self.patch_upload_history.start()
        self.mocked_post_results = self.patch_post_results.start()

    def tearDown(self):
        self.patch_get_active_bids.stop()
        self.patch_open_bidders_name.stop()
        self.patch_upload_history.stop()
        self.patch_post_results.stop()

    def test_update_source_object_with_bad_document_upload(self):
        self.mocked_upload_history.return_value = None

        post_response_data = {'response': 'data'}
        self.mocked_post_results.return_value = post_response_data

        bids_result_data = {'bids': 'result'}
        self.mocked_get_active_bids.return_value = bids_result_data

        new_db_document = {'db_document': 'with opened names'}
        self.mocked_open_bidders_name.return_value = new_db_document

        result = self.datasource.update_source_object(self.external_data, self.db_document, self.history_document)

        self.assertEqual(result, None)

        self.assertEqual(self.mocked_upload_history.call_count, 1)
        self.mocked_upload_history.assert_called_with(self.history_document)

        self.assertEqual(self.mocked_post_results.call_count, 1)
        self.mocked_post_results.assert_called_with(self.external_data, self.db_document)

        self.assertEqual(self.mocked_get_active_bids.call_count, 1)
        self.mocked_get_active_bids.assert_called_with(post_response_data)

        self.assertEqual(self.mocked_open_bidders_name.call_count, 1)
        self.mocked_open_bidders_name.assert_called_with(self.db_document, bids_result_data)

    def test_update_source_object_with_bad_api_post(self):
        doc_id = '1' * 32
        self.mocked_upload_history.return_value = doc_id

        self.mocked_post_results.return_value = None

        result = self.datasource.update_source_object(self.external_data, self.db_document, self.history_document)

        self.assertEqual(result, None)

        self.assertEqual(self.mocked_upload_history.call_count, 1)
        self.mocked_upload_history.assert_called_with(self.history_document)

        self.assertEqual(self.mocked_post_results.call_count, 1)
        self.mocked_post_results.assert_called_with(self.external_data, self.db_document)

        self.assertEqual(self.mocked_get_active_bids.call_count, 0)

        self.assertEqual(self.mocked_open_bidders_name.call_count, 0)

    def test_update_source_object_with_bad_document_upload_and_api_post(self):
        self.mocked_upload_history.return_value = None

        self.mocked_post_results.return_value = None

        result = self.datasource.update_source_object(self.external_data, self.db_document, self.history_document)

        self.assertEqual(result, None)

        self.assertEqual(self.mocked_upload_history.call_count, 1)
        self.mocked_upload_history.assert_called_with(self.history_document)

        self.assertEqual(self.mocked_post_results.call_count, 1)
        self.mocked_post_results.assert_called_with(self.external_data, self.db_document)

        self.assertEqual(self.mocked_get_active_bids.call_count, 0)

        self.assertEqual(self.mocked_open_bidders_name.call_count, 0)

    def test_update_source_object_with_second_bad_document_upload(self):
        doc_id = '1' * 32

        self.mocked_upload_history.side_effect = iter([
            doc_id,
            None
        ])

        post_response_data = {'response': 'data'}
        self.mocked_post_results.return_value = post_response_data

        bids_result_data = {'bids': 'result'}
        self.mocked_get_active_bids.return_value = bids_result_data

        new_db_document = {'db_document': 'with opened names'}
        self.mocked_open_bidders_name.return_value = new_db_document

        result = self.datasource.update_source_object(self.external_data, self.db_document, self.history_document)

        self.assertEqual(result, new_db_document)

        self.assertEqual(self.mocked_upload_history.call_count, 2)
        self.mocked_upload_history.assert_called_with(self.history_document, doc_id)

        self.assertEqual(self.mocked_post_results.call_count, 1)
        self.mocked_post_results.assert_called_with(self.external_data, self.db_document)

        self.assertEqual(self.mocked_get_active_bids.call_count, 1)
        self.mocked_get_active_bids.assert_called_with(post_response_data)

        self.assertEqual(self.mocked_open_bidders_name.call_count, 1)
        self.mocked_open_bidders_name.assert_called_with(self.db_document, bids_result_data)

    def test_successful_update(self):
        doc_id = '1' * 32

        self.mocked_upload_history.side_effect = iter([
            doc_id,
            doc_id
        ])

        post_response_data = {'response': 'data'}
        self.mocked_post_results.return_value = post_response_data

        bids_result_data = {'bids': 'result'}
        self.mocked_get_active_bids.return_value = bids_result_data

        new_db_document = {'db_document': 'with opened names'}
        self.mocked_open_bidders_name.return_value = new_db_document

        result = self.datasource.update_source_object(self.external_data, self.db_document, self.history_document)

        self.assertEqual(result, new_db_document)

        self.assertEqual(self.mocked_upload_history.call_count, 2)
        self.mocked_upload_history.assert_called_with(self.history_document, doc_id)

        self.assertEqual(self.mocked_post_results.call_count, 1)
        self.mocked_post_results.assert_called_with(self.external_data, self.db_document)

        self.assertEqual(self.mocked_get_active_bids.call_count, 1)
        self.mocked_get_active_bids.assert_called_with(post_response_data)

        self.assertEqual(self.mocked_open_bidders_name.call_count, 1)
        self.mocked_open_bidders_name.assert_called_with(self.db_document, bids_result_data)


class TestPostResultData(TestOpenProcurementAPIDataSource):

    def setUp(self):
        super(TestPostResultData, self).setUp()
        self.datasource = self.datasource_class(self.config)
        self.session = mock.MagicMock()
        self.datasource.session = self.session
        self.db_document = {'results': []}

        self.request_session = mock.MagicMock()

        self.patch_make_request = mock.patch('openprocurement.auction.gong.datasource.make_request')
        self.patch_generate_request_id = mock.patch('openprocurement.auction.gong.datasource.generate_request_id')
        self.patch_get_latest_bid_for_bidder = mock.patch('openprocurement.auction.gong.datasource.get_latest_bid_for_bidder')

        self.mocked_make_request = self.patch_make_request.start()
        self.mocked_generate_request_id = self.patch_generate_request_id.start()

        self.request_id = uuid4().hex
        self.mocked_generate_request_id.return_value = self.request_id
        self.mocked_get_latest_bid_for_bidder = self.patch_get_latest_bid_for_bidder.start()

    def tearDown(self):
        self.patch_make_request.stop()
        self.patch_generate_request_id.stop()
        self.patch_get_latest_bid_for_bidder.stop()

    def test_post_results_data_with_bids_in_active(self):
        external_data = {'data': {
            'bids': [
                {
                    'status': 'draft',
                },
                {
                    'value': {'amount': 1000},
                    'date': 'bid create date',
                    'status': 'active',
                    'id': '2' * 32
                },

            ]
        }}

        last_bid_of_active_bidder = {
            'amount': 10000,
            'time': 'time of bid',
            'id': '2' * 32
        }
        self.mocked_get_latest_bid_for_bidder.return_value = last_bid_of_active_bidder

        data_with_results = {
            'data': {
                'bids': [
                    {
                        'status': 'draft',
                    },
                    {
                        'value': {'amount': last_bid_of_active_bidder['amount']},
                        'date': last_bid_of_active_bidder['time'],
                        'status': 'active',
                        'id': '2' * 32
                    }
                ]
            }
        }

        self.datasource._post_results_data(external_data, self.db_document)

        self.assertEqual(self.mocked_get_latest_bid_for_bidder.call_count, 1)
        self.mocked_get_latest_bid_for_bidder.assert_called_with(self.db_document['results'], last_bid_of_active_bidder['id'])

        self.assertEqual(self.mocked_make_request.call_count, 1)
        self.mocked_make_request.assert_called_with(
            self.datasource.api_url + '/auction',
            data=data_with_results,
            user=self.datasource.api_token,
            method='post',
            request_id=self.request_id,
            session=self.datasource.session
        )

    def test_post_results_data_with_bid_without_status(self):
        external_data = {'data': {
            'bids': [
                {
                    'status': 'draft',
                },
                {
                    'value': {'amount': 1000},
                    'date': 'bid create date',
                    'id': '2' * 32
                },

            ]
        }}

        last_bid_of_active_bidder = {
            'amount': 10000,
            'time': 'time of bid',
            'id': '2' * 32
        }
        self.mocked_get_latest_bid_for_bidder.return_value = last_bid_of_active_bidder

        data_with_results = {
            'data': {
                'bids': [
                    {
                        'status': 'draft',
                    },
                    {
                        'value': {'amount': last_bid_of_active_bidder['amount']},
                        'date': last_bid_of_active_bidder['time'],
                        'id': '2' * 32
                    }
                ]
            }
        }

        self.datasource._post_results_data(external_data, self.db_document)

        self.assertEqual(self.mocked_get_latest_bid_for_bidder.call_count, 1)
        self.mocked_get_latest_bid_for_bidder.assert_called_with(
            self.db_document['results'],
            last_bid_of_active_bidder['id']
        )

        self.assertEqual(self.mocked_make_request.call_count, 1)
        self.mocked_make_request.assert_called_with(
            self.datasource.api_url + '/auction',
            data=data_with_results,
            user=self.datasource.api_token,
            method='post',
            request_id=self.request_id,
            session=self.datasource.session
        )


class TestUploadHistoryDocument(TestOpenProcurementAPIDataSource):

    def setUp(self):
        super(TestUploadHistoryDocument, self).setUp()

        self.history_data = {'auction': 'protocol'}

        self.patch_request_session = mock.patch('openprocurement.auction.gong.datasource.RequestsSession')
        self.mocked_request_session = self.patch_request_session.start()
        self.request_session = mock.MagicMock()
        self.mocked_request_session.return_value = self.request_session

        self.datasource = self.datasource_class(self.config)

        self.patch_upload_audit_with_ds = mock.patch.object(
            self.datasource,
            '_upload_audit_file_with_document_service'
        )
        self.patch_upload_audit_without_ds = mock.patch.object(
            self.datasource,
            '_upload_audit_file_without_document_service'
        )

        self.mocked_upload_audit_with_ds = self.patch_upload_audit_with_ds.start()
        self.mocked_upload_audit_without_ds = self.patch_upload_audit_without_ds.start()

    def tearDown(self):
        self.patch_request_session.stop()
        self.mocked_request_session.stop()
        self.patch_upload_audit_with_ds.stop()
        self.patch_upload_audit_without_ds.stop()

    def test_upload_history_document_with_ds(self):
        self.datasource.with_document_service = True

        self.mocked_upload_audit_with_ds.return_value = None

        result = self.datasource.upload_auction_history_document(self.history_data)

        self.assertIsNone(result)
        self.assertEqual(self.mocked_upload_audit_with_ds.call_count, 1)
        self.mocked_upload_audit_with_ds.assert_called_with(self.history_data, None)

        self.assertEqual(self.mocked_upload_audit_without_ds.call_count, 0)

        # With doc id
        doc_id = '1' * 32
        result = self.datasource.upload_auction_history_document(self.history_data, doc_id)

        self.assertIsNone(result)
        self.assertEqual(self.mocked_upload_audit_with_ds.call_count, 2)
        self.mocked_upload_audit_with_ds.assert_called_with(self.history_data, doc_id)

        self.assertEqual(self.mocked_upload_audit_without_ds.call_count, 0)

    def test_upload_history_document_without_ds(self):
        self.datasource.with_document_service = False

        self.mocked_upload_audit_without_ds.return_value = None

        result = self.datasource.upload_auction_history_document(self.history_data)

        self.assertIsNone(result)
        self.assertEqual(self.mocked_upload_audit_without_ds.call_count, 1)
        self.mocked_upload_audit_without_ds.assert_called_with(self.history_data, None)

        self.assertEqual(self.mocked_upload_audit_with_ds.call_count, 0)

        # With doc id
        doc_id = '1' * 32
        result = self.datasource.upload_auction_history_document(self.history_data, doc_id)

        self.assertIsNone(result)
        self.assertEqual(self.mocked_upload_audit_without_ds.call_count, 2)
        self.mocked_upload_audit_without_ds.assert_called_with(self.history_data, doc_id)

        self.assertEqual(self.mocked_upload_audit_with_ds.call_count, 0)

    def test_successful_upload_with_ds(self):
        self.datasource.with_document_service = True

        doc_id = '1' * 32
        self.mocked_upload_audit_with_ds.return_value = doc_id

        result = self.datasource.upload_auction_history_document(self.history_data)

        self.assertEqual(result, doc_id)
        self.assertEqual(self.mocked_upload_audit_with_ds.call_count, 1)
        self.mocked_upload_audit_with_ds.assert_called_with(self.history_data, None)

        self.assertEqual(self.mocked_upload_audit_without_ds.call_count, 0)

    def test_successful_upload_without_ds(self):
        self.datasource.with_document_service = False

        doc_id = '1' * 32
        self.mocked_upload_audit_without_ds.return_value = doc_id

        result = self.datasource.upload_auction_history_document(self.history_data)

        self.assertEqual(result, doc_id)
        self.assertEqual(self.mocked_upload_audit_without_ds.call_count, 1)
        self.mocked_upload_audit_without_ds.assert_called_with(self.history_data, None)

        self.assertEqual(self.mocked_upload_audit_with_ds.call_count, 0)


class TestUploadFileWithDS(TestOpenProcurementAPIDataSource):

    def setUp(self):
        super(TestUploadFileWithDS, self).setUp()

        self.ds_service_config = {
            'username': 'username',
            'password': 'password',
            'url': 'http://docservice_url'
        }

        self.config['DOCUMENT_SERVICE'] = self.ds_service_config
        self.config['with_document_service'] = True
        self.datasource = self.datasource_class(self.config)
        self.history_data = {'auction': 'protocol'}

        self.session = mock.MagicMock()
        self.session_ds = mock.MagicMock()
        self.datasource.session = self.session
        self.datasource.session_ds = self.session_ds

        self.patch_make_request = mock.patch('openprocurement.auction.gong.datasource.make_request')
        self.patch_yaml_dump = mock.patch('openprocurement.auction.gong.datasource.yaml_dump')
        self.patch_generate_request_id = mock.patch('openprocurement.auction.gong.datasource.generate_request_id')

        self.mock_make_request = self.patch_make_request.start()

        self.mock_yaml_dump = self.patch_yaml_dump.start()
        self.yaml_doc = {'yaml': 'data'}
        self.mock_yaml_dump.return_value = self.yaml_doc

        self.mock_generate_request_id = self.patch_generate_request_id.start()
        self.request_id = uuid4().hex
        self.mock_generate_request_id.return_value = self.request_id

    def tearDown(self):
        self.patch_generate_request_id.stop()
        self.patch_yaml_dump.stop()
        self.patch_make_request.stop()

    def test_upload_with_doc_id(self):
        success_put_data_response = {'data': {'id': '1' * 32}}
        ds_response = {'ds': 'response'}
        self.mock_make_request.side_effect = iter([
            ds_response,
            success_put_data_response
        ])

        doc_id = uuid4().hex

        result = self.datasource._upload_audit_file_with_document_service(self.history_data, doc_id)
        self.assertEqual(result, success_put_data_response['data']['id'])

        self.assertEqual(self.mock_make_request.call_count, 2)

        ds_request = {
            'files': {'file': ('audit_{}.yaml'.format(self.config['auction_id']), self.yaml_doc)},
            'method': 'post',
            'user': self.ds_service_config['username'],
            'password': self.ds_service_config['password'],
            'session': self.session_ds,
            'retry_count': 3
        }
        # Really bad practise but only way to make assert_called_with to previous call
        self.assertEqual(
            self.mock_make_request.call_args_list[0][0][0],
            self.ds_service_config['url']
        )
        self.assertEqual(
            self.mock_make_request.call_args_list[0][1],
            ds_request
        )

        self.mock_make_request.assert_called_with(
            self.datasource.api_url + '/documents/{}'.format(doc_id),
            data=ds_response,
            user=self.datasource.api_token,
            method='put',
            request_id=self.request_id,
            session=self.session,
            retry_count=2
        )

    def test_upload_without_doc_id(self):
        success_put_data_response = {'data': {'id': '1' * 32}}
        ds_response = {'ds': 'response'}
        self.mock_make_request.side_effect = iter([
            ds_response,
            success_put_data_response
        ])

        result = self.datasource._upload_audit_file_with_document_service(self.history_data)
        self.assertEqual(result, success_put_data_response['data']['id'])

        self.assertEqual(self.mock_make_request.call_count, 2)

        ds_request = {
            'files': {'file': ('audit_{}.yaml'.format(self.config['auction_id']), self.yaml_doc)},
            'method': 'post',
            'user': self.ds_service_config['username'],
            'password': self.ds_service_config['password'],
            'session': self.session_ds,
            'retry_count': 3
        }
        # Really bad practise but only way to make assert_called_with to previous call
        self.assertEqual(
            self.mock_make_request.call_args_list[0][0][0],
            self.ds_service_config['url']
        )
        self.assertEqual(
            self.mock_make_request.call_args_list[0][1],
            ds_request
        )

        self.mock_make_request.assert_called_with(
            self.datasource.api_url + '/documents',
            data=ds_response,
            user=self.datasource.api_token,
            method='post',
            request_id=self.request_id,
            session=self.session,
            retry_count=2
        )

    def test_upload_with_bad_api_request(self):
        ds_response = {'ds': 'response'}
        self.mock_make_request.side_effect = iter([
            ds_response,
            None
        ])

        result = self.datasource._upload_audit_file_with_document_service(self.history_data)
        self.assertEqual(result, None)

        self.assertEqual(self.mock_make_request.call_count, 2)

        ds_request = {
            'files': {'file': ('audit_{}.yaml'.format(self.config['auction_id']), self.yaml_doc)},
            'method': 'post',
            'user': self.ds_service_config['username'],
            'password': self.ds_service_config['password'],
            'session': self.session_ds,
            'retry_count': 3
        }
        # Really bad practise but only way to make assert_called_with to previous call
        self.assertEqual(
            self.mock_make_request.call_args_list[0][0][0],
            self.ds_service_config['url']
        )
        self.assertEqual(
            self.mock_make_request.call_args_list[0][1],
            ds_request
        )

        self.mock_make_request.assert_called_with(
            self.datasource.api_url + '/documents',
            data=ds_response,
            user=self.datasource.api_token,
            method='post',
            request_id=self.request_id,
            session=self.session,
            retry_count=2
        )


class TestUploadFileWithoutDS(TestOpenProcurementAPIDataSource):

    def setUp(self):
        super(TestUploadFileWithoutDS, self).setUp()

        self.datasource = self.datasource_class(self.config)
        self.history_data = {'auction': 'protocol'}

        self.session = mock.MagicMock()
        self.datasource.session = self.session

        self.patch_make_request = mock.patch('openprocurement.auction.gong.datasource.make_request')
        self.patch_yaml_dump = mock.patch('openprocurement.auction.gong.datasource.yaml_dump')
        self.patch_generate_request_id = mock.patch('openprocurement.auction.gong.datasource.generate_request_id')

        self.mock_make_request = self.patch_make_request.start()

        self.mock_yaml_dump = self.patch_yaml_dump.start()
        self.yaml_doc = {'yaml': 'data'}
        self.mock_yaml_dump.return_value = self.yaml_doc

        self.mock_generate_request_id = self.patch_generate_request_id.start()
        self.request_id = uuid4().hex
        self.mock_generate_request_id.return_value = self.request_id

    def tearDown(self):
        self.patch_generate_request_id.stop()
        self.patch_yaml_dump.stop()
        self.patch_make_request.stop()

    def test_upload_with_doc_id(self):
        success_put_data_response = {'data': {'id': '1' * 32}}
        self.mock_make_request.side_effect = iter([
            success_put_data_response
        ])

        doc_id = uuid4().hex

        result = self.datasource._upload_audit_file_without_document_service(self.history_data, doc_id)
        self.assertEqual(result, success_put_data_response['data']['id'])

        self.assertEqual(self.mock_make_request.call_count, 1)

        files = {'file': ('audit_{}.yaml'.format(self.config['auction_id']), self.yaml_doc)}
        self.mock_make_request.assert_called_with(
            self.datasource.api_url + '/documents/{}'.format(doc_id),
            files=files,
            user=self.datasource.api_token,
            method='put',
            request_id=self.request_id,
            session=self.session,
            retry_count=2
        )

    def test_upload_without_doc_id(self):
        success_put_data_response = {'data': {'id': '1' * 32}}
        self.mock_make_request.side_effect = iter([
            success_put_data_response
        ])

        result = self.datasource._upload_audit_file_without_document_service(self.history_data)
        self.assertEqual(result, success_put_data_response['data']['id'])

        self.assertEqual(self.mock_make_request.call_count, 1)

        files = {'file': ('audit_{}.yaml'.format(self.config['auction_id']), self.yaml_doc)}
        self.mock_make_request.assert_called_with(
            self.datasource.api_url + '/documents',
            files=files,
            user=self.datasource.api_token,
            method='post',
            request_id=self.request_id,
            session=self.session,
            retry_count=2
        )

    def test_upload_with_bad_api_request(self):
        self.mock_make_request.side_effect = iter([
            None
        ])

        result = self.datasource._upload_audit_file_without_document_service(self.history_data)
        self.assertEqual(result, None)

        self.assertEqual(self.mock_make_request.call_count, 1)

        files = {'file': ('audit_{}.yaml'.format(self.config['auction_id']), self.yaml_doc)}
        self.mock_make_request.assert_called_with(
            self.datasource.api_url + '/documents',
            files=files,
            user=self.datasource.api_token,
            method='post',
            request_id=self.request_id,
            session=self.session,
            retry_count=2
        )



def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestInit))
    return suite
