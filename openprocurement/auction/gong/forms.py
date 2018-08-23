# -*- coding: utf-8 -*-
from copy import deepcopy
from datetime import datetime

import wtforms_json
from flask import request, session, current_app as app
from wtforms import Form, FloatField, StringField
from wtforms.validators import InputRequired, ValidationError

from openprocurement.auction.utils import prepare_extra_journal_fields
from openprocurement.auction.worker_core.constants import TIMEZONE

from openprocurement.auction.gong.constants import MAIN_ROUND
from openprocurement.auction.gong.context import IContext
from openprocurement.auction.gong.utils import lock_bids


wtforms_json.init()


def validate_bid_value(form, field):
    """
    Bid must be higher or equal to previous bidder bid amount plus minimalStep
    amount. Bid amount should also be multiple of minimalStep amount.
    """
    stage_id = form.document['current_stage']
    minimal_step = form.document['minimalStep']['amount']
    current_amount = form.document['stages'][stage_id].get('amount')
    if form.document['stages'][stage_id]['type'] != MAIN_ROUND:
        raise ValidationError(u'Current stage does not allow bidding')
    if field.data < current_amount:
        raise ValidationError(u'Too low value')
    if field.data % minimal_step:
        raise ValidationError(
            u'Value should be a multiplier of ' 
            u'a minimalStep amount ({})'.format(minimal_step)
        )


class BidsForm(Form):
    bidder_id = StringField(
        'bidder_id',
        validators=[
            InputRequired(message=u'No bidder id'),
        ]
    )
    bid = FloatField(
        'bid',
        validators=[
            InputRequired(message=u'Bid amount is required'),
            validate_bid_value
        ]
    )


def form_handler():
    auction = app.config['auction']
    context = app.gsm.queryUtility(IContext)
    form = app.bids_form.from_json(request.json)
    form.document = deepcopy(context['auction_document'])
    current_time = datetime.now(TIMEZONE)
    if form.validate():
        with lock_bids(auction):
            app.bids_handler.add_bid(form.document['current_stage'],
                                     {'amount': form.data['bid'],
                                      'bidder_id': form.data['bidder_id'],
                                      'time': current_time.isoformat()})
            app.logger.info(
                "Bidder {} with client_id {} placed bid {} in {}".format(
                    form.data['bidder_id'], session['client_id'],
                    form.data['bid'], current_time.isoformat()
                ), extra=prepare_extra_journal_fields(request.headers)
            )
            return {'status': 'ok', 'data': form.data}
    else:
        app.logger.info(
            "Bidder {} with client_id {} wants place "
            "bid {} in {} with errors {}".format(
                request.json.get('bidder_id', 'None'), session['client_id'],
                request.json.get('bid', 'None'), current_time.isoformat(),
                repr(form.errors)
            ), extra=prepare_extra_journal_fields(request.headers)
        )
        return {'status': 'failed', 'errors': form.errors}
