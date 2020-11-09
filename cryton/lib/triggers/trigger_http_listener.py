import schema
from cryton.lib import (
    stage
)


class TriggerHTTPListener:
    """
    Trigger type 'HTTPListener'
    """
    arg_schema = schema.Schema({
        'host': str,
        'port': int,
        'routes': [
            {
                'path': str,
                'method': str,
                'parameters': [
                    {
                        'name': str,
                        'value': str
                    }
                ]
            }
        ]
    })

    def __init__(self, **kwargs):
        """
        :param kwargs:
            stage_excecution_id: int
        """
        self.stage_execution_id = kwargs.get("stage_execution_id")
        self.stage_execution_obj = stage.StageExecution(stage_execution_id=self.stage_execution_id)
        self.trigger_args = self.stage_execution_obj.model.stage_model.trigger_args

    def start(self):
        """
        Start HTTP listener on execution worker.

        :return: response code from worker
        """

        # worker_addr = self.stage_execution_obj.model.worker.address

        # TODO start listener on Worker node by sending rabbit message
        # channel = util.get_grpc_channel(worker_addr, worker_port)

        # stub = listener_pb2_grpc.HTTPListenerStub(channel)
        #
        # args = listener_pb2.listener_args(args=json.dumps(args))
        # return stub.start_listener(args).ret
        raise NotImplementedError

    def stop(self):
        """
        Stop HTTP listeners on execution worker.

        :return: response code from worker
        """
        # worker_addr = self.model.worker.address

        # TODO start listener on Worker node by sending rabbit message
        #
        # channel = util.get_grpc_channel(worker_addr, worker_port)
        # stub = listener_pb2_grpc.HTTPListenerStub(channel)
        #
        # return stub.stop_listeners(self.model.id).ret

        raise NotImplementedError
