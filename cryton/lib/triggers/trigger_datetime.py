from datetime import datetime
from schema import Schema, Optional, And, Or
import pytz

from cryton.lib.util import util
from cryton.lib.triggers.trigger_base import TriggerTime


class TriggerDateTime(TriggerTime):
    arg_schema = Schema({
        Or('year', 'month', 'day', 'hour', 'minute', 'second', only_one=False): int,
        # validates that the supplied timezone is in pytz timezones
        Optional('timezone'): And(lambda x: x in pytz.all_timezones, error='Invalid timezone')
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

        trigger_args = self.stage_execution.model.stage_model.trigger_args
        args_timezone = trigger_args.get('timezone', 'UTC')

        if args_timezone is None:
            today = datetime.utcnow()
        else:
            today = datetime.now(pytz.timezone(args_timezone))

        schedule_datetime = datetime(year=trigger_args.get('year', today.year),
                                     month=trigger_args.get('month', today.month),
                                     day=trigger_args.get('day', today.day), hour=trigger_args.get('hour', 00),
                                     minute=trigger_args.get('minute', 00), second=trigger_args.get('second', 00))

        if schedule_datetime.tzinfo != pytz.utc:
            schedule_datetime = util.convert_to_utc(schedule_datetime, args_timezone, True)

        return schedule_datetime
