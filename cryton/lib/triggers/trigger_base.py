import schema
from django.utils import timezone

from cryton.lib.models import stage, worker, step
from cryton.lib.util import constants, states, logger
from cryton.lib.util.util import Rpc, exceptions


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
        logger.logger.info("stageexecution unpausing", stage_execution_id=self.stage_execution_id)
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
            logger.logger.info("stageexecution pausing", stage_execution_id=self.stage_execution_id)
            self.stage_execution.state = states.PAUSING
