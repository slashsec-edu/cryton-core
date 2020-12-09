import json
import time
from datetime import datetime
from threading import Thread
from multiprocessing import Process, Event

import amqpstorm

from cryton.lib import (
    step,
    stage,
    plan,
    run,
    util,
    logger,
    states,
    constants,
    event
)
from cryton.lib.triggers import (
    triggers
)
from cryton.etc import config

from cryton.cryton_rest_api.models import (
    CorrelationEvent
)


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
            except amqpstorm.AMQPError as ex:
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
        logger.logger.debug('Listener created.')

    def start(self, queues: dict) -> None:
        """
        Create queues and their listeners in processes.
        :param queues: Rabbit queues with callbacks (queue_name: queue_callback)
        :return: None
        """
        # Prepare process for each queue
        for queue, callback in queues.items():
            self._create_process_for_queue(queue, callback)

        # Start prepared processes
        for process in self._listeners.values():
            process.start()

        # Keep Listener alive
        while not self._stopped:
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


def handle_finished(step_exec_obj: step.StepExecution) -> None:
    """
    Check for FINISHED states.
    :param step_exec_obj: StepExecution object to check
    :return: None
    """
    stage_exec_obj = stage.StageExecution(stage_execution_id=step_exec_obj.model.stage_execution_id)
    if stage_exec_obj.all_steps_finished:
        logger.logger.info("stagexecution finished", stage_execution_id=stage_exec_obj.model.id)
        stage_exec_obj.state = states.FINISHED
        stage_exec_obj.finish_time = datetime.utcnow()
        if stage_exec_obj.model.stage_model.trigger_type == constants.DELTA:
            triggers.TriggerType[constants.DELTA].value(stage_execution_id=stage_exec_obj.model.id)\
                .execute_subjects_to_dependency()

        plan_exec_obj = plan.PlanExecution(plan_execution_id=stage_exec_obj.model.plan_execution_id)
        if plan_exec_obj.all_stages_finished:
            logger.logger.info("planexecution finished",
                               plan_execution_id=plan_exec_obj.model.id)
            plan_exec_obj.state = states.FINISHED
            plan_exec_obj.finish_time = datetime.utcnow()
            run_obj = run.Run(run_model_id=plan_exec_obj.model.run_id)
            if run_obj.all_plans_finished:
                logger.logger.info("run finished", run_id=run_obj.model.id)
                run_obj.state = states.FINISHED
                run_obj.finish_time = datetime.utcnow()

    return None


def handle_paused(step_exec_obj: step.StepExecution) -> None:
    """
    Check for PAUSED states.
    :param step_exec_obj: StepExecution object to check
    :return: None
    """
    stage_exec_obj = stage.StageExecution(stage_execution_id=step_exec_obj.model.stage_execution_id)
    stage_exec_obj.state = states.PAUSED
    stage_exec_obj.pause_time = datetime.utcnow()
    # PAUSE all successors so they can be executed after UNPAUSE
    step_exec_obj.pause_successors()
    logger.logger.info("stageexecution paused", stage_execution_id=stage_exec_obj.model.id)
    if not stage.StageExecutionModel.objects.filter(
            plan_execution_id=stage_exec_obj.model.plan_execution_id,
            state__in=[states.RUNNING, states.PAUSING]).exists():
        msg = dict(event_t='PAUSE',
                   event_v=dict(result='OK', plan_execution_id=step_exec_obj.model.stage_execution.plan_execution_id))
        util.rabbit_send_oneway_msg(queue_name=config.Q_EVENT_RESPONSE_NAME,
                                    msg=json.dumps(msg))

    return None


def get_correlation_event(correlation_id: str) -> None:
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


def step_resp_callback(message: amqpstorm.Message) -> None:
    """
    Process StepExecution response.
    :param message: RabbitMQ response
    :return: None
    """
    # Get correlation id and message body
    correlation_id = message.correlation_id
    message_body = json.loads(message.body)

    # Get correlated object from DB
    correlation_event_obj = get_correlation_event(correlation_id)
    if correlation_event_obj is None:
        # Ignore, but log. Might be repeated response.
        logger.logger.warn("Received nonexistent correlation_id.", correlation_id=correlation_id)
        return None

    step_execution_id = correlation_event_obj.event_identification_value

    # Create execution object
    step_exec_obj = step.StepExecution(step_execution_id=step_execution_id)

    # Log
    logger.logger.info("stepexecution finished", step_execution_id=step_exec_obj.model.id,
                       step_name=step_exec_obj.model.step_model.name, status='success')

    # Postprocess all needed things, eg. sessions created, output storage etc
    step_exec_obj.postprocess(message_body)

    # Set IGNORE to successors which should be ignored
    step_exec_obj.ignore_successors()

    # Check if execution is being PAUSED
    if plan.PlanExecution(plan_execution_id=step_exec_obj.model.stage_execution.plan_execution_id).state \
            in [states.PAUSING, states.PAUSED]:
        handle_paused(step_exec_obj)

        # Delete the correlation object
        correlation_event_obj.delete()
        return None

    # Execute successors
    step_exec_obj.execute_successors()

    # Check if stage, plan or run should be set to FINISHED state
    handle_finished(step_exec_obj)

    # Delete the correlation object
    correlation_event_obj.delete()

    return None


def control_resp_callback(message: amqpstorm.Message) -> None:
    """
    Process control response.
    :param message: RabbitMQ response
    :return: None
    """
    # Get correlation id and message body
    correlation_id = message.correlation_id
    message_body = json.loads(message.body)

    # Get correlated object from DB
    correlation_event_obj = get_correlation_event(correlation_id)
    if correlation_event_obj is None:
        # Ignore, but log. Might be repeated response.
        logger.logger.warn("Received nonexistent correlation_id.", correlation_id=correlation_id)
        return None

    # Type of control event
    event_t = message_body.get('event_t')

    # Value of control event
    event_v = message_body.get('event_v')
    event.process_control_event(event_t, event_v, correlation_event_obj)

    # Delete the correlation object
    correlation_event_obj.delete()

    return None


def event_callback(message: amqpstorm.Message) -> None:
    """
    Process event.
    :param message: RabbitMQ response
    :return: None
    """
    # Get message body
    message_body = json.loads(message.body)

    # Type of control event
    event_t = message_body.get('event_t')

    # Value of control event
    event_v = message_body.get('event_v')
    event.process_event(event_t, event_v)

    return None


def start() -> None:
    """
    Set up queues with callbacks and start RabbitMQ listener implementation.
    :return: None
    """
    # Pair up queues and callbacks
    queues = {config.Q_ATTACK_RESPONSE_NAME: step_resp_callback, config.Q_CONTROL_RESPONSE_NAME: control_resp_callback,
              config.Q_EVENT_RESPONSE_NAME: event_callback}

    # Start listener with the pairs
    listener_obj = Listener()
    listener_obj.start(queues)

    return None
