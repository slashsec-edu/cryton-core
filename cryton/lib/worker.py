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
        msg = json.dumps(msg)

        # Message expires in 10 seconds
        properties = dict(expiration="10000")

        reply_to = config.Q_CONTROL_RESPONSE_NAME
        correlation_id = util.rabbit_send_msg(self.control_q_name, msg,
                                              self.model.id, reply_to,
                                              properties=properties)

        # Wait until correlation event get's deleted from DB (after successful event processing)
        # after 5 seconds consider DOWN
        for i in range(5):
            try:
                CorrelationEvent.objects.get(correlation_id=correlation_id)
            except django_exc.ObjectDoesNotExist:
                return True
            sleep(1)

        self.state = states.DOWN
        return False


class WorkerRpc(object):

    def __init__(self):
        """

        :return:
        """

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
        result = self.channel.queue.declare(queue=resp_q_name, exclusive=False)
        self.callback_queue = resp_q_name

        self.channel.basic.consume(self._on_response, no_ack=True,
                                   queue=self.callback_queue)

    def close(self):
        self.channel.queue.delete(queue=self.callback_queue)
        self.channel.stop_consuming()
        self.channel.close()
        self.connection.close()

    def call(self, q_name, method_name, method_args):
        self.response = None
        msg = {'event_t': method_name,
               **method_args}
        msg_json = json.dumps(msg)

        message = Message.create(self.channel, body=msg_json)
        message.reply_to = self.callback_queue
        self.correlation_id = message.correlation_id
        message.publish(routing_key=q_name)

        while not self.response:
            self.channel.process_data_events()
        return self.response

    def _on_response(self, message):
        if self.correlation_id != message.correlation_id:
            return
        self.response = message.body
