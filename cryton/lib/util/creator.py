from typing import List

from cryton.lib.util import exceptions, logger
from cryton.lib.models import stage, plan, step, worker, run
from cryton.cryton_rest_api.models import (
    WorkerModel,
    RunModel,
    OutputMapping
)


def validate_plan_dict(plan_file_dict: dict) -> None:
    """
    Validate plan dictionary

    :param dict plan_file_dict: plan in dictionary format as read from file
    :return: None
    :raises
        exceptions.ValidationError
    """
    plan_dict = plan_file_dict.get('plan')
    plan.Plan.validate(plan_dict=plan_dict)

    return None


def create_plan(plan_file_dict: dict) -> plan.Plan:
    """
    Save plan to database and check if its structure is correct

    :param dict plan_file_dict: plan in dictionary format as read from file ({"plan": ... })
    :return: saved Plan object
    :raises
        exceptions.ValidationError
        exceptions.PlanCreationFailedError
    """
    # First validate the dict
    validate_plan_dict(plan_file_dict)
    plan_dict = plan_file_dict.get('plan')
    stages_list = plan_dict.pop('stages', [])

    # Store Plan
    try:
        plan_obj = plan.Plan(**plan_dict)
    except TypeError as ex:
        raise exceptions.PlanCreationFailedError(message=ex, plan_name=plan_dict.get('name'))
    # Store Stages and Steps
    for stage_dict in stages_list:
        try:
            stage_obj = create_stage(stage_dict, plan_obj.model.id)
            stage_dict.update({'stage_model_id': stage_obj.model.id})
        except exceptions.CreationFailedError as ex:
            plan_obj.delete()
            raise exceptions.PlanCreationFailedError(message=ex, plan_name=plan_dict.get('name'))

    for stage_dict in stages_list:
        stage_id = stage_dict.get('stage_model_id')
        stage_dependencies = stage_dict.get('depends_on', [])
        stage_obj = stage.Stage(stage_model_id=stage_id)

        # set dependencies
        for stage_dependency_name in stage_dependencies:
            try:
                stage_dependency_id = stage.StageModel.objects.get(name=stage_dependency_name,
                                                                   plan_model_id=plan_obj.model.id).id
            except stage.StageModel.DoesNotExist as ex:
                plan_obj.delete()
                raise exceptions.DependencyDoesNotExist(message=ex, stage_name=stage_dependency_name)

            stage_obj.add_dependency(stage_dependency_id)

    logger.logger.info("plan created", plan_name=plan_obj.name,
                       plan_id=plan_obj.model.id, status='success')

    return plan_obj


def create_stage(stage_dict: dict, plan_model_id: int) -> stage.Stage:
    """
    Save stage to database

    :param stage_dict: Stage dictionary
    :param plan_model_id:
    :return: saved Stage object
    :raises
        exceptions.StageCreationFailedError
        exceptions.StepCreationFailedError
    """
    try:
        plan.PlanModel.objects.get(id=plan_model_id)
        assert type(stage_dict) is dict
    except plan.PlanModel.DoesNotExist:
        raise exceptions.StageCreationFailedError(message="Plan with id {} does not exist.".format(plan_model_id))
    except AssertionError:
        raise exceptions.StageCreationFailedError(message="stage_dict should be dict() type.")

    stage_dict_cp = stage_dict.copy()
    stage_dict_cp.update({'plan_model_id': plan_model_id})
    steps_list = stage_dict_cp.pop('steps')
    try:
        stage_obj = stage.Stage(**stage_dict_cp)
    except TypeError as ex:
        raise exceptions.StageCreationFailedError(message=ex, stage_name=stage_dict_cp.get('name'))
    for step_dict in steps_list:
        step_obj = create_step(step_dict, stage_obj.model.id)
        step_dict.update({'step_model_id': step_obj.model.id})

    for step_dict in steps_list:
        step_id = step_dict.get('step_model_id')
        step_successor_list = step_dict.get('next', [])
        step_obj = step.Step(step_model_id=step_id)

        # set successors
        for step_successor in step_successor_list:
            succ_list, succ_type, succ_value = (step_successor.get(key) for key in ['step', 'type', 'value'])
            if not isinstance(succ_list, list):
                succ_list = [succ_list]
            for succ in succ_list:
                try:
                    step_succ_id = step.StepModel.objects.get(name=succ,
                                                              stage_model_id=stage_obj.model.id).id
                except step.StepModel.DoesNotExist as ex:
                    raise exceptions.StageCreationFailedError(message=ex, stage_name=stage_dict_cp.get('name'))
                try:
                    if type(succ_value) == list:
                        for succ_value_unit in succ_value:
                            step_obj.add_successor(step_succ_id, succ_type, succ_value_unit)
                    else:
                        step_obj.add_successor(step_succ_id, succ_type, succ_value)
                except exceptions.InvalidSuccessorType as ex:
                    raise exceptions.StageCreationFailedError(message=ex, stage_name=stage_dict_cp.get('name'))

    logger.logger.info("stage created", stage_name=stage_obj.name,
                       stage_id=stage_obj.model.id, status='success')

    return stage_obj


