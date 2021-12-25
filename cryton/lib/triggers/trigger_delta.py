from datetime import datetime, timedelta
from django.utils import timezone
import schema

from cryton.lib.triggers.trigger_base import TriggerTime


class TriggerDelta(TriggerTime):
    arg_schema = schema.Schema({schema.Or('hours', 'minutes', 'seconds', only_one=False): int})

    def __init__(self, stage_execution):
        """
        :param stage_execution: StageExecution's object
        """
        super().__init__(stage_execution)

    def _create_schedule_time(self) -> datetime:
        """
        Create Stage's start time.
        :return: Stage's start time
        """
        trigger_args = self.stage_execution.model.stage_model.trigger_args
        delta = timedelta(hours=trigger_args.get('hours', 0), minutes=trigger_args.get('minutes', 0),
                          seconds=trigger_args.get('seconds', 0))

        if self.stage_execution.pause_time:
            additional_time = self.stage_execution.model.plan_execution.start_time + delta - \
                              self.stage_execution.pause_time
        else:
            additional_time = delta

        schedule_time = timezone.now() + additional_time
        return schedule_time
