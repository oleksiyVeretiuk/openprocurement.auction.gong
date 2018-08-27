# -*- coding: utf-8 -*-
from gevent import monkey
monkey.patch_all()

import argparse
import logging.config
import os
import sys

import yaml
from gevent.lock import BoundedSemaphore
from zope.component.globalregistry import getGlobalSiteManager

from openprocurement.auction.worker_core import constants as C

from openprocurement.auction.gong.auction import Auction, SCHEDULER
from openprocurement.auction.gong.context import prepare_context, IContext
from openprocurement.auction.gong.database import prepare_database, IDatabase
from openprocurement.auction.gong.datasource import prepare_datasource, IDataSource
from openprocurement.auction.gong.scheduler import prepare_job_service, IJobService


def register_utilities(worker_config, auction_id):
    gsm = getGlobalSiteManager()

    # Register datasource
    datasource_config = worker_config.get('datasource', {})
    datasource_config.update(auction_id=auction_id)
    datasource = prepare_datasource(datasource_config)
    gsm.registerUtility(datasource, IDataSource)

    # Register database
    database_config = worker_config.get('database', {})
    database = prepare_database(database_config)
    gsm.registerUtility(database, IDatabase)

    # Register context
    context_config = worker_config.get('context', {})
    context = prepare_context(context_config)
    context['auction_doc_id'] = auction_id
    context['worker_defaults'] = worker_config
    # Initializing semaphore which is used for locking WSGI server actions
    # during applying bids or updating auction document
    context['server_actions'] = BoundedSemaphore()
    gsm.registerUtility(context, IContext)

    # Register JobService
    job_service = prepare_job_service()
    gsm.registerUtility(job_service, IJobService)


def main():
    parser = argparse.ArgumentParser(description='---- Auction ----')
    parser.add_argument('cmd', type=str, help='')
    parser.add_argument('auction_doc_id', type=str, help='auction_doc_id')
    parser.add_argument('auction_worker_config', type=str,
                        help='Auction Worker Configuration File')
    parser.add_argument('--with_api_version', type=str, help='Tender Api Version')
    parser.add_argument('--planning_procerude', type=str, help='Override planning procerude',
                        default=None, choices=[None, C.PLANNING_FULL, C.PLANNING_PARTIAL_DB, C.PLANNING_PARTIAL_CRON])
    parser.add_argument('-debug', dest='debug', action='store_const',
                        const=True, default=False,
                        help='Debug mode for auction')

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

    register_utilities(worker_defaults, args.auction_doc_id)
    auction = Auction(args.auction_doc_id, worker_defaults=worker_defaults, debug=args.debug)
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
