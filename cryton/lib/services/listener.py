import json
import time
from threading import Thread, Lock
from multiprocessing import Process, Event

import amqpstorm

from cryton.lib.util import constants, logger, states, util, exceptions
from cryton.lib.models import stage, plan, step, run, event
from cryton.etc import config

from cryton.cryton_rest_api.models import (
    CorrelationEvent
)

from cryton.lib.services.scheduler import SchedulerService
from django.utils import timezone


sch_start_lock = Lock()


class ProcessListener:
    def __init__(self, queue: str, callback_executable: exec):
        """
        ProcessListener
        :param queue: Rabbit queue, that will be consumed.
        :param callback_executable: Custom Rabbit callback.
        """
        self.queue = queue
        self.callback_executable = callback_executable
        self.max_retries = 5
        self._connection: amqpstorm.Connection or None = None
        self._stopped = Event()
        logger.logger.debug('ProcessListener created.', queue=self.queue, callback=self.callback_executable)

    def start(self) -> None:
        """
        Start a Listener.
        :return: None
        """
        self._stopped.clear()
        self._create_connection()

        while not self._stopped.is_set() and self._connection.is_open:
            try:
                channel = self._connection.channel()
                channel.basic.qos(1)
                channel.queue.declare(self.queue)
                channel.basic.consume(self._execute_custom_callback, self.queue)
                logger.logger.info("Queue declared and consuming", queue=self.queue)
                channel.start_consuming()

            except amqpstorm.AMQPError as ex:
                # If an error occurs, re-connect and let listeners re-open the channels.
                logger.logger.warning(ex)
                self._create_connection()
        return None

    def _create_connection(self) -> None:
        """
        Create a Rabbit connection.
        :return: None
        """
        attempts = 0
        while True:
            attempts += 1
            if self._stopped.is_set():
                break
            try:
                self._connection = util.rabbit_connection()
                break
            except (amqpstorm.AMQPError, exceptions.RabbitConnectionError) as ex:
                logger.logger.warning(ex)
                if self.max_retries and attempts > self.max_retries:
                    logger.logger.error('max number of retries reached')
                    raise Exception('max number of retries reached')
                time.sleep(min(attempts * 2, 30))
        return None

    def stop(self) -> None:
        """
        Stop.
        :return: None
        """
        self._connection.close()
        self._stopped.set()
        return None

    def _execute_custom_callback(self, message: amqpstorm.Message) -> None:
        """
        Start custom callback in new Thread.
        :param message: Received RabbitMQ message.
        :return: None
        """
        thread = Thread(target=self._custom_callback, args=(message,))
        thread.daemon = True
        thread.start()
        return None

    def _custom_callback(self, message: amqpstorm.Message) -> None:
        """
        Rabbit callback for executing custom callbacks.
        :param message: Received RabbitMQ message.
        :return: None
        """
        message.ack()
        logger.logger.debug('Running callback.', callback=self.callback_executable, message=message.to_dict())

        self.callback_executable(message)
        return None


