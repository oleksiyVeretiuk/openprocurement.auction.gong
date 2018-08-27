# -*- coding: utf-8 -*-
import tempfile
import contextlib
from datetime import datetime, timedelta
from dateutil.tz import tzlocal

from gevent import monkey
monkey.patch_all()

import os.path
import json
from gevent.subprocess import check_output, sleep


PAUSE_SECONDS = timedelta(seconds=120)
PWD = os.path.dirname(os.path.realpath(__file__))
CWD = os.getcwd()


@contextlib.contextmanager
def update_auctionPeriod(path):
    with open(path) as file:
        data = json.loads(file.read())
    new_start_time = (datetime.now(tzlocal()) + PAUSE_SECONDS).isoformat()

    data['data']['auctionPeriod']['startDate'] = new_start_time

    with tempfile.NamedTemporaryFile(delete=False) as auction_file:
        json.dump(data, auction_file)
        auction_file.seek(0)
    yield auction_file.name
    auction_file.close()


def run_gong(tender_file_path):
    with open(tender_file_path) as _file:
        auction_id = json.load(_file).get('data', {}).get('id')
        if auction_id:
            with update_auctionPeriod(tender_file_path) as auction_file:
                check_output(TESTS['gong']['worker_cmd'].format(CWD, auction_id, auction_file).split())
    sleep(1)


TESTS = {
    "gong": {
        "worker_cmd": '{0}/bin/auction_worker planning {1}'
                      ' {0}/etc/auction_worker_defaults.yaml'
                      ' --planning_procerude partial_db --auction_info {2}',
        "runner": run_gong,
        'auction_worker_defaults': 'auction_worker_defaults:{0}/etc/auction_worker_defaults.yaml',
        'suite': PWD
    }
}


def includeme(tests):
    tests.update(TESTS)
