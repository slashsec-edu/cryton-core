from datetime import datetime, timedelta

import schema

from cryton.lib.util import constants as co, exceptions, logger, scheduler_client, states as st
from cryton.lib.models import stage, step
from django.utils import timezone


class TriggerDelta:
    """
    'Trigger type 'delta'
    """
    arg_schema = schema.Schema({schema.Or('hours', 'minutes', 'seconds', only_one=False): int})

    def __init__(self, **kwargs):
        """
        :param kwargs:
            stage_execution_id: int
        """
        self.stage_execution_id = kwargs.get("stage_execution_id")
        self.stage_execution_obj = stage.StageExecution(stage_execution_id=self.stage_execution_id)
        self.trigger_args = self.stage_execution_obj.model.stage_model.trigger_args

    def start(self) -> str:
        """
        Runs schedule() method
        :return: APS id
        """
        return self.schedule()

    def stop(self) -> None:
        """
        Runs unschedule() method
        :return:
        """
        return self.unschedule()

    def schedule(self) -> str:
        """
        Schedule stage execution
        :return: APS id
        """

        st.StageStateMachine(self.stage_execution_id).validate_state(self.stage_execution_obj.state,
                                                                     st.STAGE_SCHEDULE_STATES)
        if self.stage_execution_obj.model.stage_model.trigger_type != co.DELTA:
            raise exceptions.UnexpectedValue(
                'StageExecution with ID {} cannot be scheduled due to not having delta parameter'.format(
                    self.stage_execution_id)
            )

        schedule_time = self.__create_schedule_time()
        self.stage_execution_obj.schedule_time = schedule_time
        self.stage_execution_obj.pause_time = None
        self.stage_execution_obj.state = st.SCHEDULED
        self.stage_execution_obj.aps_job_id = scheduler_client.schedule_function(
            "cryton.lib.models.stage:execution", [self.stage_execution_id], schedule_time)

        logger.logger.info("stagexecution scheduled", stage_execution_id=self.stage_execution_id,
                           stage_name=self.stage_execution_obj.model.stage_model.name, status='success')

        return self.stage_execution_obj.aps_job_id

    def unschedule(self) -> None:
        """
        Unschedule StageExecution from a APScheduler
        :raises:
            ConnectionRefusedError
        :return: None
        """
        st.StageStateMachine(self.stage_execution_id).validate_state(self.stage_execution_obj.state,
                                                                     st.STAGE_UNSCHEDULE_STATES)

        scheduler_client.remove_job(self.stage_execution_obj.aps_job_id)
        self.stage_execution_obj.aps_job_id, self.stage_execution_obj.schedule_time = None, None
        self.stage_execution_obj.state = st.PENDING

        logger.logger.info("stagexecution unscheduled", stage_execution_id=self.stage_execution_id,
                           stage_name=self.stage_execution_obj.model.stage_model.name, status='success')

        return None

    def pause(self) -> None:
        """
        Pause stage execution
        :return:
        """
        if self.stage_execution_obj.state in st.STAGE_UNSCHEDULE_STATES:
            self.unschedule()
            self.stage_execution_obj.pause_time = timezone.now()

        # If stage is RUNNING, set PAUSING state. It will be PAUSED once the currently
        # RUNNING step finished and listener gets it's return value
        elif self.stage_execution_obj.state == st.RUNNING:
            logger.logger.info("stageexecution pausing", stage_execution_id=self.stage_execution_id)
            self.stage_execution_obj.state = st.PAUSING

        return

    def unpause(self) -> None:
        """
        Unpause stage execution (by issuing 'execute' call)
        :return:
        """
        self.stage_execution_obj.state = st.RUNNING
        self.stage_execution_obj.pause_time = None

        if self.stage_execution_obj.all_steps_finished:
            self.stage_execution_obj.state = st.FINISHED
            self.stage_execution_obj.finish_time = timezone.now()

            # start WAITING stages
            self.stage_execution_obj.execute_subjects_to_dependency()
            return

        for step_exec in self.stage_execution_obj.model.step_executions.filter(state=st.PAUSED):
            step.StepExecution(step_execution_id=step_exec.id).execute()
        return

    def __create_schedule_time(self) -> datetime:
        """
        Create Stage's start time
        :return: Stage's start time
        """
        trigger_args = self.stage_execution_obj.model.stage_model.trigger_args
        delta = timedelta(
            hours=trigger_args.get('hours', 0), minutes=trigger_args.get('minutes', 0),
            seconds=trigger_args.get('seconds', 0)
        )

        if self.stage_execution_obj.pause_time:
            additional_time = self.stage_execution_obj.model.plan_execution.start_time + delta - \
                              self.stage_execution_obj.pause_time
        else:
            additional_time = delta

        schedule_time = timezone.now() + additional_time

        return schedule_time
