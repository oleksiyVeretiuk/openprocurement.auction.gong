# -*- coding: utf-8 -*-
from openprocurement.auction.includeme import _register
from openprocurement.auction.interfaces import IAuctionsServer

from .constants import AUCTION_SUBPATH


def kadastralProcedure(components):
    _register(components, 'kadastralProcedure')
    server = components.queryUtility(IAuctionsServer)
    server.add_url_rule(
        rule='/{}/<auction_doc_id>/<path:path>'.format(AUCTION_SUBPATH),
        endpoint=AUCTION_SUBPATH,
        view_func=server.view_functions['auctions_proxy'],
        methods=['GET', 'POST']
    )
