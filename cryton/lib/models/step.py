import json
from datetime import datetime
from typing import Union, Type, Optional
import re
import copy

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models.query import QuerySet
from django.core import exceptions as django_exc
from django.db.models import Q
from django.utils import timezone
import amqpstorm
from schema import Schema, Optional as SchemaOptional, SchemaError

from cryton.cryton_rest_api.models import StepModel, StepExecutionModel, SuccessorModel, ExecutionVariableModel, \
    OutputMapping, CorrelationEvent, WorkerModel

from cryton.etc import config
from cryton.lib.util import constants, exceptions, logger, states, util
from cryton.lib.models import worker, session

from dataclasses import dataclass, asdict


@dataclass
class StepReport:
    id: int
    step_name: str
    state: str
    start_time: datetime
    finish_time: datetime
    std_err: str
    std_out: str
    mod_err: str
    mod_out: str
    evidence_file: str
    result: str
    valid: bool


class Step:

    def __init__(self, **kwargs):
        """

        :param kwargs:
                 step_model_id: int = None,
                 stage_model_id: int = None,
                 attack_module: str = None,
                 is_init: bool = None,
                 name: str = None
                 executor: str = None,
                 attack_module_args: dict = None
        """
        step_model_id = kwargs.get('step_model_id')
        if step_model_id:
            try:
                self.model = StepModel.objects.get(id=step_model_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.StepObjectDoesNotExist("PlanModel with id {} does not exist."
                                                        .format(step_model_id))

        else:
            step_obj_arguments = copy.deepcopy(kwargs)
            step_obj_arguments.pop('next', None)
            step_obj_arguments.pop('output_mapping', None)
            # Set default prefix as step name
            if step_obj_arguments.get('output_prefix') is None:
                step_obj_arguments.update({'output_prefix': step_obj_arguments.get('name')})
            self.model = StepModel.objects.create(**step_obj_arguments)

    def delete(self):
        self.model.delete()

    @property
    def model(self) -> Union[Type[StepModel], StepModel]:
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value: StepModel):
        self.__model = value

    @property
    def stage_model_id(self) -> Union[Type[int], int]:
        return self.model.stage_model_id

    @stage_model_id.setter
    def stage_model_id(self, value: int):
        model = self.model
        model.stage_model_id = value
        model.save()

    @property
    def name(self) -> str:
        return self.model.name

    @name.setter
    def name(self, value: str):
        model = self.model
        model.name = value
        model.save()

    @property
    def attack_module(self) -> str:
        return self.model.attack_module

    @attack_module.setter
    def attack_module(self, value: str):
        model = self.model
        model.attack_module = value
        model.save()

    @property
    def is_init(self) -> bool:
        return self.model.is_init

    @is_init.setter
    def is_init(self, value: bool):
        model = self.model
        model.is_init = value
        model.save()

    @property
    def is_final(self) -> bool:
        return self.model.is_final

    @is_final.setter
    def is_final(self, value: bool):
        model = self.model
        model.is_final = value
        model.save()

    @property
    def executor(self) -> str:
        if self.model.executor is not None:
            return self.model.executor
        return self.model.stage_model.executor

    @executor.setter
    def executor(self, value: str):
        model = self.model
        model.executor = value
        model.save()

    @property
    def attack_module_args(self) -> dict:
        return self.model.attack_module_args

    @attack_module_args.setter
    def attack_module_args(self, value: dict):
        model = self.model
        model.attack_module_args = value
        model.save()

    @property
    def output_prefix(self) -> str:
        return self.model.output_prefix

    @output_prefix.setter
    def output_prefix(self, value: bool):
        model = self.model
        model.output_prefix = value
        model.save()

    @property
    def execution_stats_list(self) -> QuerySet:
        """
        Returns StepExecutionStatsModel QuerySet. If the latest is needed, use '.latest()' on result.
        :return: QuerySet of StepExecutionStatsModel
        """
        return StepExecutionModel.objects.filter(step_model_id=self.model.id)

    @property
    def parents(self) -> QuerySet:
        return StepModel.objects.filter(id__in=SuccessorModel.objects.filter(
            successor_step_id=self.model.id).values_list('parent_step_id'))

    @property
    def successors(self) -> QuerySet:
        return StepModel.objects.filter(id__in=SuccessorModel.objects.filter(
            parent_step_id=self.model.id).values_list('successor_step_id'))

    @staticmethod
    def filter(**kwargs) -> QuerySet:
        """
        Get list of StepInstances according to no or specified conditions
        :param kwargs: dict of parameters to filter by
        :return:
        """
        if kwargs:
            try:
                return StepModel.objects.filter(**kwargs)
            except django_exc.FieldError as ex:
                raise exceptions.WrongParameterError(message=ex)
        else:
            return StepModel.objects.all()

    @staticmethod
    def validate(step_dict) -> bool:
        """
        Validate a step dictionary

        :raises:
            exceptions.StepValidationError
        :return: True
        """
        conf_schema = Schema({
            'name': str,
            SchemaOptional('is_init'): bool,
            'attack_module': str,
            'attack_module_args': dict,
            SchemaOptional('next'): list,
            SchemaOptional('executor'): str,
            SchemaOptional('output_mapping'): list,
            SchemaOptional('output_prefix'): str
        })

        try:
            conf_schema.validate(step_dict)
        except SchemaError as ex:
            raise exceptions.StepValidationError(ex, step_name=step_dict.get('name'))

        return True

    def add_successor(self, successor_id, successor_type, successor_value) -> int:
        """

        :param successor_id:
        :param successor_type: One of valid types
        :param successor_value: One of valid values for specified type
        :raises:
            InvalidSuccessorType
            InvalidSuccessorValue
        :return: SuccessorModel id
        """
        if successor_type not in constants.VALID_SUCCESSOR_TYPES:
            raise exceptions.InvalidSuccessorType(
                "Unknown successor type. Choose one of valid types: {}".format(constants.VALID_SUCCESSOR_TYPES),
                successor_type
            )
        if (successor_type == constants.RESULT and successor_value not in constants.VALID_SUCCESSOR_RESULTS) or \
                (successor_type == constants.STATE and successor_value not in states.VALID_SUCCESSOR_STATES):
            raise exceptions.InvalidSuccessorValue(
                "Unknown successor value. Choose one of valid types: {}".format(constants.VALID_SUCCESSOR_RESULTS),
                successor_value
            )

        stepsucc_obj = SuccessorModel(parent_step_id=self.model.id, successor_step_id=successor_id,
                                      succ_type=successor_type, succ_value=successor_value)
        stepsucc_obj.save()

        return stepsucc_obj.id


