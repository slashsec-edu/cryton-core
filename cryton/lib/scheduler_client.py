from datetime import datetime

import rpyc

from cryton.etc import config


def schedule_function(execute_function: callable, function_args: list, start_time: datetime) -> str:
    """
    Schedule a job

    :param execute_function: Function/method to be scheduled
    :param function_args: Function arguments
    :param start_time: Start time of function
    :return: ID of the scheduled job
    """
    try:
        conn = rpyc.connect(config.LHOSTNAME, config.LPORT, config={"allow_all_attrs": True, 'allow_pickle': True})
    except ConnectionRefusedError as ex:
        raise ConnectionRefusedError("Could not connect to Scheduler service. Original exception: {}".format(ex))
    job_scheduled_id = conn.root.exposed_add_job(execute_function, function_args, start_time)

    return job_scheduled_id


def schedule_repeating_function(execute_function: callable, seconds: int) -> str:
    """
    Schedule a job

    :param execute_function: Function/method to be scheduled
    :param seconds: Interval in seconds
    :return: ID of the scheduled job
    """
    try:
        conn = rpyc.connect(config.LHOSTNAME, config.LPORT, config={"allow_all_attrs": True, 'allow_pickle': True})
    except ConnectionRefusedError as ex:
        raise ConnectionRefusedError("Could not connect to Scheduler service. Original exception: {}".format(ex))
    job_scheduled_id = conn.root.exposed_add_repeating_job(execute_function, seconds)

    return job_scheduled_id


def remove_job(job_id: str) -> int:
    """
    Removes s job
    :param job_id: APS job ID
    :return: 0
    """
    try:
        conn = rpyc.connect(config.LHOSTNAME, config.LPORT, config={"allow_all_attrs": True, 'allow_pickle': True})
    except ConnectionRefusedError as ex:
        raise ConnectionRefusedError("Could not connect to Scheduler service. Original exception: {}".format(ex))
    conn.root.exposed_remove_job(job_id)

    return 0


def health_check() -> bool:
    """

    :return: True or False
    """
    try:
        conn = rpyc.connect(config.LHOSTNAME, config.LPORT, config={"allow_all_attrs": True, 'allow_pickle': True})
    except ConnectionRefusedError:
        return False
    health = conn.root.health_check()
    if health != 0:
        return False
    return True
