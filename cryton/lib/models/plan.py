import os
from datetime import datetime
from typing import Union, Type, Optional

from django.core import exceptions as django_exc
from django.db import transaction, connections
from django.db.models.query import QuerySet
import yaml
from schema import Schema, Optional as SchemaOptional, SchemaError, And
from multiprocessing import Process

from cryton.cryton_rest_api.models import (
    PlanModel,
    PlanExecutionModel,
    StageExecutionModel
)
from cryton.etc import config

from cryton.lib.util import constants as co, exceptions, logger, scheduler_client, states as st, util
from cryton.lib.models import worker
from cryton.lib.models.stage import StageExecution, Stage
from django.utils import timezone


class Plan:
    def __init__(self, **kwargs):
        plan_model_id = kwargs.get('plan_model_id')
        if plan_model_id:
            try:
                self.model = PlanModel.objects.get(id=plan_model_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.PlanObjectDoesNotExist(plan_id=plan_model_id)
        else:
            self.model = PlanModel.objects.create(**kwargs, plan_dict=kwargs)
            self.__create_evidence_dir()

    def delete(self):
        self.model.delete()

    @property
    def model(self) -> Union[Type[PlanModel], PlanModel]:
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value: PlanModel):
        self.__model = value

    @property
    def name(self) -> str:
        return self.model.name

    @name.setter
    def name(self, value: str):
        model = self.model
        model.name = value
        model.save()

    @property
    def owner(self) -> str:
        return self.model.owner

    @owner.setter
    def owner(self, value: str):
        model = self.model
        model.owner = value
        model.save()

    @property
    def evidence_dir(self) -> str:
        return self.model.evidence_dir

    @evidence_dir.setter
    def evidence_dir(self, value: str):
        model = self.model
        model.evidence_dir = value
        model.save()

    @property
    def plan_info(self) -> dict:
        return self.model.plan_info

    @plan_info.setter
    def plan_info(self, value: dict):
        model = self.model
        model.plan_info = value
        model.save()

    @property
    def plan_dict(self) -> dict:
        return self.model.plan_dict

    @plan_dict.setter
    def plan_dict(self, value: dict):
        model = self.model
        model.plan_dict = value
        model.save()

    def __create_evidence_dir(self) -> None:
        dir_name = "plan_{:0>3}-{}".format(self.model.id, self.name.replace(" ", "_"))
        path = os.path.abspath(config.EVIDENCE_DIR + "/" + dir_name)
        os.makedirs(path, exist_ok=True)
        self.evidence_dir = path

    @staticmethod
    def filter(**kwargs) -> QuerySet:
        """
        List PlanModel objects fulfilling fields specified in kwargs.

        If no such fields are specified all objects are returned.

        :param kwargs: dict of field-value pairs to filter by
        :raises WrongParameterError: invalid field is specified
        :return: Queryset of PlanModel objects
        """
        if kwargs:
            try:
                return PlanModel.objects.filter(**kwargs)
            except django_exc.FieldError as ex:
                raise exceptions.WrongParameterError(message=ex)
        return PlanModel.objects.all()

    @staticmethod
    def validate(plan_dict) -> None:
        """
        Check if plan dictionary is valid

        :raises
            exceptions.PlanValidationError:
            exceptions.StageValidationError
            exceptions.StepValidationError
        :return: True if dictionary is valid
        """
        conf_schema = Schema({
            'name': str,
            SchemaOptional('owner'): str,
            SchemaOptional('evidence_dir'): str,
            SchemaOptional('plan_info'): dict,
            'stages': And(list, lambda l: len(l) > 0)
        })

        try:
            conf_schema.validate(plan_dict)
        except SchemaError as ex:
            raise exceptions.PlanValidationError(ex, plan_name=plan_dict.get('name'))

        for stage_dict in plan_dict.get('stages'):
            Stage.validate(stage_dict)


