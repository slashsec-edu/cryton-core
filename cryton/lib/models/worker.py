from typing import Union, Type
from django.core import exceptions as django_exc

from cryton.lib.util import exceptions, states, util, constants
from cryton.cryton_rest_api.models import (
    WorkerModel
)


class Worker:
    def __init__(self, **kwargs):
        """
        :param kwargs:
        name: str
        address: str
        q_prefix: str
        state: str
        """
        worker_model_id = kwargs.get('worker_model_id')
        if worker_model_id:
            try:
                self.model = WorkerModel.objects.get(id=worker_model_id)
            except django_exc.ObjectDoesNotExist:
                raise exceptions.WorkerObjectDoesNotExist(
                    "WorkerModel with id {} does not exist.".format(worker_model_id), worker_model_id
                )

        else:
            self.model = WorkerModel.objects.create(**kwargs)

    def delete(self):
        self.model.delete()

    @property
    def model(self) -> Union[Type[WorkerModel], WorkerModel]:
        self.__model.refresh_from_db()
        return self.__model

    @model.setter
    def model(self, value: WorkerModel):
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
    def address(self) -> str:
        return self.model.address

    @address.setter
    def address(self, value: str):
        model = self.model
        model.address = value
        model.save()

    @property
    def q_prefix(self) -> str:
        return self.model.q_prefix

    @q_prefix.setter
    def q_prefix(self, value: str):
        model = self.model
        model.q_prefix = value
        model.save()

    @property
    def state(self) -> str:
        return self.model.state

    @state.setter
    def state(self, value: str):
        model = self.model
        model.state = value
        model.save()

    @property
    def attack_q_name(self):
        worker_q_name = "cryton_worker.{}.attack.request".format(self.q_prefix)
        return worker_q_name

    @property
    def control_q_name(self):
        worker_q_name = "cryton_worker.{}.control.request".format(self.q_prefix)
        return worker_q_name

    def healthcheck(self) -> bool:
        """
        Check if Worker is consuming its attack queue
        :return:
        """
        event_info = {constants.EVENT_T: constants.EVENT_HEALTH_CHECK,
                      constants.EVENT_V: {}}

        with util.Rpc() as worker_rpc:
            response = worker_rpc.call(self.control_q_name, event_info, 5)
            if response is not None and response.get('event_v').get(constants.RETURN_CODE) == 0:
                self.state = states.UP
                return True
            else:
                self.state = states.DOWN
                return False