class StepExecution:

    def __init__(self, **kwargs):
        """

        :param kwargs:
        (optional) step_execution_id: int - for retrieving existing execution
        step_model_id: int - for creating new execution
        """
        step_execution_id = kwargs.get('step_execution_id')
        if step_execution_id is not None:
            try:
                self.model = StepExecutionModel.objects.get(id=step_execution_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.StepExecutionDoesNotExist("StepExecutionStatsModel with id {} does not exist."
                                                           .format(step_execution_id))

        else:
            self.model = StepExecutionModel.objects.create(**kwargs)

    def delete(self):
        self.model.delete()

    @property
    def model(self) -> Union[Type[StepExecutionModel], StepExecutionModel]:
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value: StepExecutionModel):
        self.__model = value

    @property
    def state(self) -> str:
        return self.model.state

    @state.setter
    def state(self, value: str):
        with transaction.atomic():
            StepExecutionModel.objects.select_for_update().get(id=self.model.id)
            if states.StepStateMachine(self.model.id).validate_transition(self.state, value):
                logger.logger.debug("stepexecution changed state", state_from=self.state, state_to=value)
                model = self.model
                model.state = value
                model.save()

    @property
    def result(self) -> str:
        return self.model.result

    @result.setter
    def result(self, value: str):
        model = self.model
        model.result = value
        model.save()

    @property
    def std_out(self) -> str:
        return self.model.std_out

    @std_out.setter
    def std_out(self, value: str):
        model = self.model
        model.std_out = value
        model.save()

    @property
    def std_err(self) -> str:
        return self.model.std_err

    @std_err.setter
    def std_err(self, value: str):
        model = self.model
        model.std_err = value
        model.save()

    @property
    def mod_out(self) -> dict:
        return self.model.mod_out

    @mod_out.setter
    def mod_out(self, value: dict):
        model = self.model
        model.mod_out = value
        model.save()

    @property
    def mod_err(self) -> str:
        return self.model.mod_err

    @mod_err.setter
    def mod_err(self, value: str):
        model = self.model
        model.mod_err = value
        model.save()

    @property
    def evidence_file(self) -> str:
        return self.model.evidence_file

    @evidence_file.setter
    def evidence_file(self, value: str):
        model = self.model
        model.evidence_file = value
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
    def finish_time(self) -> Optional[datetime]:
        return self.model.finish_time

    @finish_time.setter
    def finish_time(self, value: Optional[datetime]):
        model = self.model
        model.finish_time = value
        model.save()

    @property
    def valid(self) -> bool:
        return self.model.valid

    @valid.setter
    def valid(self, value: bool):
        model = self.model
        model.valid = value
        model.save()

    @property
    def parent_id(self) -> int:
        return self.model.parent_id

    @parent_id.setter
    def parent_id(self, value: int):
        model = self.model
        model.parent_id = value
        model.save()

    @staticmethod
    def filter(**kwargs) -> QuerySet:
        """
        Get list of StepExecutionStatsModel according to no or specified conditions
        :param kwargs: dict of parameters to filter by
        :return: Desired QuerySet
        """
        if kwargs:
            try:
                return StepExecutionModel.objects.filter(**kwargs)
            except django_exc.FieldError as ex:
                raise exceptions.WrongParameterError(message=ex)
        else:
            return StepExecutionModel.objects.all()

    def validate_module(self) -> bool:
        """

        Validate attack module arguments

        :return:
        """
        logger.logger.debug("Validating Step module", step_id=self.model.step_model_id)
        worker_obj = self.model.stage_execution.plan_execution.worker
        module_name = self.model.step_model.attack_module.replace('/', '.')
        resp = util.validate_attack_module_args(module_name,
                                                self.model.step_model.attack_module_args,
                                                worker_obj,
                                                )
        if resp:
            self.valid = True

        return resp

    def save_output(self, step_output) -> None:
        """

        :param step_output: dictionary with keys: std_err, std_out
        :return: None
        """
        mod_out = step_output.get(constants.MOD_OUT)
        if mod_out is not None:
            output_mappings = OutputMapping.objects.filter(step_model=self.model.step_model)
            for output_mapping in output_mappings:
                util.rename_key(mod_out, output_mapping.name_from, output_mapping.name_to)
        model = self.model
        model.std_out = step_output.get(constants.STD_OUT, 'No output')
        model.std_err = step_output.get(constants.STD_ERR, 'No error')
        model.mod_out = mod_out
        model.mod_err = step_output.get(constants.MOD_ERR, 'No error')
        model.evidence_file = step_output.get(constants.EVIDENCE_FILE, 'No evidence')
        model.save()

        return None

    def _update_dynamic_variables(self, mod_args, parent_step_ex_id):
        """
        Update dynamic variables in mod_args (even with special $parent prefix)
        :param mod_args:
        :param parent_step_ex_id:
        :return:
        """

        # Get list of dynamic variables
        vars_list = util.get_dynamic_variables(mod_args)

        # Get their prefixes
        prefixes = util.get_prefixes(vars_list)
        vars_dict = dict()
        is_parent = False

        for prefix in prefixes:
            # If prefix is parent, get parents prefix
            if prefix == 'parent':
                if parent_step_ex_id is None:
                    raise RuntimeError("Parent must be specified for $parent prefix.")
                is_parent = True
                prefix = StepExecutionModel.objects.get(id=parent_step_ex_id).step_model.output_prefix

            tmp_dict = dict()

            for step_ex in StepExecutionModel.objects.filter(step_model__output_prefix=prefix,
                                                             stage_execution__plan_execution=self.model.stage_execution.plan_execution):
                if step_ex.mod_out is not None:
                    tmp_dict.update(step_ex.mod_out)

            # Change parents prefix back to 'parent' for updating dictionary to susbtitute
            if is_parent:
                prefix = 'parent'
                is_parent = False
            vars_dict.update({prefix: tmp_dict})

        mod_args = util.fill_dynamic_variables(mod_args, vars_dict)
        return mod_args

    def execute(self, rabbit_channel: amqpstorm.Channel = None) -> str:
        """
        Execute Step on single worker specified in execution stats

        :param rabbit_channel: Rabbit channel
        :return: Return Correlation ID
        """
        logger.logger.debug("Executing Step", step_id=self.model.step_model_id)
        if rabbit_channel is None:
            rabbit_connection = util.rabbit_connection()
            rabbit_channel = rabbit_connection.channel()
        states.StepStateMachine(self.model.id).validate_state(self.state, states.STEP_EXECUTE_STATES)
        step_obj = Step(step_model_id=self.model.step_model_id)
        plan_execution_id = self.model.stage_execution.plan_execution_id
        step_worker_obj = self.model.stage_execution.plan_execution.worker

        # Set RUNNING state
        self.start_time = timezone.now()
        self.state = states.RUNNING

        # Check if any session should be used
        use_named_session = step_obj.attack_module_args.get(constants.USE_NAMED_SESSION)
        use_any_session_to_target = step_obj.attack_module_args.get(constants.USE_ANY_SESSION_TO_TARGET)
        if use_named_session is not None:
            # Throws SessionObjectDoesNotExist
            session_msf_id = session.get_msf_session_id(use_named_session, plan_execution_id)
            if session_msf_id is None:
                err_msg = {'message': "No session with specified name open",
                           'session_name': use_named_session,
                           'plan_execution_id': plan_execution_id, 'step_id': step_obj.model.id}
                logger.logger.error(**err_msg)
                self.state = states.ERROR
                raise exceptions.SessionIsNotOpen(**err_msg)

        elif use_any_session_to_target is not None:
            # Get last session
            try:
                session_msf_id_lst = session.get_session_ids(use_any_session_to_target, plan_execution_id)
            except Exception as ex:
                raise exceptions.RabbitConnectionError(str(ex))

            if len(session_msf_id_lst) == 0 or session_msf_id_lst[-1] is None:
                err_msg = {'message': "No session to desired target open",
                           'plan_execution_id': plan_execution_id, 'step_id': step_obj.model.id}
                logger.logger.error(**err_msg)
                self.state = states.ERROR
                raise exceptions.SessionObjectDoesNotExist(**err_msg)
            session_msf_id = session_msf_id_lst[-1]

        else:
            session_msf_id = None

        mod_args = step_obj.attack_module_args

        # Update module arguments with execution variables
        execution_vars = list(ExecutionVariableModel.objects.filter(plan_execution_id=plan_execution_id).values())
        if execution_vars:
            execution_vars_dict = dict()
            for execution_var in execution_vars:
                execution_vars_dict.update({execution_var.get('name'): execution_var.get('value')})

            mod_args = json.dumps(mod_args)
            mod_args = util.fill_template(mod_args, execution_vars_dict)
            mod_args = json.loads(mod_args)

        # Update dynamic variables
        mod_args = self._update_dynamic_variables(mod_args, self.parent_id)

        if session_msf_id is not None:
            mod_args.update({constants.SESSION_ID: session_msf_id})

        # Execute Attack module
        try:
            correlation_id = self._execute_attack_module(rabbit_channel, step_obj.attack_module, mod_args,
                                                         step_worker_obj, step_obj.model.executor)
        except exceptions.RabbitConnectionError as ex:
            logger.logger.error("Step could not be executed due to connection error: {}".format(ex))
            self.state = states.ERROR
            raise

        # Log
        logger.logger.info("stepexecution executed", step_execution_id=self.model.id,
                           step_name=self.model.step_model.name, status='success')

        return correlation_id

    def report(self) -> dict:
        report_obj = StepReport(id=self.model.id, step_name=self.model.step_model.name, state=self.state,
                                start_time=self.start_time, finish_time=self.finish_time, result=self.result,
                                mod_out=self.mod_out, mod_err=self.mod_err, std_out=self.std_out,
                                std_err=self.std_err, evidence_file=self.evidence_file, valid=self.valid)

        return asdict(report_obj)

    def _execute_attack_module(self, rabbit_channel: amqpstorm.Channel, attack_module: str,
                               attack_module_arguments: dict, worker_model: WorkerModel, executor: str = None) -> str:
        """
        Sends RPC request to execute attack module using RabbitMQ.

        :param rabbit_channel: Rabbit channel
        :param attack_module: Attack module string (dot notation, eg: modules.infrastructure.mod_nmap
        :param attack_module_arguments: Arguments in form o dictionary
        :param worker_model: WorkerModel object
        :param executor: Executor address (address:port or address), if desired.
        :return: correlation_id of the sent message
        """
        message_body = {
            "attack_module": attack_module,
            "attack_module_arguments": attack_module_arguments,
            # "executor": executor
        }
        target_queue = worker.Worker(worker_model_id=worker_model.id).attack_q_name

        with util.Rpc(rabbit_channel) as rpc:
            correlation_id = rpc.prepare_message(message_body, config.Q_ATTACK_RESPONSE_NAME)
            CorrelationEvent.objects.create(correlation_id=correlation_id, step_execution_id=self.model.id,
                                            worker_q_name=target_queue)

            response = rpc.call(target_queue, time_limit=10)
            if response is None:
                raise exceptions.RabbitConnectionError("No response from Worker.")
            correlation_id = rpc.correlation_id

        return correlation_id

    def get_regex_sucessors(self) -> QuerySet:
        """
        Get successors according to provided regex

        :return: QuerySet of StepModel objects
        """
        succs_ids_set = set()
        # Get all successormodels that have regex specified in succ_value (starting with r' or r")
        succ_list = SuccessorModel.objects.filter(parent_step_id=self.model.step_model.id). \
            filter(Q(succ_value__startswith='r"', succ_value__endswith='"')
                   | Q(succ_value__startswith="r'", succ_value__endswith="'"))

        # Match all regex successors against actual value
        for succ_obj in succ_list:
            desired_succ_value = succ_obj.succ_value
            regex = re.match(r"r[\"|\'](.*?)[\"|\']", desired_succ_value)
            # Gets succ_value from succ_type eg. self.mod_out for succ_type == 'mod_out'
            succ_value = getattr(self, succ_obj.succ_type)
            # If regex matches -> add successor step_id to set
            if re.search(r"{}".format(regex.group(0)[2:-1]), succ_value):
                matched_succ = succ_obj.successor_step.id
                succs_ids_set.add(matched_succ)

        # Convert set of IDs into actual StepModels
        succs_queryset = StepModel.objects.filter(id__in=succs_ids_set)
        return succs_queryset

    def get_successors(self) -> QuerySet:
        """
        Get Successors based on evaluated dependency

        :return: QuerySet of StepModel objects
        """
        # Get step successor from DB
        succs_ids_set = set()
        for succ_type in SuccessorModel.objects.filter(parent_step_id=self.model.step_model.id).values(
                'succ_type').distinct():
            succ_type = succ_type.get('succ_type')
            # Add ANY successors and continue
            if succ_type == constants.ANY:
                matched_succ = SuccessorModel.objects.get(parent_step_id=self.model.step_model.id,
                                                          succ_type=succ_type).successor_step.id
                succs_ids_set.add(matched_succ)
                continue
            # Get the actual value of succ_type
            try:
                succ_value = getattr(self, succ_type)
            except AttributeError:
                # This should be taken care of during Plan validation, but in any case:
                logger.logger.error("Wrong successor type.", succ_type=succ_type)
                continue
            try:
                matched_succ = SuccessorModel.objects.get(parent_step_id=self.model.step_model.id,
                                                          succ_type=succ_type,
                                                          succ_value=succ_value).successor_step.id
            except ObjectDoesNotExist:
                pass
            else:
                succs_ids_set.add(matched_succ)

        succs_queryset = StepModel.objects.filter(id__in=succs_ids_set)

        regex_succs_queryset = self.get_regex_sucessors()
        result_queryset = succs_queryset | regex_succs_queryset

        return result_queryset

    def ignore(self) -> None:
        """
        Sets statse.IGNORE state to step execution and to all executions of it's successors
        :return:
        """
        logger.logger.debug("Ignoring Step", step_id=self.model.step_model_id)
        # Stop recursion
        if self.state == states.IGNORED:
            return None
        # If any non SKIPPED parent exists (ignoring the one that called ignore())
        for par_step in Step(step_model_id=self.model.step_model.id).parents:
            step_exec_obj = StepExecutionModel.objects.get(step_model=par_step,
                                                           stage_execution=self.model.stage_execution)
            if step_exec_obj.state not in states.STEP_FINAL_STATES:
                return None
        # Set ignore state
        self.state = states.IGNORED
        # Execute for all successors
        for succ_step in Step(step_model_id=self.model.step_model.id).successors:
            step_ex_id = StepExecutionModel.objects.get(step_model=succ_step,
                                                        stage_execution=self.model.stage_execution).id
            step_ex_obj = StepExecution(step_execution_id=step_ex_id)
            step_ex_obj.ignore()

        return None

    def postprocess(self, ret_vals: dict) -> None:
        logger.logger.debug("Postprocessing Step", step_id=self.model.step_model_id)
        step_obj = Step(step_model_id=self.model.step_model.id)

        # Check if any named session should be created:
        create_named_session = step_obj.attack_module_args.get(constants.CREATE_NAMED_SESSION)
        if create_named_session is not None:
            msf_session_id = ret_vals.get(constants.RET_SESSION_ID)
            if msf_session_id is not None:
                session.create_session(self.model.stage_execution.plan_execution_id, msf_session_id,
                                       create_named_session)

        # Store job result
        step_result = constants.RET_CODE_ENUM.get(ret_vals.get(constants.RETURN_CODE))
        if step_result is None:
            step_result = constants.RESULT_UNKNOWN
        self.result = step_result

        # Set step FINISHED state
        self.finish_time = timezone.now()
        self.state = states.FINISHED

        # update Successors parents
        succ_list = self.get_successors()

        for succ_step in succ_list:
            succ_step_execution_model = StepExecutionModel.objects.get(
                step_model_id=succ_step.id, stage_execution_id=self.model.stage_execution_id, state=states.PENDING)
            StepExecution(step_execution_id=succ_step_execution_model.id).parent_id = self.model.id

        # Store file, if present in returned object
        ret_file = ret_vals.get(constants.RET_FILE)
        if ret_file is not None:
            file_name = ret_file.get(constants.RET_FILE_NAME)
            file_content = ret_file.get(constants.RET_FILE_CONTENT)
            evidence_dir = self.model.stage_execution.plan_execution.evidence_dir
            file_path = util.store_evidence_file(file_name, file_content, evidence_dir)
            ret_vals.update({constants.EVIDENCE_FILE: file_path})

        # Store job output and error message
        self.save_output(ret_vals)
        logger.logger.debug("Step postprocess finished", step_id=self.model.step_model_id)
        return None

    def ignore_successors(self) -> None:
        logger.logger.debug("Ignoring Step successors", step_id=self.model.step_model_id)
        step_obj = Step(step_model_id=self.model.step_model.id)
        # Get correct step successor from DB which are to be executed
        succ_list = self.get_successors()
        # Get all possible successors
        all_succ_list = StepModel.objects.filter(
            id__in=step_obj.model.successors.all().values_list('successor_step'))
        # Set IGNORE steps (all successors which wont be executed and don't have parents
        succ_to_be_skipped = all_succ_list.difference(succ_list)
        for succ_step in succ_to_be_skipped:
            try:
                succ_step_exec_id = StepExecutionModel.objects.get(step_model_id=succ_step.id,
                                                                   stage_execution=self.model.stage_execution_id,
                                                                   state=states.PENDING).id
            except ObjectDoesNotExist:
                # Does not exist or is not PENDING
                continue
            StepExecution(step_execution_id=succ_step_exec_id).ignore()
        return None

    def execute_successors(self) -> None:
        logger.logger.debug("Executing Step successors", step_id=self.model.step_model_id)

        # Get correct step successor from DB which are to be executed
        succ_list = self.get_successors()

        # Execute all successors
        for succ_step_model in succ_list:
            succ_step_id = succ_step_model.id
            succ_step_execution_model = StepExecutionModel.objects.get(step_model_id=succ_step_id,
                                                                       stage_execution_id=self.model.stage_execution_id,
                                                                       state=states.PENDING)
            succ_step_exec = StepExecution(step_execution_id=succ_step_execution_model.id)
            try:
                succ_step_exec.execute()
            except (exceptions.SessionIsNotOpen, exceptions.SessionObjectDoesNotExist) as ex:
                succ_step_exec.result = constants.RESULT_FAIL
                succ_step_exec.std_err = str(ex)
        return None

    def pause_successors(self) -> None:
        logger.logger.debug("Pausing Step successors", step_id=self.model.step_model_id)
        # Set all successors to PAUSED, so they can be recognized/executed when unpaused
        succ_list = self.get_successors()
        for step_obj in succ_list:
            succ_exec_id = StepExecutionModel.objects.get(stage_execution=self.model.stage_execution,
                                                          step_model_id=step_obj.id).id
            StepExecution(step_execution_id=succ_exec_id).state = states.PAUSED
            logger.logger.info('successors stepexecution paused', succ_exec_id=succ_exec_id)

        return None

    def kill(self) -> dict:
        """
        Kill current Step Execution on Worker
        :return: Dictionary containing return_code and std_err
        """
        logger.logger.debug("Killing Step", step_id=self.model.step_model_id)
        states.StepStateMachine(self.model.id).validate_state(self.state, states.STEP_KILL_STATES)
        worker_obj = worker.Worker(worker_model_id=self.model.stage_execution.plan_execution.worker.id)
        correlation_id = self.model.correlation_events.first().correlation_id
        event_info = {constants.EVENT_T: constants.EVENT_KILL_STEP_EXECUTION,
                      constants.EVENT_V: {"correlation_id": correlation_id}}

        with util.Rpc() as worker_rpc:
            resp = worker_rpc.call(worker_obj.control_q_name, event_info)

        resp_dict = resp.get('event_v')

        if resp_dict.get('return_code') == 0:
            logger.logger.info("stepexecution killed", step_execution_id=self.model.id,
                               stage_name=self.model.step_model.name, status='success')
        else:
            logger.logger.info("stepexecution not killed", step_execution_id=self.model.id,
                               stage_name=self.model.step_model.name, status='failure', error=resp_dict.get('std_err'))

        return resp_dict

    def re_execute(self) -> None:
        """
        Reset execution data and re-execute StepExecution.
        :return: None
        """
        states.StepStateMachine(self.model.id).validate_state(self.state, states.STEP_FINAL_STATES)
        self.reset_execution_data()
        self.execute()

    def reset_execution_data(self) -> None:
        """
        Reset changeable data to defaults.
        :return: None
        """
        states.StepStateMachine(self.model.id).validate_state(self.state, states.STEP_FINAL_STATES)

        with transaction.atomic():
            model = self.model
            StepExecutionModel.objects.select_for_update().get(id=model.id)

            model.state = model._meta.get_field('state').get_default()
            model.start_time = model._meta.get_field('start_time').get_default()
            model.pause_time = model._meta.get_field('pause_time').get_default()
            model.finish_time = model._meta.get_field('finish_time').get_default()
            model.result = model._meta.get_field('result').get_default()
            model.std_out = model._meta.get_field('std_out').get_default()
            model.std_err = model._meta.get_field('std_err').get_default()
            model.mod_out = model._meta.get_field('mod_out').get_default()
            model.mod_err = model._meta.get_field('mod_err').get_default()
            model.evidence_file = model._meta.get_field('evidence_file').get_default()
            model.valid = model._meta.get_field('valid').get_default()
            model.parent_id = model._meta.get_field('parent_id').get_default()
            model.save()
