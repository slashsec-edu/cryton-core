from datetime import datetime
from schema import Schema, Optional, And, Or, Use
from pytz import timezone, all_timezones

from cryton.lib.triggers.trigger_base import TriggerTime


class TriggerDateTime(TriggerTime):
    arg_schema = Schema({
        Or('year', 'month', 'day', 'hour', 'minute', 'second', only_one=False): int,
        # validates that the supplied timezone is in pytz timezones in lowercase,
        # because pytz.timezone() function is not case sensitive
        Optional('timezone'): And(lambda x: x.lower() in map(lambda y: y.lower(), all_timezones),
                                  error='Invalid timezone')
        })

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
        today = datetime.utcnow()
        trigger_args = self.stage_execution.model.stage_model.trigger_args
        args_timezone = trigger_args.get('timezone')

        if args_timezone is not None and args_timezone.lower() != "utc":
            today = today.astimezone(timezone(args_timezone))

        schedule_datetime = datetime(year=trigger_args.get('year', today.year),
                                     month=trigger_args.get('month', today.month),
                                     day=trigger_args.get('day', today.day), hour=trigger_args.get('hour', 00),
                                     minute=trigger_args.get('minute', 00), second=trigger_args.get('second', 00))

        return schedule_datetime
