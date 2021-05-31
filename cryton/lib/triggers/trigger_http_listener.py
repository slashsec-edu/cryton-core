import schema
from cryton.lib.models import stage, worker
from cryton.lib.util.util import Rpc
from cryton.lib.util import states, logger, constants
from cryton.etc import config


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
        worker_obj = worker.Worker(worker_model_id=self.stage_execution_obj.model.plan_execution.worker.id)
        worker_rpc = Rpc()

        event_v = {"trigger_type": "HTTP", "reply_to": config.Q_EVENT_RESPONSE_NAME,
                   "stage_execution_id": self.stage_execution_id}
        event_v.update(self.trigger_args)
        args = {"event_v": event_v}

        try:
            resp = worker_rpc.call(worker_obj.control_q_name, constants.EVENT_START_TRIGGER, args)
        except Exception as ex:
            logger.logger.error(f"Couldn't start Stage Execution trigger. {str(ex)}",
                                stage_execution_id=self.stage_execution_id)
            raise ex
        finally:
            worker_rpc.close()

        if resp is None:
            logger.logger.error("Couldn't start Stage Execution trigger - RPC timeout.",
                                stage_execution_id=self.stage_execution_id)
        elif resp.get('event_v').get('return_code') == 0:
            logger.logger.info("Stage Execution trigger started.", stage_execution_id=self.stage_execution_id)
        else:
            logger.logger.info("Couldn't start Stage Execution trigger.", stage_execution_id=self.stage_execution_id)

        self.stage_execution_obj.state = states.AWAITING

    def stop(self):
        """
        Stop HTTP listener on execution worker.
        :return: response code from worker
        """
        worker_obj = worker.Worker(worker_model_id=self.stage_execution_obj.model.plan_execution.worker.id)
        worker_rpc = Rpc()

        event_v = {"trigger_type": "HTTP", "reply_to": config.Q_EVENT_RESPONSE_NAME,
                   "stage_execution_id": self.stage_execution_id}
        event_v.update({"host": self.trigger_args.get("host")})
        event_v.update({"port": self.trigger_args.get("port")})
        args = {"event_v": event_v}

        try:
            resp = worker_rpc.call(worker_obj.control_q_name, constants.EVENT_STOP_TRIGGER, args)
        except Exception as ex:
            logger.logger.error(f"Couldn't stop Stage Execution trigger. {str(ex)}",
                                stage_execution_id=self.stage_execution_id)
            raise ex
        finally:
            worker_rpc.close()

        if resp is None:
            logger.logger.error("Couldn't stop Stage Execution trigger - RPC timeout.",
                                stage_execution_id=self.stage_execution_id)
        elif resp.get('event_v').get('return_code') == 0:
            logger.logger.info("Stage Execution trigger stopped.", stage_execution_id=self.stage_execution_id)
        else:
            logger.logger.info("Couldn't stop Stage Execution trigger.", stage_execution_id=self.stage_execution_id)
