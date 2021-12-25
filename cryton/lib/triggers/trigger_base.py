from datetime import datetime
from django.utils import timezone
import schema

from cryton.lib.models import stage, worker, step
from cryton.lib.util import constants, states, logger
from cryton.lib.util.util import Rpc, exceptions
from cryton.lib.util import constants as co, exceptions, logger, scheduler_client, states as st


class TriggerBase:
    arg_schema = schema.Schema({})

    def __init__(self, stage_execution):  # Not using typing since it's causing loop import error
        """
        :param stage_execution: StageExecution's object
        """
        self.stage_execution: stage.StageExecution = stage_execution
        self.stage_execution_id = self.stage_execution.model.id
        self.trigger_args = self.stage_execution.model.stage_model.trigger_args

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def pause(self) -> None:
        pass

    def unpause(self) -> None:
        """
        Unpause stage execution.
        :return: None
        """
        logger.logger.info("stage execution unpausing", stage_execution_id=self.stage_execution_id)
        states.StageStateMachine(self.stage_execution.model.id).validate_state(self.stage_execution.state,
                                                                               states.STAGE_UNPAUSE_STATES)

        self.stage_execution.state = states.RUNNING
        self.stage_execution.pause_time = None

        if self.stage_execution.all_steps_finished:
            self.stage_execution.state = states.FINISHED
            self.stage_execution.finish_time = timezone.now()

            # start WAITING stages
            self.stage_execution.execute_subjects_to_dependency()
        else:
            for step_exec in self.stage_execution.model.step_executions.filter(state=states.PAUSED):
                step.StepExecution(step_execution_id=step_exec.id).execute()


class TriggerTime(TriggerBase):
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
        Runs unschedule() method.
        :return: None
        """
        try:
            self.unschedule()
        except exceptions.InvalidStateError as err:
            logger.logger.warning(str(err))

    def schedule(self) -> None:
        """
        Schedule stage execution.
        :return: None
        """

        st.StageStateMachine(self.stage_execution_id).validate_state(self.stage_execution.state,
                                                                     st.STAGE_SCHEDULE_STATES)
        if self.stage_execution.model.stage_model.trigger_type not in [co.DELTA, co.DATETIME]:
            raise exceptions.UnexpectedValue(
                'StageExecution with ID {} cannot be scheduled due to not having delta or datetime parameter'.format(
                    self.stage_execution_id)
            )

        schedule_time = self._create_schedule_time()
        self.stage_execution.schedule_time = schedule_time
        self.stage_execution.pause_time = None
        self.stage_execution.state = st.SCHEDULED
        self.stage_execution.aps_job_id = scheduler_client.schedule_function(
            "cryton.lib.models.stage:execution", [self.stage_execution_id], schedule_time)

        logger.logger.info("stage execution scheduled", stage_execution_id=self.stage_execution_id,
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

        logger.logger.info("stage execution unscheduled", stage_execution_id=self.stage_execution_id,
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
            logger.logger.info("stage execution pausing", stage_execution_id=self.stage_execution_id)
            self.stage_execution.state = st.PAUSING

    def _create_schedule_time(self) -> datetime:
        pass


class TriggerWorker(TriggerBase):
    def __init__(self, stage_execution):
        super().__init__(stage_execution)

    def _rpc_start(self, event_v: dict) -> None:
        """
        Start trigger's listener on worker.
        :param event_v: Special trigger parameters for listener on worker
        :return: None
        """
        worker_obj = worker.Worker(worker_model_id=self.stage_execution.model.plan_execution.worker.id)
        event_v.update(self.trigger_args)
        event_info = {constants.EVENT_T: constants.EVENT_START_TRIGGER, constants.EVENT_V: event_v}

        with Rpc() as rpc:
            response = rpc.call(worker_obj.control_q_name, event_info)

        if response is None:
            logger.logger.error("Couldn't start Stage Execution trigger - RPC timeout.",
                                stage_execution_id=self.stage_execution_id)
        elif response.get(constants.EVENT_V).get(constants.RETURN_CODE) == 0:
            logger.logger.info("Stage Execution trigger started.", stage_execution_id=self.stage_execution_id)
            self.stage_execution.trigger_id = response.get(constants.EVENT_V).get(constants.TRIGGER_ID)
            self.stage_execution.state = states.AWAITING
        else:
            logger.logger.info("Couldn't start Stage Execution trigger.", stage_execution_id=self.stage_execution_id)

    def _rpc_stop(self) -> None:
        """
        Stop trigger's listener on worker.
        :return: None
        """
        worker_obj = worker.Worker(worker_model_id=self.stage_execution.model.plan_execution.worker.id)
        event_info = {constants.EVENT_T: constants.EVENT_STOP_TRIGGER,
                      constants.EVENT_V: {constants.TRIGGER_ID: self.stage_execution.trigger_id}}

        with Rpc() as rpc:
            response = rpc.call(worker_obj.control_q_name, event_info)

        if response is None:
            logger.logger.error("Couldn't stop Stage Execution trigger - RPC timeout.",
                                stage_execution_id=self.stage_execution_id)
        elif response.get(constants.EVENT_V).get(constants.RETURN_CODE) == 0:
            logger.logger.info("Stage Execution trigger stopped.", stage_execution_id=self.stage_execution_id)
            self.stage_execution.trigger_id = None
        else:
            logger.logger.info("Couldn't stop Stage Execution trigger.", stage_execution_id=self.stage_execution_id)

    def pause(self) -> None:
        """
        Pause stage execution.
        :return: None
        """
        # If stage is RUNNING, set PAUSING state. It will be PAUSED once the currently
        # RUNNING step finished and listener gets it's return value
        if self.stage_execution.state == states.RUNNING:
            logger.logger.info("stage execution pausing", stage_execution_id=self.stage_execution_id)
            self.stage_execution.state = states.PAUSING
