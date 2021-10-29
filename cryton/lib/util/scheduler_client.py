from datetime import datetime

from cryton.etc import config
from cryton.lib.util.util import Rpc
from cryton.lib.util import constants

from cryton.lib.util.logger import logger

SCHEDULER_T = 'SCHEDULER'


def schedule_function(execute_function: callable, function_args: list, start_time: datetime) -> str:
    """
    Schedule a job

    :param execute_function: Function/method to be scheduled
    :param function_args: Function arguments
    :param start_time: Start time of function
    :return: ID of the scheduled job
    """
    logger.debug("Scheduling function", execute_function=str(execute_function))
    with Rpc() as rpc:

        args = {
            'execute_function': execute_function,
            'function_args': function_args,
            'start_time': start_time.isoformat()
        }
        event_info = {constants.EVENT_T: SCHEDULER_T,
                      constants.EVENT_V: {constants.EVENT_ACTION: constants.ADD_JOB, "args": args}}
        logger.debug("Scheduling job", execute_function=execute_function)

        resp = rpc.call(config.Q_CONTROL_REQUEST_NAME, event_info)
        if resp is None:
            logger.error("rpc timeouted")
            return ""
        else:
            logger.debug("Got response", resp=resp)
            job_scheduled_id = resp.get(constants.RETURN_VALUE)

    return job_scheduled_id


def schedule_repeating_function(execute_function: callable, seconds: int) -> str:
    """
    Schedule a job

    :param execute_function: Function/method to be scheduled
    :param seconds: Interval in seconds
    :return: ID of the scheduled job
    """
    logger.debug("Scheduling repeating function", execute_function=str(execute_function))
    with Rpc() as rpc:
        args = {
            'execute_function': execute_function,
            'seconds': seconds,
        }
        event_info = {constants.EVENT_T: SCHEDULER_T,
                      constants.EVENT_V: {constants.EVENT_ACTION: constants.ADD_REPEATING_JOB, 'args': args}}
        resp = rpc.call(config.Q_CONTROL_REQUEST_NAME, event_info)
        job_scheduled_id = resp.get(constants.RETURN_VALUE)

    return job_scheduled_id


def remove_job(job_id: str) -> int:
    """
    Removes s job
    :param job_id: APS job ID
    :return: 0
    """
    logger.debug("Removing job", job_id=job_id)
    with Rpc() as rpc:
        args = {
            'job_id': job_id
        }
        event_info = {constants.EVENT_T: SCHEDULER_T,
                      constants.EVENT_V: {constants.EVENT_ACTION: constants.REMOVE_JOB, 'args': args}}
        rpc.call(config.Q_CONTROL_REQUEST_NAME, event_info)

    return 0


def health_check() -> bool:
    """

    :return: True or False
    """
    rpc = Rpc()
    args = {}
    event_info = {constants.EVENT_T: SCHEDULER_T,
                  constants.EVENT_V: {constants.EVENT_ACTION: constants.EVENT_HEALTH_CHECK, 'args': args}}
    resp = rpc.call(config.Q_CONTROL_REQUEST_NAME, event_info)
    health = resp.get('return_value')
    if health != 0:
        return False
    return True
