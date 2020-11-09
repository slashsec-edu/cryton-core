from enum import Enum, EnumMeta

from cryton.lib.exceptions import TriggerTypeDoesNotExist
from cryton.lib.triggers import (
    trigger_delta,
    trigger_http_listener
)


class TriggerTypeMeta(EnumMeta):
    """
    Overrides base metaclass of Enum in order to support custom exception when accessing not present item.
    """
    def __getitem__(self, item):
        try:
            return super().__getitem__(item)
        except KeyError:
            raise TriggerTypeDoesNotExist(item, [trigger.name for trigger in list(self)])


class TriggerType(Enum, metaclass=TriggerTypeMeta):
    """
    Keys according to lib.constants
    """
    delta = trigger_delta.TriggerDelta
    HTTPListener = trigger_http_listener.TriggerHTTPListener
