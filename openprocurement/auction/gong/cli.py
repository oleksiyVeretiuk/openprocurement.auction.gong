# -*- coding: utf-8 -*-
from gevent import monkey
monkey.patch_all()

import argparse
import logging.config
import json
import yaml
import sys
import os

from openprocurement.auction.gong.auction import Auction, SCHEDULER
from openprocurement.auction.worker_core import constants as C


def main():
    parser = argparse.ArgumentParser(description='---- Auction ----')
    parser.add_argument('cmd', type=str, help='')
    parser.add_argument('auction_doc_id', type=str, help='auction_doc_id')
    parser.add_argument('auction_worker_config', type=str,
                        help='Auction Worker Configuration File')
    parser.add_argument('--auction_info', type=str, help='Auction File')
    parser.add_argument('--auction_info_from_db', type=str, help='Get auction data from local database')
    parser.add_argument('--with_api_version', type=str, help='Tender Api Version')
    parser.add_argument('--planning_procerude', type=str, help='Override planning procerude',
                        default=None, choices=[None, C.PLANNING_FULL, C.PLANNING_PARTIAL_DB, C.PLANNING_PARTIAL_CRON])

    args = parser.parse_args()

    if os.path.isfile(args.auction_worker_config):
        worker_defaults = yaml.load(open(args.auction_worker_config))
        if args.with_api_version:
            worker_defaults['resource_api_version'] = args.with_api_version
        if args.cmd != 'cleanup':
            worker_defaults['handlers']['journal']['TENDER_ID'] = args.auction_doc_id

        worker_defaults['handlers']['journal']['TENDERS_API_VERSION'] = worker_defaults['resource_api_version']
        worker_defaults['handlers']['journal']['TENDERS_API_URL'] = worker_defaults['resource_api_server']

        logging.config.dictConfig(worker_defaults)
    else:
        print "Auction worker defaults config not exists!!!"
        sys.exit(1)

    if args.auction_info_from_db:
        auction_data = {'mode': 'test'}
    elif args.auction_info:
        auction_data = json.load(open(args.auction_info))
    else:
        auction_data = None

    auction = Auction(args.auction_doc_id,
                      worker_defaults=worker_defaults,
                      auction_data=auction_data,
                      )
    if args.cmd == 'run':
        SCHEDULER.start()
        auction.schedule_auction()
        auction.wait_to_end()
        SCHEDULER.shutdown()
    elif args.cmd == 'planning':
        auction.prepare_auction_document()
    elif args.cmd == 'announce':
        auction.post_announce()
    elif args.cmd == 'cancel':
        auction.cancel_auction()
    elif args.cmd == 'reschedule':
        auction.reschedule_auction()
    elif args.cmd == 'prepare_audit':
        auction.post_audit()

if __name__ == "__main__":
    main()
