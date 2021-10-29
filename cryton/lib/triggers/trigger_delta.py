from datetime import datetime, timedelta
from django.utils import timezone
import schema

from cryton.lib.util import constants as co, exceptions, logger, scheduler_client, states as st
from cryton.lib.triggers.trigger_base import TriggerBase


class TriggerDelta(TriggerBase):
    arg_schema = schema.Schema({schema.Or('hours', 'minutes', 'seconds', only_one=False): int})

    def __init__(self, stage_execution):
        """
        :param stage_execution: StageExecution's object
        """
        super().__init__(stage_execution)

    def start(self) -> None:
        """
        Runs schedule() method.
        :return: None
        """
        self.schedule()

    def stop(self) -> None:
        """
        Checks if StageExecution is in final state and runs unschedule() method.
        :return: None
        """
        if self.stage_execution.state not in st.STAGE_FINAL_STATES:
            self.unschedule()

    def schedule(self) -> None:
        """
        Schedule stage execution.
        :return: None
        """

        st.StageStateMachine(self.stage_execution_id).validate_state(self.stage_execution.state,
                                                                     st.STAGE_SCHEDULE_STATES)
        if self.stage_execution.model.stage_model.trigger_type != co.DELTA:
            raise exceptions.UnexpectedValue(
                'StageExecution with ID {} cannot be scheduled due to not having delta parameter'.format(
                    self.stage_execution_id)
            )

        schedule_time = self.__create_schedule_time()
        self.stage_execution.schedule_time = schedule_time
        self.stage_execution.pause_time = None
        self.stage_execution.state = st.SCHEDULED
        self.stage_execution.aps_job_id = scheduler_client.schedule_function(
            "cryton.lib.models.stage:execution", [self.stage_execution_id], schedule_time)

        logger.logger.info("stagexecution scheduled", stage_execution_id=self.stage_execution_id,
                           stage_name=self.stage_execution.model.stage_model.name, status='success')

    def unschedule(self) -> None:
        """
        Unschedule StageExecution from a APScheduler.
        :raises:
            ConnectionRefusedError
        :return: None
        """
        st.StageStateMachine(self.stage_execution_id).validate_state(self.stage_execution.state,
                                                                     st.STAGE_UNSCHEDULE_STATES)

        scheduler_client.remove_job(self.stage_execution.aps_job_id)
        self.stage_execution.aps_job_id, self.stage_execution.schedule_time = None, None
        self.stage_execution.state = st.PENDING

        logger.logger.info("stagexecution unscheduled", stage_execution_id=self.stage_execution_id,
                           stage_name=self.stage_execution.model.stage_model.name, status='success')

    def pause(self) -> None:
        """
        Pause stage execution.
        :return: None
        """
        if self.stage_execution.state in st.STAGE_UNSCHEDULE_STATES:
            self.unschedule()
            self.stage_execution.pause_time = timezone.now()

        # If stage is RUNNING, set PAUSING state. It will be PAUSED once the currently
        # RUNNING step finished and listener gets it's return value
        elif self.stage_execution.state == st.RUNNING:
            logger.logger.info("stageexecution pausing", stage_execution_id=self.stage_execution_id)
            self.stage_execution.state = st.PAUSING

    def __create_schedule_time(self) -> datetime:
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
