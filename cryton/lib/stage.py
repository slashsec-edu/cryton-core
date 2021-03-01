from typing import Union, Type, Optional
from datetime import datetime
from multiprocessing import Process
from schema import Schema, SchemaError, Or, Optional as SchemaOptional
import copy
from threading import Thread

from django.db.models.query import QuerySet
from django.core import exceptions as django_exc
from django.db import transaction, connections

from cryton.cryton_rest_api.models import (
    StageModel,
    StageExecutionModel,
    StepExecutionModel,
    DependencyModel
)
from cryton.lib import (
    exceptions,
    states as st,
    constants as co,
    logger,
    util
)

from cryton.lib.triggers import (
    triggers,
)

from cryton.lib.step import (
    StepExecution,
    Step
)

from cryton.etc import config


class Stage:
    def __init__(self, **kwargs):
        """
        :param kwargs:
            stage_model_id: int = None,
            plan_model_id: int = None,
            name: str = None,
            executor: str = None,
            trigger_type: str = None,
            trigger_args: dict = None
        """
        stage_model_id = kwargs.get('stage_model_id')
        if stage_model_id:
            try:
                self.model = StageModel.objects.get(id=stage_model_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.StageObjectDoesNotExist(
                    "StageModel with id {} does not exist.".format(stage_model_id), stage_model_id
                )

        else:
            stage_obj_arguments = copy.deepcopy(kwargs)
            stage_obj_arguments.pop('depends_on', None)
            self.model = StageModel.objects.create(**stage_obj_arguments)

    def delete(self):
        self.model.delete()

    @property
    def model(self) -> Union[Type[StageModel], StageModel]:
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value: StageModel):
        self.__model = value

    @property
    def name(self) -> str:
        return self.model.name

    @name.setter
    def name(self, value):
        model = self.model
        model.name = value
        model.save()

    @property
    def executor(self) -> str:
        return self.model.executor

    @executor.setter
    def executor(self, value):
        model = self.model
        model.executor = value
        model.save()

    @property
    def trigger_type(self) -> str:
        return self.model.trigger_type

    @trigger_type.setter
    def trigger_type(self, value: str):
        model = self.model
        model.trigger_type = value
        model.save()

    @property
    def trigger_args(self) -> dict:
        return self.model.trigger_args

    @trigger_args.setter
    def trigger_args(self, value: dict):
        model = self.model
        model.trigger_args = value
        model.save()

    @property
    def final_steps(self) -> QuerySet:
        steps_list = Step.filter(stage_model_id=self.model.id, is_final=True)
        return steps_list

    @property
    def execution_list(self) -> QuerySet:
        """
        Returns StageExecutionModel QuerySet. If the latest is needed, use '.latest()' on result.
        :return: QuerySet of StageExecutionModel
        """
        return StageExecutionModel.objects.filter(stage_model_id=self.model.id)

    @staticmethod
    def filter(**kwargs) -> QuerySet:
        """
        :param kwargs: dict of parameters to filter by
        :return: QuerySet of StageModel
        """
        if kwargs:
            try:
                return StageModel.objects.filter(**kwargs)
            except django_exc.FieldError as e:
                raise exceptions.WrongParameterError(e)
        else:
            return StageModel.objects.all()

    @staticmethod
    def _dfs_reachable(visited: set, completed: set, nodes_pairs: dict, node: str) -> set:
        """

        Depth first search of reachable nodes

        :param visited: set of visited nodes
        :param completed: set of completed nodes
        :param nodes_pairs: stage successors representation ({parent: [successors]})
        :param node: current node
        :return:
        """
        if node in visited and node not in completed:
            raise exceptions.StageCycleDetected("Stage cycle detected.")
        if node in completed:
            return completed
        visited.add(node)
        for neighbour in nodes_pairs.get(node, []):
            Stage._dfs_reachable(visited, completed, nodes_pairs, neighbour)
        completed.add(node)
        # completed and visited should be the same
        return completed

    @staticmethod
    def validate(stage_dict) -> bool:
        """
        Check if Stage's dictionary is valid
        :raises
            exceptions.StageValidationError
            exceptions.StepValidationError
        :return True if Stage's dictionary is valid
        """
        conf_schema = Schema({
            'name': str,
            'trigger_type': Or(*[trigger.name for trigger in list(triggers.TriggerType)]),
            'trigger_args': dict,
            'steps': list,
            SchemaOptional('depends_on'): list

        })

        try:
            conf_schema.validate(stage_dict)
        except SchemaError as ex:
            raise exceptions.StageValidationError(ex, stage_name=stage_dict.get('name'))

        trigger = triggers.TriggerType[stage_dict.get('trigger_type')].value
        arg_schema = trigger.arg_schema
        try:
            arg_schema.validate(stage_dict.get('trigger_args'))
        except SchemaError as ex:
            raise exceptions.StageValidationError(ex, stage_name=stage_dict.get('name'))

        if not stage_dict.get('steps'):
            raise exceptions.StageValidationError(
                'Stage cannot exist without steps!', stage_name=stage_dict.get('name'))

        steps_graph = dict()
        init_steps = set()
        all_steps_set = set()
        all_successors_set = set()
        for step_dict in stage_dict.get('steps'):
            # Get needed information for reachability check
            if step_dict.get('is_init'):
                init_steps.add(step_dict.get('name'))
            succ_set = set()
            for succ_obj in step_dict.get('next', []):
                step_successors = succ_obj.get('step')
                if not isinstance(step_successors, list):
                    step_successors = [step_successors]
                succ_set.update(step_successors)
                steps_graph.update({step_dict.get('name'): succ_set})
            all_successors_set.update(succ_set)
            all_steps_set.add(step_dict.get('name'))

            Step.validate(step_dict)

        # Check reachability
        reachable_steps_set = set()
        for init_step in init_steps:
            try:
                reachable_steps_set.update(Stage._dfs_reachable(set(), set(), steps_graph, init_step))
            except exceptions.StageCycleDetected:
                raise exceptions.StageValidationError("Cycle detected in Stage", stage_name=stage_dict.get('name'))
        if all_steps_set != reachable_steps_set:
            raise exceptions.StageValidationError(
                f'There is a problem with steps. Check that all steps are reachable, and that only existing steps are '
                f'set as successors. All steps: {all_steps_set}, reachable steps:{reachable_steps_set}', )

        # Check that init steps are not set as successors
        if not init_steps.isdisjoint(all_successors_set):
            invalid_steps = init_steps.intersection(all_successors_set)
            raise exceptions.StageValidationError(
                f"One or more successors are set as init steps. Invalid steps are {invalid_steps}.")

        return True

    def add_dependency(self, dependency_id: int) -> int:
        """
        Create dependency object
        :param dependency_id: Stage ID
        :return: ID of the dependency object
        """
        dependency_obj = DependencyModel(stage_model_id=self.model.id, dependency_id=dependency_id)
        dependency_obj.save()

        return dependency_obj.id


