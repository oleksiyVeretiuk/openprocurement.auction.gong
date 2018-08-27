from zope.interface import (
    Interface,
    implementer,
)


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
    """
    _mapping = None

    def __init__(self, _):
        self._mapping = dict()

    def __getitem__(self, key):
        return self._mapping[key]

    def __setitem__(self, key, value):
        self._mapping[key] = value

    def get(self, key, default=None):
        return self._mapping.get(key, default)


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
