import collections
import dataclasses
from typing import Type, Union

from cryton.cryton_rest_api.models import (
    CorrelationEvent, SessionModel,
)
from cryton.lib.util import constants, logger, states
from cryton.lib.models import plan, step, worker, run, stage, session
from cryton.lib.services import scheduler

import amqpstorm
import json

from django.utils import timezone


@dataclasses.dataclass
class Event:
    event_t: str
    event_v: dict = dataclasses.field(default_factory=dict)


def process_event(event_obj: Event) -> None:
    """
    Proces received event

    :param event_obj: Event object
    :return:
    """
    logger.logger.debug("Received event", event_v=event_obj.event_v)

    if event_obj.event_t == constants.PAUSE:
        process_pause(event_obj)

    elif event_obj.event_t == constants.EVENT_TRIGGER_STAGE:
        process_trigger(event_obj)

    else:
        logger.logger.warn("Nonexistent event received.", event_v=event_obj.event_v)
    return None


def process_control_event(control_event_t: str,
                          control_event_v: dict,
                          correlation_event_obj: CorrelationEvent,
                          reply_to: str or None = None) -> dict or None:
    """
    Proces received control event
    :param control_event_t: one of allowed control event types
    :param control_event_v: arguments for specified control event
    :param correlation_event_obj: correlation object
    :param reply_to: name of queue for sending reply to
    :return: result of event execution
    """

    ret_val = None
    # No Control event implemented, all moved to Rpc calls

    return ret_val


def process_validate_module(event_obj: Event, step_execution_id: Union[int, Type[int]]) -> bool:
    """
    Process validate_cryton_module
    :param event_obj: Event object
    :param step_execution_id: Step execution ID
    :return: True or False, depending on validity of module
    """
    logger.logger.debug("Processing module validation", event_v=event_obj.event_v)
    step_execution = step.StepExecution(step_execution_id=step_execution_id)
    if event_obj.event_v.get(constants.RETURN_CODE) == 0:
        step_execution.valid = True
        return True
    else:
        step_execution.std_err = event_obj.event_v.get(constants.STD_ERR)
        step_execution.valid = False
        return False


def process_pause(event_obj: Event) -> int:
    """
    Process pause event
    :param event_obj: Event object
    :return: 0 in success
    """
    logger.logger.debug("Processing pause", event_v=event_obj.event_v)
    if event_obj.event_v.get(constants.RESULT) == constants.RESULT_OK:
        plan_execution_id = event_obj.event_v.get('plan_execution_id')
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan_execution_id)
        plan_ex_obj.state = states.PAUSED
        plan_ex_obj.pause_time = timezone.now()
        if not plan.PlanExecutionModel.objects.filter(run_id=plan_ex_obj.model.run_id). \
                exclude(state__in=states.PLAN_FINAL_STATES + [states.PAUSED]).exists():
            run_obj = run.Run(run_model_id=plan_ex_obj.model.run_id)
            run_obj.state = states.PAUSED
            run_obj.pause_time = timezone.now()

    return 0


def process_trigger(event_obj: Event) -> None:
    """
    Process callback and run desired StageExecution.
    :param event_obj: Event object
    :return: None
    """
    trigger_id = event_obj.event_v.get("trigger_id")
    logger.logger.debug("Processing trigger.", event_v=event_obj.event_v)
    stage_ex_id = stage.StageExecutionModel.objects.get(trigger_id=trigger_id).id
    stage_ex = stage.StageExecution(stage_execution_id=stage_ex_id)

    if stage_ex.model.stage_model.trigger_type == constants.HTTP_LISTENER and stage_ex.state == states.AWAITING:
        stage_ex.execute()

    elif stage_ex.model.stage_model.trigger_type == constants.MSF_LISTENER and stage_ex.state == states.AWAITING:
        session_name = f"{stage_ex.model.stage_model.name}_session"

        # TODO_SIEMENS: When using MSF_LISTENER send also msf-session-type within event. Here hard-coded.
        session_type = SessionModel.MSF_SHELL_TYPE

        session.create_session(stage_ex.model.plan_execution_id, event_obj.event_v.get("parameters"), session_name,
                               session_type)
        stage_ex.execute()

    else:
        logger.logger.warn("Invalid Trigger type.", trigger_type=stage_ex.model.stage_model.trigger_type,
                           stage_ex=stage_ex_id)

    return None


