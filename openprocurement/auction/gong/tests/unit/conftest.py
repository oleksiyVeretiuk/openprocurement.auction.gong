# -*- coding: utf-8 -*-
import datetime
import logging
import os
import pytest
import yaml
import couchdb

from flask import redirect
from mock import MagicMock
from dateutil.tz import tzlocal
from datetime import timedelta
from StringIO import StringIO
from pytz import timezone as tz

from openprocurement.auction.gong.auction import Auction, SCHEDULER
from openprocurement.auction.gong.mixins import LOGGER
from openprocurement.auction.gong.tests.data.data import (
    tender_data, test_auction_document
)
from openprocurement.auction.gong.server import (
    app as worker_app, BidsForm
)


def update_auctionPeriod(data):
    new_start_time = (datetime.datetime.now(tzlocal()) + datetime.timedelta(seconds=1)).isoformat()
    data['data']['auctionPeriod']['startDate'] = new_start_time


PWD = os.path.dirname(os.path.realpath(__file__))

worker_defaults_file_path = os.path.join(PWD, "../data/auction_worker_defaults.yaml")
with open(worker_defaults_file_path) as stream:
    worker_defaults = yaml.load(stream)


@pytest.yield_fixture(scope="class")
def auction(request):
    update_auctionPeriod(tender_data)

    request.cls.auction = Auction(
        tender_id=tender_data['data']['auctionID'],
        worker_defaults=yaml.load(open(worker_defaults_file_path)),
        auction_data=tender_data,
    )


@pytest.fixture(scope='class')
def db(request):
    server = couchdb.Server("http://" + worker_defaults['COUCH_DATABASE'].split('/')[2])
    name = worker_defaults['COUCH_DATABASE'].split('/')[3]

    def delete():
        del server[name]

    if name in server:
        delete()
    server.create(name)
    request.addfinalizer(delete)


class LogInterceptor(object):
    def __init__(self, logger):
        self.log_capture_string = StringIO()
        self.test_handler = logging.StreamHandler(self.log_capture_string)
        self.test_handler.setLevel(logging.INFO)
        logger.addHandler(self.test_handler)


@pytest.fixture(scope='class')
def logger(request):
    request.cls.log_interceptor = LogInterceptor(LOGGER)


@pytest.fixture(scope='class')
def scheduler(request):
    request.cls.SCHEDULER = SCHEDULER


@pytest.fixture(scope='class')
def app(request):
    update_auctionPeriod(tender_data)
    logger = MagicMock()
    logger.name = 'some-logger'
    app_auction = Auction(
        tender_id=tender_data['data']['auctionID'],
        worker_defaults=yaml.load(open(worker_defaults_file_path)),
        auction_data=tender_data,
    )
    app_auction.bidders_data = tender_data['data']['bids']
    app_auction.db = MagicMock()
    app_auction.db.get.return_value = test_auction_document
    worker_app.config.update(app_auction.worker_defaults)
    worker_app.logger_name = logger.name
    worker_app._logger = logger
    worker_app.config['auction'] = app_auction
    worker_app.config['timezone'] = tz('Europe/Kiev')
    worker_app.config['SESSION_COOKIE_PATH'] = '/{}/{}'.format(
        'auctions', app_auction.auction_doc_id)
    worker_app.config['SESSION_COOKIE_NAME'] = 'auction_session'
    worker_app.oauth = MagicMock()
    worker_app.bids_form = BidsForm
    worker_app.form_handler = MagicMock()
    worker_app.form_handler.return_value = {'data': 'ok'}
    worker_app.remote_oauth = MagicMock()
    worker_app.remote_oauth.authorized_response.side_effect = [None, {
        u'access_token': u'aMALGpjnB1iyBwXJM6betfgT4usHqw',
        u'token_type': u'Bearer',
        u'expires_in': 86400,
        u'refresh_token': u'uoRKeSJl9UFjuMwOw6PikXuUVp7MjX',
        u'scope': u'email'
    }]
    worker_app.remote_oauth.authorize.return_value = \
        redirect('https://my.test.url')
    worker_app.logins_cache[(u'aMALGpjnB1iyBwXJM6betfgT4usHqw', '')] = {
        u'bidder_id': u'f7c8cd1d56624477af8dc3aa9c4b3ea3',
        u'expires':
            (datetime.datetime.now(tzlocal()) + timedelta(0, 600)).isoformat()
    }
    worker_app.auction_bidders = {
        u'f7c8cd1d56624477af8dc3aa9c4b3ea3': {
            'clients': {},
            'channels': {}
        }}
    request.cls.worker_app = worker_app.test_client()


def pytest_addoption(parser):
    parser.addoption("--worker", action="store_true", help="runs worker test", dest='worker')


def pytest_configure(config):
    # register an additional marker
    config.addinivalue_line("markers", "worker: mark test to run only if worker option is passed (--worker)")


def pytest_runtest_setup(item):
    worker_marker = item.get_marker("worker")
    if worker_marker is not None:
        if not item.config.getoption("worker", False):
            pytest.skip("test requires worker option (--worker)")
