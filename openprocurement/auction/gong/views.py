# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta
from urlparse import urljoin

import iso8601
from dateutil.tz import tzlocal
from flask import (
    current_app as app, request, jsonify, url_for, session, abort, redirect
)

from openprocurement.auction.event_source import (
    send_event, send_event_to_client, remove_client,
)
from openprocurement.auction.utils import (
    prepare_extra_journal_fields, get_bidder_id
)

INVALIDATE_GRANT = timedelta(0, 230)


def login():
    if 'bidder_id' in request.args and 'hash' in request.args:
        for bidder_info in app.config['auction'].bidders_data:
            if bidder_info['id'] == request.args['bidder_id']:
                next_url = request.args.get('next') or request.referrer or None
                if 'X-Forwarded-Path' in request.headers:
                    callback_url = urljoin(
                        request.headers['X-Forwarded-Path'],
                        'authorized'
                    )
                else:
                    callback_url = url_for('authorized', next=next_url, _external=True)
                response = app.remote_oauth.authorize(
                    callback=callback_url,
                    bidder_id=request.args['bidder_id'],
                    hash=request.args['hash']
                )
                if 'return_url' in request.args:
                    session['return_url'] = request.args['return_url']
                session['login_bidder_id'] = request.args['bidder_id']
                session['login_hash'] = request.args['hash']
                session['login_callback'] = callback_url
                app.logger.debug("Session: {}".format(repr(session)))
                return response
    return abort(401)


def authorized():
    if not('error' in request.args and request.args['error'] == 'access_denied'):
        resp = app.remote_oauth.authorized_response()
        if resp is None or hasattr(resp, 'data'):
            app.logger.info("Error Response from Oauth: {}".format(resp))
            return abort(403, 'Access denied')
        app.logger.info("Get response from Oauth: {}".format(repr(resp)))
        session['remote_oauth'] = (resp['access_token'], '')
        session['client_id'] = os.urandom(16).encode('hex')
    else:
        app.logger.info("Error on user authorization. Error: {}".format(
            request.args.get('error', ''))
            )
        return abort(403, 'Access denied')
    bidder_data = get_bidder_id(app, session)
    app.logger.info("Bidder {} with client_id {} authorized".format(
                    bidder_data.get('bidder_id'), session.get('client_id'),
                    ), extra=prepare_extra_journal_fields(request.headers))

    app.logger.debug("Session: {}".format(repr(session)))
    response = redirect(
        urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
    )
    response.set_cookie('auctions_loggedin', '1',
                        path=app.config['SESSION_COOKIE_PATH'],
                        secure=False, httponly=False, max_age=36000
                        )
    return response


def relogin():
    if (all([key in session
             for key in ['login_callback', 'login_bidder_id', 'login_hash']])):
        if 'amount' in request.args:
            session['amount'] = request.args['amount']
        app.logger.debug("Session: {}".format(repr(session)))
        app.logger.info("Bidder {} with login_hash {} start re-login".format(
                        session['login_bidder_id'], session['login_hash'],
                        ), extra=prepare_extra_journal_fields(request.headers))
        return app.remote_oauth.authorize(
            callback=session['login_callback'],
            bidder_id=session['login_bidder_id'],
            hash=session['login_hash'],
            auto_allow='1'
        )
    return redirect(
        urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
    )


def check_authorization():
    if 'remote_oauth' in session and 'client_id' in session:
        # resp = app.remote_oauth.get('me')
        bidder_data = get_bidder_id(app, session)
        if bidder_data:
            grant_timeout = iso8601.parse_date(bidder_data[u'expires']) - datetime.now(tzlocal())
            if grant_timeout > INVALIDATE_GRANT:
                app.logger.info("Bidder {} with client_id {} pass check_authorization".format(
                                bidder_data['bidder_id'], session['client_id'],
                                ), extra=prepare_extra_journal_fields(request.headers))
                return jsonify({'status': 'ok'})
            else:
                app.logger.info(
                    "Grant will end in a short time. Activate re-login functionality",
                    extra=prepare_extra_journal_fields(request.headers)
                )
        else:
            app.logger.warning("Client_id {} didn't passed check_authorization".format(session['client_id']),
                               extra=prepare_extra_journal_fields(request.headers))
    abort(401)


def logout():
    if 'remote_oauth' in session and 'client_id' in session:
        bidder_data = get_bidder_id(app, session)
        if bidder_data:
            remove_client(bidder_data['bidder_id'], session['client_id'])
            send_event(
                bidder_data['bidder_id'],
                app.auction_bidders[bidder_data['bidder_id']]["clients"],
                "ClientsList"
            )
    session.clear()
    return redirect(
        urljoin(request.headers['X-Forwarded-Path'], '.').rstrip('/')
    )


def post_bid():
    if 'remote_oauth' in session and 'client_id' in session:
        bidder_data = get_bidder_id(app, session)
        if bidder_data and bidder_data['bidder_id'] == request.json['bidder_id']:
            return jsonify(app.form_handler())
        else:
            app.logger.warning(
                "Client with client id: {} and bidder_id {} wants post bid but response status from Oauth".format(
                    session.get('client_id', 'None'), request.json.get('bidder_id', 'None')
                )
            )
    abort(401)


def kickclient():
    if 'remote_oauth' in session and 'client_id' in session:
        auction = app.config['auction']
        with auction.bids_actions:
            data = request.json
            bidder_data = get_bidder_id(app, session)
            if bidder_data:
                data['bidder_id'] = bidder_data['bidder_id']
                if 'client_id' in data:
                    send_event_to_client(
                        data['bidder_id'], data['client_id'], {
                            "from": session['client_id']
                        }, "KickClient"
                    )
                    return jsonify({"status": "ok"})
    abort(401)
