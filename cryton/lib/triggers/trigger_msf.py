from schema import Schema, Optional, Or

from cryton.lib.triggers.trigger_base import TriggerWorker
from cryton.lib.util import constants
from cryton.etc import config


class TriggerMSF(TriggerWorker):
    arg_schema = Schema({
        'host': str,
        'port': int,
        "exploit": str,
        Optional("exploit_arguments"): {
            Optional(str): Or(str, int)
        },
        "payload": str,
        Optional("payload_arguments"): {
            Optional(str): Or(str, int)
        }
    })

    def __init__(self, stage_execution):
        """
        :param stage_execution: StageExecution's object
        """
        super().__init__(stage_execution)

    def start(self) -> None:
        """
        Start MSF listener.
        :return: None
        """
        event_v = {constants.TRIGGER_TYPE: "MSF", constants.REPLY_TO: config.Q_EVENT_RESPONSE_NAME}
        self._rpc_start(event_v)

    def stop(self) -> None:
        """
        Stop MSF listener.
        :return: None
        """
        self._rpc_stop()
