# -*- coding: utf-8 -*-
import logging
from collections import defaultdict as dd
from copy import deepcopy
from datetime import datetime

from zope.component import getGlobalSiteManager

from openprocurement.auction.utils import generate_request_id
from openprocurement.auction.worker_core.constants import TIMEZONE

from openprocurement.auction.gong import utils
from openprocurement.auction.gong.context import IContext
from openprocurement.auction.gong.constants import ROUND_DURATION, BIDS_KEYS_FOR_COPY, DEADLINE_HOUR
from openprocurement.auction.gong.database import IDatabase
from openprocurement.auction.gong.scheduler import IJobService
from openprocurement.auction.gong.scheduler import SCHEDULER
from openprocurement.auction.gong.journal import (
    AUCTION_WORKER_SERVICE_END_BID_STAGE,
    AUCTION_WORKER_SERVICE_START_NEXT_STAGE
)
from openprocurement.auction.gong.utils import set_specific_hour, get_round_ending_time

LOGGER = logging.getLogger("Auction Worker Gong")


class BidsHandler(object):
    """
    Class for work with bids data
    """
    def __init__(self):
        gsm = getGlobalSiteManager()
        self.context = gsm.queryUtility(IContext)
        self.database = gsm.queryUtility(IDatabase)
        self.job_service = gsm.queryUtility(IJobService)

        self.context['bids_mapping'] = {}  # TODO: should be created during Auction initialization
        self.context['_bids_data'] = dd(list)

    def add_bid(self, current_stage, bid):
        LOGGER.info(
            '------------------ Adding bid ------------------',
        )
        # Updating auction document with bid data
        with utils.update_auction_document(self.context, self.database) as auction_document:
            bid['bidder_name'] = self.context['bids_mapping'].get(bid['bidder_id'], False)
            self.context['_bids_data'][bid['bidder_id']].append(deepcopy(bid))
            result = utils.prepare_results_stage(**bid)
            auction_document['stages'][current_stage].update(result)
            auction_document['results'].append(result)
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

        with utils.update_auction_document(self.context, self.database) as auction_document:
            # Creating new stages

            pause, main_round = utils.prepare_auction_stages(
                utils.convert_datetime(bid['time']),
                auction_document
            )

            auction_document['stages'].append(pause)
            if main_round:
                auction_document['stages'].append(main_round)

            # Updating current stage
            auction_document["current_stage"] += 1

        LOGGER.info('---------------- Start stage {0} ----------------'.format(
            self.context['auction_document']["current_stage"]),
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

            self.job_service.add_pause_job(round_start_date)
            self.job_service.add_ending_main_round_job(round_end_date)
        else:
            self.job_service.add_ending_main_round_job(deadline)

    def filter_bids_keys(self, bids):
        filtered_bids_data = []
        for bid_info in bids:
            bid_info_result = {key: bid_info[key] for key in BIDS_KEYS_FOR_COPY}
            bid_info_result["bidder_name"] = self.context['bids_mapping'][bid_info_result['bidder_id']]
            filtered_bids_data.append(bid_info_result)
        return filtered_bids_data

    def approve_bids_information(self):
        pass
