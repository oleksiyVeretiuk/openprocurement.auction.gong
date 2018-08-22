# -*- coding: utf-8 -*-
from openprocurement.auction.includeme import _register
from openprocurement.auction.interfaces import IAuctionsServer


def kadastralProcedure(components):
    _register(components, 'kadastralProcedure')
    server = components.queryUtility(IAuctionsServer)
    server.add_url_rule(
        '/auctions/<auction_doc_id>/<path:path>', 'auctions',
        server.view_functions['auctions_proxy'], methods=['GET', 'POST']
    )
