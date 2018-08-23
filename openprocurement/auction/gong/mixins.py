# -*- coding: utf-8 -*-
import json
import logging
from collections import defaultdict as dd
from copy import deepcopy
from couchdb.http import HTTPError, RETRYABLE_ERRORS
from datetime import timedelta, datetime
from openprocurement.auction.gong.scheduler import SCHEDULER

from openprocurement.auction.utils import (
    generate_request_id
)
from openprocurement.auction.worker_core.constants import TIMEZONE
from openprocurement.auction.worker_core.utils import prepare_service_stage

from openprocurement.auction.gong.utils import (
    set_specific_hour,
    get_round_ending_time
)
from openprocurement.auction.gong.constants import (
    BIDS_KEYS_FOR_COPY,
    MAIN_ROUND,
    END,
    ROUND_DURATION,
    PAUSE_DURATION,
    DEADLINE_HOUR
)
from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_DB_GET_DOC,
    AUCTION_WORKER_DB_GET_DOC_ERROR,
    AUCTION_WORKER_DB_GET_DOC_UNHANDLED_ERROR,
    AUCTION_WORKER_DB_SAVE_DOC,
    AUCTION_WORKER_DB_SAVE_DOC_ERROR,
    AUCTION_WORKER_DB_SAVE_DOC_UNHANDLED_ERROR,
    AUCTION_WORKER_SERVICE_END_BID_STAGE,
    AUCTION_WORKER_SERVICE_START_NEXT_STAGE,
)

from openprocurement.auction.gong import utils


LOGGER = logging.getLogger("Auction Worker")


class BiddersServiceMixin(object):
    """Mixin class to work with bids data"""
    _bids_data = dd(list)

    def add_bid(self, current_stage, bid):
        LOGGER.info(
            '------------------ Adding bid ------------------',
        )
        # Updating auction document with bid data
        with utils.update_auction_document(self):
            bid['bidder_name'] = self.mapping.get(bid['bidder_id'], False)
            self._bids_data[bid['bidder_id']].append(deepcopy(bid))
            result = utils.prepare_results_stage(**bid)
            self.auction_document['stages'][current_stage].update(result)
            self.auction_document['results'].append(result)
        self.end_bid_stage(bid)

    def end_bid_stage(self, bid):
        request_id = generate_request_id()
        LOGGER.info(
            '---------------- End Bids Stage ----------------',
            extra={"JOURNAL_REQUEST_ID": request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_END_BID_STAGE}
        )

        # Cleaning up preplanned jobs
        SCHEDULER.remove_all_jobs()

        with utils.update_auction_document(self):
            # Creating new stages
            pause, main_round = self.prepare_auction_stages(
                utils.convert_datetime(bid['time']),
                self.auction_document
            )
            self.auction_document['stages'].append(pause)
            if main_round:
                self.auction_document['stages'].append(main_round)

            # Updating current stage
            self.auction_document["current_stage"] += 1

        LOGGER.info('---------------- Start stage {0} ----------------'.format(
            self.auction_document["current_stage"]),
            extra={"JOURNAL_REQUEST_ID": request_id,
                   "MESSAGE_ID": AUCTION_WORKER_SERVICE_START_NEXT_STAGE}
        )

        # Adding jobs to scheduler
        deadline = set_specific_hour(datetime.now(TIMEZONE), DEADLINE_HOUR)

        if main_round:
            round_start_date = utils.convert_datetime(main_round['start'])
            round_end_date = get_round_ending_time(
                round_start_date, ROUND_DURATION, deadline
            )
            self.add_pause_job(round_start_date)
            self.add_ending_main_round_job(round_end_date)
        else:
            self.add_ending_main_round_job(deadline)

    def filter_bids_keys(self, bids):
        filtered_bids_data = []
        for bid_info in bids:
            bid_info_result = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            bid_info_result["bidder_name"] = self.mapping[bid_info_result['bidder_id']]
            filtered_bids_data.append(bid_info_result)
        return filtered_bids_data

    def approve_bids_information(self):
        pass


class StagesServiceMixin(object):

    def prepare_auction_stages(self, stage_start, auction_data, fast_forward=False):
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

    def prepare_end_stage(self, start):
        stage = {
            'start': start.isoformat(),
            'type': END,
        }
        return stage
