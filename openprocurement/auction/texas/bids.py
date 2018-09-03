# -*- coding: utf-8 -*-
import logging
from datetime import datetime

from zope.component import getGlobalSiteManager

from openprocurement.auction.utils import generate_request_id, sorting_by_amount
from openprocurement.auction.worker_core.constants import TIMEZONE

from openprocurement.auction.texas import utils
from openprocurement.auction.texas.context import IContext
from openprocurement.auction.texas.constants import ROUND_DURATION, DEADLINE_HOUR
from openprocurement.auction.texas.database import IDatabase
from openprocurement.auction.texas.scheduler import IJobService
from openprocurement.auction.texas.scheduler import SCHEDULER
from openprocurement.auction.texas.journal import (
    AUCTION_WORKER_SERVICE_END_BID_STAGE,
    AUCTION_WORKER_SERVICE_START_NEXT_STAGE
)
from openprocurement.auction.texas.utils import set_specific_hour, get_round_ending_time, \
    approve_auction_protocol_info_on_bids_stage

LOGGER = logging.getLogger("Auction Worker Texas")


class BidsHandler(object):
    """
    Class for work with bids data
    """
    def __init__(self):
        gsm = getGlobalSiteManager()
        self.context = gsm.queryUtility(IContext)
        self.database = gsm.queryUtility(IDatabase)
        self.job_service = gsm.queryUtility(IJobService)

    def add_bid(self, current_stage, bid):
        LOGGER.info(
            '------------------ Adding bid ------------------',
        )
        # Updating auction document with bid data
        with utils.update_auction_document(self.context, self.database) as auction_document:
            bid['bidder_name'] = self.context['bids_mapping'].get(bid['bidder_id'], False)
            result = utils.prepare_results_stage(**bid)
            auction_document['stages'][current_stage].update(result)
            results = auction_document['results']
            bid_index = next((i for i, res in enumerate(results)
                              if res['bidder_id'] == bid['bidder_id']), None)
            if bid_index is not None:
                results[bid_index] = result
            else:
                results.append(result)
            auction_document['results'] = sorting_by_amount(results)
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

        approve_auction_protocol_info_on_bids_stage(self.context)

        with utils.update_auction_document(self.context, self.database) as auction_document:
            # Creating new stages
            bid_document = {
                'value': {'amount': bid['amount']},
                'minimalStep': auction_document['minimalStep']
            }

            pause, main_round = utils.prepare_auction_stages(
                utils.convert_datetime(bid['time']),
                bid_document
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
