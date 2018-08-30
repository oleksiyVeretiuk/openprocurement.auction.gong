# -*- coding: utf-8 -*-
from copy import deepcopy

from gevent.event import Event
from gevent.lock import BoundedSemaphore
from gevent.pywsgi import WSGIServer
from zope.interface import (
    Interface,
    implementer,
)


class ContextException(Exception):
    pass


class IContext(Interface):
    """
    Interface for objects which are serves as mapping for shared objects among
    other AuctionWorker components
    """
    def get(self, key, default=None):
        # Should return default value if key does not exist
        raise NotImplementedError


@implementer(IContext)
class DictContext(object):
    """
    Implementation of AuctionWorker context with simple python dictionary

    Attributes:
    _mapping: object, that actually stores all the shared data
    :type _mapping: dict

    types_to_return_copy_of: only copy of object stored in context mapping
    should be returned while getting if its type is defined in this sequence
    :type types_to_return_copy_of: tuple

    acceptable_fields: dictionary, which contains names of fields that could be
    stored in context mapping as a keys and type of value which this field should contain
    :type acceptable_fields: dict

    """
    _mapping = None
    types_to_return_copy_of = (list, dict, set)
    acceptable_fields = {
        'auction_data': {'type': dict},
        'auction_doc_id': {'type': str},
        'auction_document': {'type': dict},
        'audit': {'type': dict},
        'bidders_data': {'type': list},
        '_bids_data': {'type': dict},
        'bids_mapping': {'type': dict},
        'end_auction_event': {'type': Event},
        'server': {'type': WSGIServer},
        'server_actions': {'type': BoundedSemaphore},
        'worker_defaults': {'type': dict},
    }

    error_messages = {
        'fields': 'Only fields from this list can be stored in context: {}'.format(acceptable_fields.keys()),
        'types': 'Value of field {} must be {} type'
    }

    def __init__(self, _):
        self._mapping = dict()

    def __getitem__(self, key):
        value = self._mapping[key]
        # return copy of object if its type in types_to_return_copy_of sequence
        if isinstance(value, self.types_to_return_copy_of):
            return deepcopy(value)
        return value

    def __setitem__(self, key, value):
        # check if object could be stored in context mapping
        if key not in self.acceptable_fields:
            raise ContextException(self.error_messages['fields'])
        # check if object to store has proper type
        if not isinstance(value, self.acceptable_fields[key]['type']):
            raise ContextException(self.error_messages['types'].format(
                key, self.acceptable_fields[key]['type'])
            )
        self._mapping[key] = value

    def get(self, key, default=None):
        value = self._mapping.get(key, default)
        # return copy of object if its type in types_to_return_copy_of sequence
        if isinstance(value, self.types_to_return_copy_of):
            return deepcopy(value)
        return value


CONTEXT_MAPPING = {
    'dict': DictContext,
}


def prepare_context(config):
    context_type = config.get('type')
    context_class = CONTEXT_MAPPING.get(context_type, None)

    if context_class is None:
        raise AttributeError(
            'There is no context for such type {}. Available types {}'.format(
                context_type,
                CONTEXT_MAPPING.keys()
            )
        )

    context = context_class(config)
    return context
