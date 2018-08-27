# -*- coding: utf-8 -*-
import iso8601

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, time, timedelta

from openprocurement.auction.worker_core.constants import TIMEZONE
from openprocurement.auction.worker_core.utils import prepare_service_stage

from openprocurement.auction.gong.constants import (
    PAUSE_DURATION, DEADLINE_HOUR, END, MAIN_ROUND
)


def prepare_results_stage(bidder_id="", bidder_name="", amount="", time=""):
    stage = dict(
        bidder_id=bidder_id,
        time=str(time),
        amount=amount or 0,
        label=dict(
            en="Bidder #{}".format(bidder_name),
            uk="Учасник №{}".format(bidder_name),
            ru="Участник №{}".format(bidder_name)
        )
    )
    return stage


def prepare_auction_stages(stage_start, auction_data, fast_forward=False):
    pause_stage = prepare_service_stage(start=stage_start.isoformat())
    main_round_stage = {}
    stages = [pause_stage, main_round_stage]

    stage_start += timedelta(seconds=PAUSE_DURATION)
    deadline = set_specific_hour(stage_start, DEADLINE_HOUR)
    if stage_start < deadline:
        main_round_stage.update({
            'start': stage_start.isoformat(),
            'type': MAIN_ROUND,
            'amount': auction_data['value']['amount'] + auction_data['minimalStep']['amount'],
            'time': ''
        })

    return stages


def prepare_end_stage(start):
    stage = {
        'start': start.isoformat(),
        'type': END,
    }
    return stage


def get_round_ending_time(start_date, duration, deadline):
    default_round_ending_time = start_date + timedelta(seconds=duration)
    if default_round_ending_time < deadline:
        return default_round_ending_time
    return deadline


def set_specific_hour(date_time, hour):
    """Reset datetime's time to {hour}:00:00, while saving timezone data

    Example:
        2018-1-1T14:12:55+02:00 -> 2018-1-1T02:00:00+02:00, for hour=2
        2018-1-1T14:12:55+02:00 -> 2018-1-1T18:00:00+02:00, for hour=18
    """

    return datetime.combine(
        date_time.date(), time(hour % 24, tzinfo=date_time.tzinfo)
    )


def prepare_bid_stage(exist_stage_params, params={},  current_auction_value=0):
    # Should get amount of previous stage or initial_auction_value
    # current_auction_value += minimalStep
    stage = None
    return stage


def get_active_bids(results):

    bids_information = dict([
        (bid["id"], bid.get("tenderers"))
        for bid in results["data"].get("bids", [])
        if bid.get("status", "active") == "active"
    ])

    return bids_information


def open_bidders_name(auction_document, bids_information):
    for field in ['results', 'stages']:
        for index, stage in enumerate(auction_document[field]):
            if 'bidder_id' in stage and stage['bidder_id'] in bids_information:
                auction_document[field][index].update({
                    "label": {
                        'uk': bids_information[stage['bidder_id']][0]["name"],
                        'en': bids_information[stage['bidder_id']][0]["name"],
                        'ru': bids_information[stage['bidder_id']][0]["name"],
                    }
                })
    return auction_document


@contextmanager
def update_auction_document(context, database):
    auction_document = deepcopy(context['auction_document'])
    yield auction_document
    database.save_auction_document(auction_document, context['auction_doc_id'])
    context['auction_document'].update(auction_document)


@contextmanager
def lock_server(semaphore):
    semaphore.acquire()
    yield
    semaphore.release()


def prepare_audit():
    protocol = {
        "timeline": {
            "auction_start": {
                "initial_bids": []
            }
        }
    }
    return protocol


def convert_datetime(datetime_stamp):
    return iso8601.parse_date(datetime_stamp).astimezone(TIMEZONE)