def create_step(step_dict: dict, stage_model_id: int) -> step.Step:
    """
    Save step to database

    :param step_dict: Step dictionary
    :param stage_model_id:
    :return: save Step object
    :raises
        exceptions.StepCreationFailedError
    """
    # Set 'is_final' flag
    step_successor_list = step_dict.get('next', [])
    if len(step_successor_list) == 0:
        step_dict.update({'is_final': True})
    step_dict.update({'stage_model_id': stage_model_id})
    try:
        step_obj = step.Step(**step_dict)
    except TypeError as ex:
        raise exceptions.StepCreationFailedError(message=ex, step_name=step_dict.get('name'))

    # Create OutputMappings
    output_mappings = step_dict.get('output_mapping', [])
    for output_mapping in output_mappings:
        name_from = output_mapping.get('name_from')
        name_to = output_mapping.get('name_to')
        OutputMapping.objects.create(step_model=step_obj.model, name_from=name_from, name_to=name_to)

    logger.logger.info("step created", step_name=step_obj.name,
                       step_id=step_obj.model.id, status='success')
    return step_obj


def create_run(plan_model_id: int, workers_list: List[WorkerModel]) -> run.Run:
    """
    Creat Run
    :param plan_model_id: PlanModel ID
    :param workers_list: List of WorkerModel
    :return: Created Run object
    """
    try:
        run_obj = run.Run(plan_model_id=plan_model_id, workers_list=workers_list)
    except (ValueError, exceptions.ParameterMissingError) as ex:
        raise exceptions.RunCreationFailedError(ex)
    return run_obj


def create_plan_execution(plan_model_id: int, worker_id: int, run_id: int) -> plan.PlanExecution:
    if not plan.PlanModel.objects.filter(id=plan_model_id).exists():
        raise exceptions.PlanExecutionCreationFailedError(param_name='plan_model_id', param_type='int')

    if not WorkerModel.objects.filter(id=worker_id).exists():
        raise exceptions.PlanExecutionCreationFailedError(param_name='worker_id', param_type='int')

    if not RunModel.objects.filter(id=run_id).exists():
        raise exceptions.PlanExecutionCreationFailedError(param_name='run_id', param_type='int')

    plan_execution_obj = plan.PlanExecution(plan_model_id=plan_model_id, worker_id=worker_id, run_id=run_id)

    return plan_execution_obj


def create_worker(name: str, address: str, q_prefix: str = None, state: str = 'DOWN') -> worker.Worker:

    if name is None or len(name) == 0:
        raise exceptions.WrongParameterError(message="Parameter cannot be empty", param_name='name')
    if address is None or len(address) == 0:
        raise exceptions.WrongParameterError(message="Parameter cannot be empty", param_name='address')

    if q_prefix is None or len(q_prefix) == 0:
        q_prefix = '{}_{}'.format(name, address)
    worker_obj = worker.Worker(name=name, address=address, q_prefix=q_prefix, state=state)
    return worker_obj
