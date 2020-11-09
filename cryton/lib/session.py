from typing import Union, Type

from django.core.exceptions import ObjectDoesNotExist

from cryton.cryton_rest_api.models import (
    SessionModel,
    PlanExecutionModel
)
from cryton.lib import (
    exceptions,
    worker
)


def create_session(plan_execution_id: Union[Type[int], int], session_id: str,
                   session_name: str = None) -> SessionModel:
    """

    :param plan_execution_id:
    :param session_id:
    :param session_name:
    :return:
    """

    if not PlanExecutionModel.objects.filter(id=plan_execution_id).exists():
        raise exceptions.PlanExecutionDoesNotExist(plan_execution_id=str(plan_execution_id))

    sess_obj = SessionModel.objects.create(plan_execution_id=plan_execution_id,
                                           session_name=session_name,
                                           session_id=session_id,
                                           )

    return sess_obj


def get_msf_session_id(session_name: str, plan_execution_id: Union[Type[int], int]) -> str:
    """
    Get a Metasploit session ID by the defined session name

    :param str session_name: Session name provided in input file
    :param int plan_execution_id: ID of the desired plan execution
    :raises:
        SessionObjectDoesNotExist: If Session doesn't exist
    :return: Metasploit session ID
    """
    try:
        msf_session_id = SessionModel.objects.get(session_name=session_name,
                                                  plan_execution_id=plan_execution_id).session_id
    except ObjectDoesNotExist as ex:
        raise exceptions.SessionObjectDoesNotExist(ex, session_name=session_name,
                                                   plan_execution_id=plan_execution_id)
    return msf_session_id


def set_msf_session_id(session_name: str,
                       msf_session_id: str,
                       plan_execution_id: Union[Type[int], int]) -> int:
    """
    Update metasploit session ID

    :param int plan_execution_id: ID of the desired plan execution
    :param msf_session_id: Metasploit session ID
    :param str session_name: Session name
    :return: ID of the named session
    """

    try:
        named_session = SessionModel.objects.get(session_name=session_name,
                                                 plan_execution_id=plan_execution_id)
    except ObjectDoesNotExist as ex:
        raise exceptions.SessionObjectDoesNotExist(ex, session_name=session_name,
                                                   plan_execution_id=plan_execution_id)
    named_session.session_id = msf_session_id
    named_session.save()

    return named_session.id


def get_session_ids(target_ip: str, plan_execution_id: Union[Type[int], int]) -> list:
    """
    Get list of session IDs to specified IP

    :param str target_ip: Target IP
    :param int plan_execution_id: ID of the desired Plan execution
    :return: List of session IDs
    """
    worker_obj = worker.Worker(worker_model_id=PlanExecutionModel.objects.get(id=plan_execution_id).worker.id)
    worker_rpc = worker.WorkerRpc()

    args = {'target_ip': target_ip}
    try:
        resp = worker_rpc.call(worker_obj.control_q_name, 'LIST_SESSIONS', args)
    except Exception:
        raise
    finally:
        worker_rpc.close()
    resp_dict = json.loads(resp)
    sess_list = resp_dict.get('event_v').get('session_list')
    return sess_list
