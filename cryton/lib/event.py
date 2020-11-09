import datetime
from typing import Type, Union

from cryton.cryton_rest_api.models import (
    CorrelationEvent,
)
from cryton.lib import (
    plan,
    step,
    run,
    states,
    logger,
    worker,
    constants
)


def process_event(event_t: str, event_v: dict) -> None:
    if event_t in ['PAUSE']:
        process_pause(event_v)
    else:
        logger.logger.warn("Nonexistent event received.", event_t=event_t)
    return None


def process_control_event(control_event_t: str, control_event_v: dict, correlation_event_obj: CorrelationEvent) -> None:

    if control_event_t == 'VALIDATE_MODULE':
        process_validate_module(control_event_v, correlation_event_obj.event_identification_value)

    elif control_event_t == 'HEALTHCHECK':
        process_healthcheck(control_event_v, correlation_event_obj.event_identification_value)

    elif control_event_t == 'LIST_SESSIONS':
        process_list_sessions(control_event_v)

    elif control_event_t == 'LIST_MODULES':
        process_list_modules(control_event_v)

    elif control_event_t == 'KILL_EXECUTION':
        process_kill_execution(control_event_v, correlation_event_obj.event_identification_value)

    else:
        logger.logger.warn("Nonexistent control event received.", control_event_t=control_event_t)

    return None


def process_validate_module(event_v: dict, step_execution_id: Union[int, Type[int]]) -> None:
    step_execution = step.StepExecution(step_execution_id=step_execution_id)
    if event_v.get(constants.RETURN_CODE) == 0:
        step_execution.valid = True
    else:
        step_execution.std_err = event_v.get(constants.STD_ERR)
        step_execution.valid = False

    return None


def process_pause(event_v: dict) -> None:
    if event_v.get('result') == 'OK':
        plan_execution_id = event_v.get('plan_execution_id')
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan_execution_id)
        plan_ex_obj.state = states.PAUSED
        plan_ex_obj.pause_time = datetime.datetime.utcnow()
        if not plan.PlanExecutionModel.objects.filter(run_id=plan_ex_obj.model.run_id). \
                exclude(state__in=states.PLAN_FINAL_STATES + [states.PAUSED]).exists():
            run_obj = run.Run(run_model_id=plan_ex_obj.model.run_id)
            run_obj.state = states.PAUSED
            run_obj.pause_time = datetime.datetime.utcnow()

    return None


def process_healthcheck(event_v: dict, worker_model_id: Union[int, Type[int]]) -> None:
    worker_obj = worker.Worker(worker_model_id=worker_model_id)
    if event_v.get(constants.RETURN_CODE) == 0:
        worker_obj.state = states.UP
    else:
        worker_obj.state = states.DOWN

    return None


def process_list_sessions(event_v: dict) -> None:

    return None


def process_list_modules(event_v: dict) -> None:

    return None


def process_kill_execution(event_v: dict, step_execution_id: Union[int, Type[int]]) -> None:

    return None