class StageExecution:
    def __init__(self, **kwargs):
        """
        :param kwargs:
        (optional) stage_execution_id: int - for retrieving existing execution
        stage_model_id: int - for creating new execution
        """
        stage_execution_id = kwargs.get('stage_execution_id')
        if stage_execution_id:
            try:
                self.model = StageExecutionModel.objects.get(id=stage_execution_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.StageExecutionObjectDoesNotExist(
                    "StageExecutionModel with id {} does not exist.".format(stage_execution_id), stage_execution_id
                )

        else:
            self.model = StageExecutionModel.objects.create(**kwargs)

    def delete(self):
        self.model.delete()

    @property
    def model(self) -> Union[Type[StageExecutionModel], StageExecutionModel]:
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value: StageExecutionModel):
        self.__model = value

    @property
    def state(self) -> str:
        return self.model.state

    @state.setter
    def state(self, value: str):
        with transaction.atomic():
            StageExecutionModel.objects.select_for_update().get(id=self.model.id)
            if st.StageStateMachine(self.model.id).validate_transition(self.state, value):
                logger.logger.debug("stagexecution changed state", state_from=self.state, state_to=value)
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
    def start_time(self) -> Optional[datetime]:
        return self.model.start_time

    @start_time.setter
    def start_time(self, value: Optional[datetime]):
        model = self.model
        model.start_time = value
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
    def all_steps_finished(self) -> bool:
        # Check if any steps are unfinished
        cond = StepExecutionModel.objects.filter(stage_execution_id=self.model.id) \
            .exclude(state__in=st.STEP_FINAL_STATES).exists()

        return not cond

    @property
    def all_dependencies_finished(self) -> bool:
        dependency_ids = self.model.stage_model.dependencies.all().values_list('dependency_id', flat=True)
        cond = self.filter(stage_model_id__in=dependency_ids, plan_execution_id=self.model.plan_execution_id)\
            .exclude(state=st.FINISHED).exists()

        return not cond

    @staticmethod
    def filter(**kwargs) -> QuerySet:
        """
        Get list of StageExecutionModel according to no or specified conditions
        :param kwargs: dict of parameters to filter by
        :return: Desired QuerySet
        """
        if kwargs:
            try:
                return StageExecutionModel.objects.filter(**kwargs)
            except django_exc.FieldError as ex:
                raise exceptions.WrongParameterError(message=ex)
        else:
            return StageExecutionModel.objects.all()

    def execute(self) -> None:
        """
        Create engine, nest it with Steps and execute it. If you want to replay Stage, create new StageExecution
        :return: None
        """
        st.StageStateMachine(self.model.id).validate_state(self.state, st.STAGE_EXECUTE_STATES)

        # Stop the execution if dependencies aren't finished
        if not self.all_dependencies_finished:
            if self.state != st.WAITING:
                self.state = st.WAITING
            return None

        # Get initial Steps in Stage
        init_steps = self.model.stage_model.steps.filter(is_init=True)
        step_exec_list = list()
        for step_model in init_steps:
            # TODO make sure there is only one - this should not happen
            try:
                step_exec_model = StepExecutionModel.objects.get(step_model=step_model,
                                                                 stage_execution_id=self.model.id,
                                                                 state=st.PENDING)
            except django_exc.MultipleObjectsReturned as ex:
                logger.logger.warn(str(ex))
                raise RuntimeError(ex)
            step_exec_list.append(StepExecution(step_execution_id=step_exec_model.id))

        # Prepare processes and evenly distribute executions into processes
        step_exec_lists = list(util.split_into_lists(step_exec_list, config.CRYTON_CPU_CORES))
        processes = []
        for step_exec_list in step_exec_lists:
            if step_exec_list:
                processes.append(Process(target=util.run_executions_in_threads, args=(step_exec_list,)))

        # Close django db connections and run processes
        connections.close_all()
        for process in processes:
            process.start()

        # Update state and time
        self.state = st.RUNNING
        if self.start_time is None:
            self.start_time = datetime.utcnow()

        logger.logger.info("stagexecution executed", stage_execution_id=self.model.id,
                           stage_name=self.model.stage_model.name, status='success')

        return None

    def validate_modules(self) -> None:
        """
        Check if module is present and module args are correct for each Step
        """

        for step_ex_id in self.model.step_executions.values_list('id', flat=True):
            StepExecution(step_execution_id=step_ex_id).validate_module()

        return None

    def report(self) -> dict:
        report_dict = dict()
        report_dict.update({'id': self.model.id, 'stage_name': self.model.stage_model.name, 'state': self.state,
                            'schedule_time': self.schedule_time, 'start_time': self.start_time,
                            'finish_time': self.finish_time, 'pause_time': self.pause_time})
        report_dict.update({'step_executions': []})
        for step_execution_obj in StepExecutionModel.objects.filter(stage_execution_id=self.model.id).order_by('id'):
            step_ex_report = StepExecution(step_execution_id=step_execution_obj.id).report()
            report_dict['step_executions'].append(step_ex_report)

        return report_dict

    def kill(self) -> None:
        """
        Kill current StageExecution and its StepExecutions
        :return: None
        """
        st.StageStateMachine(self.model.id).validate_state(self.state, st.STAGE_KILL_STATES)

        if self.state == st.WAITING:
            pass

        elif self.schedule_time is not None and self.state == st.PENDING and \
                self.model.stage_model.trigger_type == co.DELTA:
            triggers.TriggerType[co.DELTA].value(stage_execution_id=self.model.id).unschedule()

        else:
            threads = list()
            for step_ex_obj in self.model.step_executions.filter(state__in=st.STEP_KILL_STATES):
                step_ex = StepExecution(step_execution_id=step_ex_obj.id)
                thread = Thread(target=step_ex.kill)
                threads.append(thread)

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join()

        self.state = st.TERMINATED
        logger.logger.info("stagexecution killed", stage_execution_id=self.model.id,
                           stage_name=self.model.stage_model.name, status='success')

        return None


def execution(execution_id: int) -> None:
    """
    Create StageExecution object and call its execute method
    :param execution_id: desired StageExecution's ID
    :return: None
    """
    StageExecution(stage_execution_id=execution_id).execute()
    return None
