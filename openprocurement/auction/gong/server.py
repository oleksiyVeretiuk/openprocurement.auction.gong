# -*- coding: utf-8 -*-
import os

from flask import Flask, session
from flask_oauthlib.client import OAuth
from gevent import spawn
from gevent.pywsgi import WSGIServer
from pytz import timezone as tz
from zope.component import getGlobalSiteManager


from openprocurement.auction.helpers.system import get_lisener
from openprocurement.auction.event_source import (
    sse, push_timestamps_events, check_clients
)
from openprocurement.auction.utils import create_mapping
from openprocurement.auction.worker_core.server import (
    _LoggerStream, AuctionsWSGIHandler
)

from openprocurement.auction.gong import views
from openprocurement.auction.gong.bids import BidsHandler
from openprocurement.auction.gong.constants import AUCTION_SUBPATH
from openprocurement.auction.gong.forms import BidsForm, form_handler


def initialize_application():
    app = Flask(__name__)
    app.auction_bidders = {}
    app.register_blueprint(sse)
    app.secret_key = os.urandom(24)
    app.logins_cache = {}
    return app


def add_url_rules(app):
    app.add_url_rule('/login', 'login', views.login)
    app.add_url_rule('/logout', 'logout', views.logout)
    app.add_url_rule('/authorized', 'authorized', views.authorized)
    app.add_url_rule('/postbid', 'postbid', views.post_bid, methods=['POST'])
    app.add_url_rule('/kickclient', 'kickclient', views.kickclient, methods=['POST'])
    app.add_url_rule('/check_authorization', 'check_authorization', views.check_authorization, methods=['POST'])


def run_server(auction, mapping_expire_time, logger, timezone='Europe/Kiev', bids_form=BidsForm,
               bids_handler=BidsHandler, form_handler=form_handler, cookie_path=AUCTION_SUBPATH):
    app = initialize_application()
    add_url_rules(app)
    app.config.update(auction.worker_defaults)
    # Replace Flask custom logger
    app.logger_name = logger.name
    app._logger = logger
    app.config['timezone'] = tz(timezone)
    app.config['SESSION_COOKIE_PATH'] = '/{}/{}'.format(cookie_path, auction.auction_doc_id)
    app.config['SESSION_COOKIE_NAME'] = 'auction_session'
    app.oauth = OAuth(app)
    app.gsm = getGlobalSiteManager()
    app.bids_form = bids_form
    app.bids_handler = bids_handler()
    app.form_handler = form_handler
    app.remote_oauth = app.oauth.remote_app(
        'remote',
        consumer_key=app.config['OAUTH_CLIENT_ID'],
        consumer_secret=app.config['OAUTH_CLIENT_SECRET'],
        request_token_params={'scope': 'email'},
        base_url=app.config['OAUTH_BASE_URL'],
        access_token_url=app.config['OAUTH_ACCESS_TOKEN_URL'],
        authorize_url=app.config['OAUTH_AUTHORIZE_URL']
    )

    @app.remote_oauth.tokengetter
    def get_oauth_token():
        return session.get('remote_oauth')
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

    # Start server on unused port
    listener = get_lisener(auction.worker_defaults["STARTS_PORT"],
                          host=auction.worker_defaults.get("WORKER_BIND_IP", ""))
    app.logger.info(
        "Start server on {0}:{1}".format(*listener.getsockname()),
        extra={"JOURNAL_REQUEST_ID": auction.request_id}
    )
    server = WSGIServer(listener, app,
                        log=_LoggerStream(logger),
                        handler_class=AuctionsWSGIHandler)
    server.start()
    # Set mapping
    mapping_value = "http://{0}:{1}/".format(*listener.getsockname())
    create_mapping(auction.worker_defaults,
                   auction.auction_doc_id,
                   mapping_value)
    app.logger.info("Server mapping: {} -> {}".format(
        auction.auction_doc_id,
        mapping_value,
        mapping_expire_time
    ), extra={"JOURNAL_REQUEST_ID": auction.request_id})

    # Spawn events functionality
    spawn(push_timestamps_events, app,)
    spawn(check_clients, app, )
    return server