def process_healthcheck(event_obj: Event, worker_model_id: Union[int, Type[int]]) -> int:
    """
    Process healthcheck event
    :param event_obj: Event object
    :param worker_model_id: Worker ID
    :return: 0 if UP, -1 if DOWN
    """
    logger.logger.debug("Processing healthcheck", event_v=event_obj.event_v)
    worker_obj = worker.Worker(worker_model_id=worker_model_id)
    if event_obj.event_v.get(constants.RETURN_CODE) == 0:
        worker_obj.state = states.UP
        return 0
    else:
        worker_obj.state = states.DOWN
        return -1


def process_list_sessions(event_v: dict, reply_to: str or None) -> list:
    return list()


def process_list_modules(event_v: dict, reply_to: str or None) -> list:
    return list()


def process_kill_execution(event_v: dict, step_execution_id: Union[int, Type[int]]) -> int:
    return 0


def process_scheduler(event_obj: Event) -> int:
    """
    Process scheduler event
    :param event_obj: Event object
    :return: -1 if failed, otherwise relevant data (eg. ID of scheduled job)
    """
    logger.logger.debug("Processing scheduler event", event_v=event_obj.event_v)
    scheduler_action = event_obj.event_v.get(constants.EVENT_ACTION)
    scheduler_args = event_obj.event_v.get('args')
    ret_val = -1
    scheduler_obj = scheduler.SchedulerService()
    if scheduler_action == constants.ADD_JOB:
        ret_val = scheduler_obj.exposed_add_job(**scheduler_args)
    if scheduler_action == constants.ADD_REPEATING_JOB:
        ret_val = scheduler_obj.exposed_add_repeating_job(**scheduler_args)
    if scheduler_action == constants.RESCHEDULE_JOB:
        ret_val = scheduler_obj.exposed_reschedule_job(**scheduler_args)
    if scheduler_action == constants.PAUSE_JOB:
        ret_val = scheduler_obj.exposed_pause_job(**scheduler_args)
    if scheduler_action == constants.RESUME_JOB:
        ret_val = scheduler_obj.exposed_resume_job(**scheduler_args)
    if scheduler_action == constants.REMOVE_JOB:
        ret_val = scheduler_obj.exposed_remove_job(**scheduler_args)
    if scheduler_action == constants.GET_JOBS:
        ret_val = scheduler_obj.exposed_get_jobs()
    if scheduler_action == constants.PAUSE_SCHEDULER:
        ret_val = scheduler_obj.exposed_pause_scheduler()
    if scheduler_action == constants.RESUME_SCHEDULER:
        ret_val = scheduler_obj.exposed_resume_scheduler()
    if scheduler_action == constants.EVENT_HEALTH_CHECK:
        ret_val = scheduler_obj.health_check()

    return ret_val


def process_control_request(message: amqpstorm.Message):
    """
    Proces control event request
    :param message: received message
    :param ctx: Context
    :return:
    """

    message_body = json.loads(message.body)

    event_t = message_body.get('event_t')
    event_v = message_body.get('event_v')
    event_obj = Event(event_t, event_v)
    logger.logger.info("Processing control request", event_v=event_obj.event_v)
    ret_val = None

    if event_t == constants.SCHEDULER:
        try:
            ret_val = process_scheduler(event_obj)
        except Exception as ex:
            logger.logger.error("could not schedule function", ex=str(ex))
            ret_val = -1

    return ret_val