class Listener:
    def __init__(self):
        """
        Listener.
        """
        self._listeners = {}
        self._stopped = Event()
        self.scheduler = SchedulerService()

        logger.logger.debug('Listener created.')

    def start(self) -> None:
        """
        Create queues and their listeners in processes.
        :return: None
        """

        # Pair up queues and callbacks
        queues = {config.Q_ATTACK_RESPONSE_NAME: self.step_resp_callback,
                  config.Q_CONTROL_RESPONSE_NAME: self.control_resp_callback,
                  config.Q_EVENT_RESPONSE_NAME: self.event_callback,
                  config.Q_CONTROL_REQUEST_NAME: self.control_req_callback}

        # Prepare process for each queue
        for queue, callback in queues.items():
            self._create_process_for_queue(queue, callback)

        # Start prepared processes
        for process in self._listeners.values():
            process.start()

        # Start listener with the pairs
        logger.logger.info("Started listener", test=1)

        # Keep Listener alive
        while not self._stopped.is_set():
            time.sleep(5)
        return None

    def stop(self) -> None:
        """
        Stop Listener and it's listeners.
        :return: None
        """
        for proc_listener, process in self._listeners.items():
            try:
                proc_listener.stop()
            except Exception as ex:
                logger.logger.warning("ProcessListener couldn't be closed", exception=str(ex))
                process.kill()

        self._stopped.set()
        logger.logger.debug("Listener stopped")
        return None

    def _create_process_for_queue(self, queue: str, callback: exec) -> None:
        """
        Create ProcessListener and assign it into Process.
        :param queue: Rabbit queue, that will be consumed.
        :param callback: Custom Rabbit callback.
        :return: None
        """
        proc_listener = ProcessListener(queue, callback)
        process = Process(target=proc_listener.start)
        self._listeners.update({proc_listener: process})
        return None

    @staticmethod
    def handle_paused(step_exec_obj: step.StepExecution) -> None:
        """
        Check for PAUSED states.
        :param step_exec_obj: StepExecution object to check
        :return: None
        """
        logger.logger.info("Handling Step pause", step_execution_id=step_exec_obj.model.id)
        stage_exec_obj = stage.StageExecution(stage_execution_id=step_exec_obj.model.stage_execution_id)
        if stage_exec_obj.state not in states.STAGE_FINAL_STATES:
            stage_exec_obj.state = states.PAUSED
            stage_exec_obj.pause_time = timezone.now()
            step_exec_obj.pause_successors()  # PAUSE all successors so they can be executed after UNPAUSE
            logger.logger.info("stageexecution paused", stage_execution_id=stage_exec_obj.model.id)

        if not stage.StageExecutionModel.objects.filter(plan_execution_id=stage_exec_obj.model.plan_execution_id)\
                .exclude(state__in=states.PLAN_STAGE_PAUSE_STATES).exists():
            msg = dict(event_t=constants.PAUSE,
                       event_v=dict(result=constants.RESULT_OK,
                                    plan_execution_id=step_exec_obj.model.stage_execution.plan_execution_id))
            util.rabbit_send_oneway_msg(queue_name=config.Q_EVENT_RESPONSE_NAME,
                                        msg=json.dumps(msg))

    @staticmethod
    def get_correlation_event(correlation_id: str) -> None or CorrelationEvent:
        """
        Get CorrelationEvent with timeout.
        :param correlation_id: Correlation ID
        :return: None
        """
        for i in range(3):
            try:
                correlation_event_obj = CorrelationEvent.objects.get(correlation_id=correlation_id)
                return correlation_event_obj
            except CorrelationEvent.DoesNotExist:
                time.sleep(0.1)

        return None

    def step_resp_callback(self, message: amqpstorm.Message) -> None:
        """
        Process StepExecution response.
        :param message: RabbitMQ response
        :return: None
        """
        logger.logger.debug("Received Step response callback", message_id=message.message_id)
        # Get correlation id and message body
        correlation_id = message.correlation_id
        message_body = json.loads(message.body)

        # Get correlated object from DB
        correlation_event_obj = self.get_correlation_event(correlation_id)
        if correlation_event_obj is None:
            # Ignore, but log. Might be repeated response.
            logger.logger.warn("Received nonexistent correlation_id.", correlation_id=correlation_id)
            return None

        step_execution_id = correlation_event_obj.step_execution_id

        # Create execution object
        step_exec_obj = step.StepExecution(step_execution_id=step_execution_id)

        # Log
        logger.logger.info("stepexecution finished", step_execution_id=step_exec_obj.model.id,
                           step_name=step_exec_obj.model.step_model.name, status=constants.STATUS_OK)

        # Postprocess all needed things, eg. sessions created, output storage etc
        logger.logger.debug(step_execution_id=step_exec_obj.model.id, message_body=message_body)
        step_exec_obj.postprocess(message_body)

        # Set IGNORE to successors which should be ignored
        step_exec_obj.ignore_successors()

        # Check if stage, plan or run should be set to FINISHED state
        self.handle_finished(step_exec_obj)

        # Check if execution is being PAUSED
        if plan.PlanExecution(plan_execution_id=step_exec_obj.model.stage_execution.plan_execution_id).state \
                == states.PAUSING:
            self.handle_paused(step_exec_obj)

        else:
            # Execute successors
            step_exec_obj.execute_successors()

        # Delete the correlation object
        correlation_event_obj.delete()

        return None

    def control_resp_callback(self, message: amqpstorm.Message) -> None:
        """
        Process control response.
        :param message: RabbitMQ response
        :return: None
        """
        logger.logger.debug("Received control response callback", message_id=message.message_id)
        # Get correlation id and message body
        correlation_id = message.correlation_id
        message_body = json.loads(message.body)

        # Get correlated object from DB
        correlation_event_obj = self.get_correlation_event(correlation_id)
        if correlation_event_obj is None:
            # Ignore, but log. Might be repeated response.
            logger.logger.warn("Received nonexistent correlation_id.", correlation_id=correlation_id)
            return None

        # Type of control event
        event_t = message_body.get('event_t')

        # Value of control event
        event_v = message_body.get('event_v')
        ret_val = event.process_control_event(event_t, event_v, correlation_event_obj, message.reply_to)
        ret_val = {constants.RETURN_VALUE: ret_val}
        util.send_response(message, json.dumps(ret_val))

        # Delete the correlation object
        correlation_event_obj.delete()

        return None

    @staticmethod
    def control_req_callback(message: amqpstorm.Message) -> None:
        """
        Process control request.
        :param message: RabbitMQ request
        :return: None
        """
        logger.logger.debug("Received control request callback", message_id=message.message_id)
        ret_val = event.process_control_request(message)
        ret_val = {constants.RETURN_VALUE: ret_val}
        util.send_response(message, json.dumps(ret_val))

        return None

    @staticmethod
    def event_callback(message: amqpstorm.Message) -> None:
        """
        Process event.
        :param message: RabbitMQ response
        :return: None
        """
        logger.logger.debug("Received event callback", message_id=message.message_id)
        # Get message body
        message_body = json.loads(message.body)

        # Type of control event
        event_t = message_body.get('event_t')

        # Value of control event
        event_v = message_body.get('event_v')

        event_obj = event.Event(event_t=event_t, event_v=event_v)
        event.process_event(event_obj)

        return None

    @staticmethod
    def handle_finished(step_exec_obj: step.StepExecution) -> None:
        """
        Check for FINISHED states.
        :param step_exec_obj: StepExecution object to check
        :return: None
        """
        logger.logger.debug("Handling finished Step", step_id=step_exec_obj.model.step_model_id)
        stage_exec_obj = stage.StageExecution(stage_execution_id=step_exec_obj.model.stage_execution_id)
        if stage_exec_obj.all_steps_finished:
            logger.logger.info("stagexecution finished", stage_execution_id=stage_exec_obj.model.id)
            stage_exec_obj.state = states.FINISHED
            stage_exec_obj.finish_time = timezone.now()
            stage_exec_obj.execute_subjects_to_dependency()
            stage_exec_obj.trigger.stop()

            plan_exec_obj = plan.PlanExecution(plan_execution_id=stage_exec_obj.model.plan_execution_id)
            if plan_exec_obj.all_stages_finished:
                logger.logger.info("planexecution finished", plan_execution_id=plan_exec_obj.model.id)
                plan_exec_obj.state = states.FINISHED
                plan_exec_obj.finish_time = timezone.now()
                plan_exec_obj.model.save()

                run_obj = run.Run(run_model_id=plan_exec_obj.model.run_id)
                if run_obj.all_plans_finished:
                    logger.logger.info("run finished", run_id=run_obj.model.id)
                    run_obj.state = states.FINISHED
                    run_obj.finish_time = timezone.now()