class PlanExecution:
    def __init__(self, **kwargs):
        plan_execution_id = kwargs.get("plan_execution_id")
        if plan_execution_id is not None:
            try:
                self.model = PlanExecutionModel.objects.get(id=plan_execution_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.PlanExecutionDoesNotExist(plan_execution_id=plan_execution_id)
        else:
            self.model = PlanExecutionModel.objects.create(**kwargs)

    def delete(self):
        self.model.delete()

    @property
    def model(self) -> Union[Type[PlanExecutionModel], PlanExecutionModel]:
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value: PlanExecutionModel):
        self.__model = value

    @property
    def state(self) -> str:
        return self.model.state

    @state.setter
    def state(self, value: str):
        with transaction.atomic():
            PlanExecutionModel.objects.select_for_update().get(id=self.model.id)
            if st.PlanStateMachine(self.model.id).validate_transition(self.state, value):
                logger.logger.debug("planexecution changed state", state_from=self.state, state_to=value)
                model = self.model
                model.state = value
                model.save()

    @property
    def schedule_time(self) -> Optional[datetime]:
        return self.model.schedule_time

    @schedule_time.setter
    def schedule_time(self, value: Optional[datetime]):
        model = self.model
        model.schedule_time = value
        model.save()

    @property
    def start_time(self) -> Optional[datetime]:
        return self.model.start_time

    @start_time.setter
    def start_time(self, value: Optional[datetime]):
        model = self.model
        model.start_time = value
        model.save()

    @property
    def pause_time(self) -> Optional[datetime]:
        return self.model.pause_time

    @pause_time.setter
    def pause_time(self, value: Optional[datetime]):
        model = self.model
        model.pause_time = value
        model.save()

    @property
    def finish_time(self) -> Optional[datetime]:
        return self.model.finish_time

    @finish_time.setter
    def finish_time(self, value: Optional[datetime]):
        model = self.model
        model.finish_time = value
        model.save()

    @property
    def aps_job_id(self) -> str:
        return self.model.aps_job_id

    @aps_job_id.setter
    def aps_job_id(self, value: Optional[str]):
        model = self.model
        model.aps_job_id = value
        model.save()

    @property
    def evidence_dir(self) -> Optional[str]:
        return self.model.evidence_dir

    @evidence_dir.setter
    def evidence_dir(self, value: str):
        model = self.model
        model.evidence_dir = value
        model.save()

    @property
    def all_stages_finished(self) -> bool:
        self.model.stage_executions.all()
        cond = self.model.stage_executions.all().exclude(state__in=[st.FINISHED]).exists()
        return not cond

    def __generate_evidence_dir(self) -> None:
        """
        Generate directory for storing execution evidence.
        :return: None
        """
        execution_evidence_dir = os.path.abspath("{}/run_{}/worker_{}".format(
            self.model.run.plan_model.evidence_dir, self.model.run_id, self.model.worker.name))

        os.makedirs(execution_evidence_dir, exist_ok=True)
        self.evidence_dir = execution_evidence_dir

    def schedule(self, schedule_time: datetime) -> None:
        """
        Schedule all plan's stages.
        :param schedule_time: Time to schedule to
        :return: None
        :raises
            :exception RuntimeError
        """
        # Check state
        logger.logger.debug("Scheduling Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_SCHEDULE_STATES)

        self.aps_job_id = scheduler_client.schedule_function("cryton.lib.models.plan:execution", [self.model.id],
                                                             schedule_time)

        if isinstance(self.aps_job_id, str):
            self.schedule_time = schedule_time.replace(tzinfo=timezone.utc)
            self.state = st.SCHEDULED
            logger.logger.info("planexecution scheduled", plan_name=self.model.plan_model.name, status='success')
        else:
            raise RuntimeError("Could not schedule planexecution")

    def execute(self) -> None:
        """
        Execute Plan. This method starts triggers.
        :return: None
        """
        logger.logger.debug("Executing Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_EXECUTE_STATES)

        self.start_time = timezone.now()
        self.state = st.RUNNING

        self.__generate_evidence_dir()

        # TODO: move queue preparation to worker creation?
        # Prepare rabbit queue
        worker_obj = worker.Worker(worker_model_id=self.model.worker_id)
        util.rabbit_prepare_queue(worker_obj.attack_q_name)
        util.rabbit_prepare_queue(worker_obj.agent_q_name)

        # Start triggers
        self.start_triggers()
        logger.logger.info("planexecution executed", plan_name=self.model.plan_model.name, status='success')

    def unschedule(self) -> None:
        """
        Unschedule plan execution.
        :return: None
        """
        logger.logger.debug("Unscheduling Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_UNSCHEDULE_STATES)

        scheduler_client.remove_job(self.aps_job_id)
        self.aps_job_id, self.schedule_time = None, None
        self.state = st.PENDING
        logger.logger.info("planexecution unscheduled", plan_name=self.model.plan_model.name, status='success')

    def reschedule(self, new_time: datetime) -> None:
        """
        Reschedule plan execution.
        :param new_time: Time to reschedule to
        :raises UserInputError: when provided time < present
        :return: None
        """
        logger.logger.debug("Rescheduling Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_RESCHEDULE_STATES)

        if new_time < timezone.now():
            raise exceptions.UserInputError("Time argument must be greater or equal than current time.", str(new_time))

        self.unschedule()
        self.schedule(new_time)
        logger.logger.info("planexecution rescheduled", plan_name=self.model.plan_model.name, status='success')

    def postpone(self, delta: str):
        """
        Postpone plan execution.
        :param delta: Time to postpone by, in [int]h[int]m[int]s format
        :raises UserInputError: when provided delta is in incorrect format
        :return: None
        """
        logger.logger.debug("Postponing Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_POSTPONE_STATES)

        original_schedule_time = self.schedule_time
        delta = util.parse_delta_to_datetime(delta)

        schedule_time = original_schedule_time + delta

        self.unschedule()
        self.schedule(schedule_time)
        logger.logger.info("planexecution postponed", plan_name=self.model.plan_model.name, status='success')

    def pause(self) -> None:
        """
        Pause plan execution.
        :return: None
        """
        logger.logger.debug("Pausing Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_PAUSE_STATES)

        self.state = st.PAUSING
        logger.logger.info("planexecution pausing", plan_name=self.model.plan_model.name, status='success')

        for stage_ex in self.model.stage_executions.all():  # Pause StageExecutions.
            StageExecution(stage_execution_id=stage_ex.id).trigger.pause()

        if not self.model.stage_executions.exclude(state__in=st.PLAN_STAGE_PAUSE_STATES).exists():
            self.state = st.PAUSED
            self.pause_time = timezone.now()
            logger.logger.info("planexecution paused", plan_name=self.model.plan_model.name, status='success')

    def unpause(self) -> None:
        logger.logger.debug("Unpausing Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_UNPAUSE_STATES)

        self.pause_time = None
        self.state = st.RUNNING

        for stage_execution_model in self.model.stage_executions.all():
            stage_ex = StageExecution(stage_execution_id=stage_execution_model.id)
            if stage_ex.model.stage_model.trigger_type == co.DELTA and stage_ex.state in st.STAGE_SCHEDULE_STATES:
                stage_ex.trigger.schedule()
            else:
                try:
                    stage_ex.trigger.unpause()
                except exceptions.StageInvalidStateError:
                    pass

        logger.logger.info("Plan unpaused", plan_id=self.model.plan_model_id)

    def validate_modules(self):
        """
        For each stage validate if worker is up, all modules are present and module args are correct.
        """
        logger.logger.debug("Plan modules validation started", plan_id=self.model.plan_model_id)

        for stage_execution_id in self.model.stage_executions.values_list('id', flat=True):
            stage_execution = StageExecution(stage_execution_id=stage_execution_id)
            stage_execution.validate_modules()

        return None

    def report_to_file(self, file_path: str = None) -> str:
        """
        Generate a report file for plan execution.

        :param file_path: Path to output file. If None, default is used
        :raises:
            IOError: If there is a problem with creating the report
            UnexpectedError: If there is any other problem
        :return: absolute file path
        """
        if file_path is None:
            file_path = "{}/planid-{}-runid-{}-executionid-{}.yaml".format(config.REPORT_DIR,
                                                                           self.model.run.plan_model_id,
                                                                           self.model.run_id, self.model.id)
        abs_path = os.path.abspath(file_path)

        with open(abs_path, "w") as out:
            report_dict = {"plan_name": self.model.run.plan_model.name}
            stages_dict = {}

            for stage_execution_model in self.model.stage_executions.all():
                steps_dict = {}

                for step_execution_model in stage_execution_model.step_executions.all():
                    step = step_execution_model.step_model
                    step_info = {"executor": step.executor,
                                 "step_type": step.step_type,
                                 co.STATE: step_execution_model.state, co.RESULT: step_execution_model.result,
                                 co.STD_OUT: step_execution_model.std_out, co.STD_ERR: step_execution_model.std_err,
                                 co.MOD_OUT: step_execution_model.mod_out, co.MOD_ERR: step_execution_model.mod_err}
                    steps_dict.update({step.name: step_info})
                stages_dict.update({stage_execution_model.stage_model.name: steps_dict})

            report_dict.update({"stages": stages_dict})
            yaml.dump(report_dict, out, indent=2, default_flow_style=False)

        return abs_path

    def start_triggers(self) -> None:
        """
        Start triggers for all execution stages.

        :return: None
        """
        logger.logger.debug("Starting triggers", plan_id=self.model.plan_model_id)
        for stage_execution_model in self.model.stage_executions.all():
            stage_execution = StageExecution(stage_execution_id=stage_execution_model.id)
            stage_execution.trigger.start()
            logger.logger.debug("Trigger started", plan_id=self.model.plan_model_id,
                                trigger=str(stage_execution.trigger))
        logger.logger.info("triggers started", plan_name=self.model.run.plan_model.name, status='success')

    def stop_triggers(self) -> None:
        """
        Stop triggers for all execution stages. Also unschedules delta types.

        :return: None
        """
        logger.logger.debug("Stopping triggers", plan_id=self.model.plan_model_id)
        for stage_execution_model in self.model.stage_executions.all():
            stage_execution = StageExecution(stage_execution_id=stage_execution_model.id)
            stage_execution.trigger.stop()
            logger.logger.debug("Trigger stopped", plan_id=self.model.plan_model_id,
                                trigger=str(stage_execution.trigger))
        logger.logger.info("triggers stopped", plan_name=self.model.run.plan_model.name, status='success')

    @staticmethod
    def filter(**kwargs) -> QuerySet:
        """
        List PlanExecutionModel objects fulfilling fields specified in kwargs.

        If no such fields are specified all objects are returned.

        :param kwargs: dict of field-value pairs to filter by
        :return: Queryset of PlanExecutionModel objects
        :raises WrongParameterError: invalid field is specified
        """
        if kwargs:
            try:
                return PlanExecutionModel.objects.filter(**kwargs)
            except django_exc.FieldError as ex:
                raise exceptions.WrongParameterError(message=ex)
        return PlanExecutionModel.objects.all()

    def report(self) -> dict:
        report_dict = dict()
        report_dict.update({'id': self.model.id, 'stage_name': self.model.plan_model.name, 'state': self.state,
                            'schedule_time': self.schedule_time, 'start_time': self.start_time,
                            'finish_time': self.finish_time, 'pause_time': self.pause_time,
                            'worker_id': self.model.worker_id, 'worker_name': self.model.worker.name,
                            'evidence_dir': self.evidence_dir})
        report_dict.update({'stage_executions': []})
        for stage_execution_obj in StageExecutionModel.objects.filter(plan_execution_id=self.model.id).order_by('id'):
            stage_ex_report = StageExecution(stage_execution_id=stage_execution_obj.id).report()
            report_dict['stage_executions'].append(stage_ex_report)

        return report_dict

    def kill(self) -> None:
        """
        Kill current PlanExecution and its StageExecutions
        :return: None
        """
        logger.logger.debug("Killing Plan", plan_id=self.model.plan_model_id)
        st.PlanStateMachine(self.model.id).validate_state(self.state, st.PLAN_KILL_STATES)

        processes = list()
        for stage_ex_model in self.model.stage_executions.filter(state__in=st.STAGE_KILL_STATES):
            stage_ex = StageExecution(stage_execution_id=stage_ex_model.id)
            process = Process(target=stage_ex.kill)
            processes.append(process)

        for stage_ex_model in self.model.stage_executions.filter(state__in=st.STAGE_UNSCHEDULE_STATES):
            stage_ex = StageExecution(stage_execution_id=stage_ex_model.id)
            process = Process(target=stage_ex.trigger.stop)
            processes.append(process)

        connections.close_all()  # close connections to force each process to create its own
        for process in processes:
            process.start()

        for process in processes:
            process.join()

        self.state = st.TERMINATED
        logger.logger.info("planexecution killed", plan_execution_id=self.model.id,
                           plan_name=self.model.plan_model.name, status='success')

        return None


def execution(plan_execution_id: int) -> None:
    """
    Create PlanExecution object and call its execute method
    :param plan_execution_id: desired PlanExecutionModel's ID
    :return: None
    """
    logger.logger.debug("Starting Plan execution", plan_execution_id=plan_execution_id)
    PlanExecution(plan_execution_id=plan_execution_id).execute()
    return None
