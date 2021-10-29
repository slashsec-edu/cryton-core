from typing import List, Optional, Union, Type
from datetime import datetime, timedelta
from threading import Thread

from django.db.models.query import QuerySet
from django.core import exceptions as django_exc
from django.db import transaction
from django.utils import timezone

from cryton.cryton_rest_api.models import (
    RunModel,
    PlanModel,
    PlanExecutionModel,
    WorkerModel
)
from cryton.lib.util import exceptions, logger, scheduler_client, states as st
from cryton.lib.models import stage, plan, step

from dataclasses import dataclass, asdict


@dataclass
class RunReport:
    id: int
    plan_id: int
    plan_name: str
    state: str
    schedule_time: datetime
    start_time: datetime
    pause_time: datetime
    finish_time: datetime
    plan_executions: list


class Run:

    def __init__(self, **kwargs):
        """
        :param kwargs:
            run_id: int = None,
            plan_model_id: int
            workers_list: list
        """
        if kwargs.get('run_model_id'):
            run_id = kwargs.get('run_model_id')

            try:
                self.model = RunModel.objects.get(id=run_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.RunObjectDoesNotExist(run_id=run_id)
            self.workers = [pex.worker for pex in self.model.plan_executions.all()]
        else:
            plan_model_id = kwargs.get('plan_model_id')
            try:
                workers_list: list = kwargs.pop('workers_list')
            except KeyError:
                raise exceptions.ParameterMissingError(param_name='workers_list')
            try:
                PlanModel.objects.get(id=plan_model_id)
                self.workers = workers_list
            except django_exc.ObjectDoesNotExist:
                raise ValueError("PlanModel with id {} does not exist.".format(plan_model_id))
            self.model = RunModel.objects.create(**kwargs)
            try:
                self.__prepare(workers_list)
            except exceptions.StateTransitionError:
                self.delete()
                raise

    def delete(self):
        """
        Delete RunModel
        :return:
        """
        if self.model is not None:
            self.model.delete()

    @property
    def model(self) -> Union[Type[RunModel], RunModel]:
        """
        Get or set the RunModel.
        """
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value):
        self.__model = value

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
        """
        Get or set start time of RunModel.
        """
        return self.model.start_time

    @start_time.setter
    def start_time(self, value: Optional[datetime]):
        model = self.model
        model.start_time = value
        model.save()

    @property
    def pause_time(self) -> Optional[datetime]:
        """
        Get or set pause time of RunModel.
        """
        return self.model.pause_time

    @pause_time.setter
    def pause_time(self, value: Optional[datetime]):
        model = self.model
        model.pause_time = value
        model.save()

    @property
    def finish_time(self) -> Optional[datetime]:
        """
        Get or set pause time of RunModel.
        """
        return self.model.finish_time

    @finish_time.setter
    def finish_time(self, value: Optional[datetime]):
        model = self.model
        model.finish_time = value
        model.save()

    @property
    def state(self):
        """
        Get or set pause time of RunModel.
        """
        return self.model.state

    @state.setter
    def state(self, value: str):
        with transaction.atomic():
            RunModel.objects.select_for_update().get(id=self.model.id)
            if st.RunStateMachine(self.model.id).validate_transition(self.state, value):
                logger.logger.debug("run changed state", state_from=self.state, state_to=value)
                model = self.model
                model.state = value
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
    def workers(self) -> List[WorkerModel]:
        return self.__workers

    @workers.setter
    def workers(self, value: List[WorkerModel]):
        self.__workers = value

    @property
    def all_plans_finished(self) -> bool:
        cond = self.model.plan_executions.all().exclude(state__in=[st.FINISHED]).exists()
        return not cond

    @staticmethod
    def filter(**kwargs) -> QuerySet:

        """
        Get list of RunModel according to no or specified conditions
        :param kwargs: dict of parameters to filter by
        :return:
        """
        if kwargs:
            try:
                return RunModel.objects.filter(**kwargs)
            except django_exc.FieldError as ex:
                raise exceptions.WrongParameterError(message=ex)
        else:
            return RunModel.objects.all()

    def __prepare(self, workers_list: List[WorkerModel]) -> dict:
        """
        Creates Run, Execution and calls execute for each worker

        :param workers_list: List of WorkerModel objects
        :return: dict of objects
        example:
        ret.get(worker_id).get(plan_id).get('execution')
        ret.get(worker_id).get(plan_id).get(stage_id).get('execution')
        ret.get(worker_id).get(plan_id).get(stage_id).get(step_id).get('execution')
        """

        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_PREPARE_STATES)

        plan_execution_kwargs = {
            'run': self.model,
            'plan_model_id': self.model.plan_model_id
        }
        ret_dict = dict()
        if not workers_list:
            raise exceptions.WrongParameterError(message="Parameter cannot be empty.", param_name="workers_list")
        for worker_obj in workers_list:

            plan_execution_kwargs.update({'worker': worker_obj})
            plan_execution_obj = plan.PlanExecution(**plan_execution_kwargs)
            stage_execution_kwargs = {
                'plan_execution': plan_execution_obj.model
            }
            plan_dict = {'execution': plan_execution_obj}
            for stage_obj in self.model.plan_model.stages.all():
                stage_execution_kwargs.update({'stage_model': stage_obj})
                stage_execution_obj = stage.StageExecution(**stage_execution_kwargs)

                step_execution_kwargs = {
                    'stage_execution': stage_execution_obj.model
                }

                stage_dict = {'execution': stage_execution_obj}
                for step_obj in stage_obj.steps.all():
                    step_execution_kwargs.update({'step_model': step_obj})
                    step_execution_obj = step.StepExecution(**step_execution_kwargs)
                    stage_dict.update({step_obj.id: {
                        'execution': step_execution_obj
                    }})
                plan_dict.update({stage_obj.id: stage_dict})
            ret_dict.update({
                worker_obj.id: {
                    self.model.plan_model_id: plan_dict
                }
            })

        return ret_dict

    def report(self) -> dict:
        report_obj = RunReport(id=self.model.id, plan_id=self.model.plan_model.id,
                               plan_name=self.model.plan_model.name, state=self.state,
                               schedule_time=self.schedule_time, start_time=self.start_time,
                               finish_time=self.finish_time, pause_time=self.pause_time, plan_executions=[])

        for plan_execution_obj in PlanExecutionModel.objects.filter(run_id=self.model.id).order_by('id'):
            plan_ex_report = plan.PlanExecution(plan_execution_id=plan_execution_obj.id).report()
            report_obj.plan_executions.append(plan_ex_report)

        return asdict(report_obj)

    def schedule(self, schedule_time: datetime) -> None:
        """
        Schedules Run for specific time.
        :param schedule_time: Desired start time
        :return: None
        :raises
            :exception RuntimeError
        """
        logger.logger.debug("Scheduling Run", run_id=self.model.id)
        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_SCHEDULE_STATES)

        # Schedule execution
        self.aps_job_id = scheduler_client.schedule_function("cryton.lib.models.run:execution",
                                                             [self.model.id], schedule_time)
        if isinstance(self.aps_job_id, str):
            self.schedule_time = schedule_time.replace(tzinfo=timezone.utc)
            self.state = st.SCHEDULED
            logger.logger.info("run scheduled", run_id=self.model.id, status='success')
        else:
            raise RuntimeError("Could not schedule run")

    def unschedule(self) -> None:
        """
        Unschedules Run on specified workers
        :return: None
        """
        logger.logger.debug("Unscheduling Run", run_id=self.model.id)
        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_UNSCHEDULE_STATES)

        scheduler_client.remove_job(self.aps_job_id)
        self.aps_job_id, self.schedule_time = None, None
        self.state = st.PENDING
        logger.logger.info("run unscheduled", run_id=self.model.id, status='success')

    def reschedule(self, schedule_time: datetime) -> None:
        """
        Reschedules Run on specified WorkerModels
        :param schedule_time: Desired start time
        :return: None
        """
        logger.logger.debug("Rescheduling Run", run_id=self.model.id)
        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_RESCHEDULE_STATES)

        self.unschedule()
        self.schedule(schedule_time)

        logger.logger.info("run rescheduled", run_id=self.model.id, status='success')

    def pause(self) -> None:
        """
        Pauses Run on specified WorkerModels
        :return:
        """
        logger.logger.debug("Pausing Run", run_id=self.model.id)
        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_PAUSE_STATES)

        self.state = st.PAUSING
        logger.logger.info("run pausing", run_id=self.model.id, status='success')

        for plan_ex in self.model.plan_executions.all():
            plan.PlanExecution(plan_execution_id=plan_ex.id).pause()

        if not self.model.plan_executions.exclude(state__in=st.RUN_PLAN_PAUSE_STATES).exists():
            self.state = st.PAUSED
            self.pause_time = timezone.now()
            logger.logger.info("run paused", run_id=self.model.id, status='success')

    def unpause(self) -> None:
        """
        Unpauses Run on specified WorkerModels
        :return:
        """
        logger.logger.debug("Unpausing Run", run_id=self.model.id)
        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_UNPAUSE_STATES)

        self.pause_time = None
        self.state = st.RUNNING

        for plan_execution_model in self.model.plan_executions.all():
            plan.PlanExecution(plan_execution_id=plan_execution_model.id).unpause()

        logger.logger.info("run unpaused", run_id=self.model.id, status='success')

    def postpone(self, delta: timedelta) -> None:
        """
        Postpones Run on specified WorkerModels
        :param delta: Time delta
        :return:
        """
        logger.logger.debug("Postponing Run", run_id=self.model.id)
        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_POSTPONE_STATES)

        schedule_time = self.schedule_time + delta

        self.unschedule()
        self.schedule(schedule_time)

        logger.logger.info("run postponed", run_id=self.model.id, status='success')

    def execute(self) -> None:
        """
        Executes Run
        :return:
        """
        logger.logger.debug("Executing Run", run_id=self.model.id)
        # Check state
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_EXECUTE_STATES)

        self.start_time = timezone.now()
        self.state = st.RUNNING

        # Execute Plan on every Slave
        for worker_obj in self.workers:
            plan_execution_model = self.model.plan_executions.get(worker_id=worker_obj.id)
            plan.PlanExecution(plan_execution_id=plan_execution_model.id).execute()

        logger.logger.info("run executed", run_id=self.model.id, status='success')

    def kill(self) -> None:
        """
        Kill current Run and its PlanExecutions
        :return: None
        """
        logger.logger.debug("Killing Run", run_id=self.model.id)
        st.RunStateMachine(self.model.id).validate_state(self.state, st.RUN_KILL_STATES)
        threads = list()

        for plan_ex_obj in self.model.plan_executions.filter(state__in=st.PLAN_KILL_STATES):
            plan_ex = plan.PlanExecution(plan_execution_id=plan_ex_obj.id)
            thread = Thread(target=plan_ex.kill)
            threads.append(thread)

        for plan_ex_obj in self.model.plan_executions.filter(state__in=st.PLAN_UNSCHEDULE_STATES):
            plan_ex = plan.PlanExecution(plan_execution_id=plan_ex_obj.id)
            thread = Thread(target=plan_ex.unschedule)
            threads.append(thread)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        self.finish_time = timezone.now()
        self.state = st.TERMINATED
        logger.logger.info("run killed", run_id=self.model.id, status='success')

        return None


def execution(run_model_id: int) -> None:
    """
    Create Run object and call its execute method
    :param run_model_id: desired RunModel's ID
    :return: None
    """
    logger.logger.debug("Starting Run execution", run_id=run_model_id)
    Run(run_model_id=run_model_id).execute()
    return None
