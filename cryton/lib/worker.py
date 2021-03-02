from typing import Union, Type
from time import sleep
import json
from amqpstorm import Message
from django.core import exceptions as django_exc

from cryton.etc import config
from cryton.lib import (
    exceptions,
    util,
    states
)
from cryton.cryton_rest_api.models import (
    WorkerModel,
    CorrelationEvent
)

import uuid


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

        msg = {'event_t': 'HEALTHCHECK'}

        worker_rpc = WorkerRpc(healthcheck=True)

        response = worker_rpc.call(self.control_q_name, 'HEALTHCHECK', msg, 5)

        if response is not None and response.get('event_v').get('return_code') == 0:
            self.state = states.UP
            return True
        else:
            self.state = states.DOWN
            return False


class WorkerRpc(object):

    def __init__(self, healthcheck: bool = False):
        """

        :return:
        """

        if healthcheck:
            self.queue_arguments = {'x-expires': 10000}
        else:
            self.queue_arguments = {}
        self.channel = None
        self.response = None
        self.connection = None
        self.callback_queue = None
        self.correlation_id = None
        self.open()

    def open(self):
        self.connection = util.rabbit_connection()

        self.channel = self.connection.channel()

        resp_q_name = str(uuid.uuid4())
        self.channel.queue.declare(queue=resp_q_name, exclusive=False, arguments=self.queue_arguments)
        self.callback_queue = resp_q_name

        self.channel.basic.consume(self.on_response, no_ack=True,
                                   queue=self.callback_queue)

    def close(self):
        self.channel.queue.delete(queue=self.callback_queue)
        self.channel.stop_consuming()
        self.channel.close()
        self.connection.close()

    def call(self, q_name, method_name, method_args=None, time_limit: float = config.WORKER_HEALTHCHECK_TIMEOUT) -> dict:
        if not method_args:
            method_args = {}

        msg = {'event_t': method_name,
               **method_args}
        msg_json = json.dumps(msg)

        message = Message.create(self.channel, body=msg_json)
        message.reply_to = self.callback_queue
        self.correlation_id = message.correlation_id
        message.publish(routing_key=q_name)

        check = time_limit
        self.channel.process_data_events()
        while not self.response:
            self.channel.process_data_events()
            check -= 1
            sleep(1)
            if check <= 0:
                break
        self.channel.queue.delete(self.callback_queue)
        return self.response

    def on_response(self, message):
        if self.correlation_id != message.correlation_id:
            return
        self.response = json.loads(message.body)
