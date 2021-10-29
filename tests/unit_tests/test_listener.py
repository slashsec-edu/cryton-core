from django.test import TestCase
from cryton.lib.services import listener
from cryton.lib.models import stage, step, plan, run, worker, event
from cryton.lib.util import logger, states
from mock import patch, Mock
import os
import uuid
import threading
import time
from model_bakery import baker
from cryton.cryton_rest_api.models import (
    CorrelationEvent
)
import json


def run_null(*kwargs):
    return 0


mock_exc = Mock()
mock_exc.start.side_effect = run_null

devnull = open(os.devnull, 'w')

queue_name = uuid.uuid4().hex


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch("sys.stdout", devnull)
@patch('amqpstorm.Connection', Mock())
class ProcessListenerTest(TestCase):

    @patch('cryton.lib.util.util.rabbit_connection')
    def setUp(self, mock_rabbit_connection):
        self.proce_list_obj = listener.ProcessListener(queue_name, run_null)
        channel = Mock()
        channel.start_consuming.return_value = 42
        mock_rabbit_connection.return_value = channel

        self.proce_list_obj._create_connection()

    def tearDown(self) -> None:
        self.proce_list_obj.stop()

    def test_start(self):
        t = threading.Thread(target=self.proce_list_obj.start)
        t.start()

        self.assertFalse(self.proce_list_obj._stopped.is_set())

    def test_create_connection(self):
        self.assertFalse(self.proce_list_obj._stopped.is_set())

    def test_stop(self):
        self.assertFalse(self.proce_list_obj._stopped.is_set())
        self.proce_list_obj.stop()
        self.assertTrue(self.proce_list_obj._stopped.is_set())

    @patch('cryton.lib.services.listener.Thread')
    def test_execute_custom_callback(self, mock_thread):
        mock_cc = Mock()

        self.proce_list_obj._custom_callback = mock_cc
        self.proce_list_obj._execute_custom_callback(message='42')
        mock_thread.assert_called_with(target=mock_cc, args=('42',))

    def test_custom_callback(self):
        mock_cc = Mock()
        mock_msg = Mock()

        self.proce_list_obj.callback_executable = mock_cc
        self.proce_list_obj._custom_callback(mock_msg)
        mock_cc.assert_called_with(mock_msg)


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch("sys.stdout", devnull)
@patch('amqpstorm.Connection', Mock())
class ListenerTest(TestCase):

    @patch('cryton.lib.services.listener.SchedulerService')
    def setUp(self, mock_ss):
        self.listener_obj = listener.Listener()

    @patch('cryton.lib.services.listener.Listener._create_process_for_queue', Mock())
    @patch('time.sleep')
    def test_start(self, mock_sleep: Mock):
        self.assertFalse(self.listener_obj._stopped.is_set())
        t = threading.Thread(target=self.listener_obj.start)
        mock_sleep.assert_not_called()
        t.start()
        called = False

        # wait until thread comes to time.sleep
        for i in range(10):
            try:
                mock_sleep.assert_called()
                called = True
                break
            except AssertionError:
                time.sleep(0.1)
                pass
        if not called:
            raise AssertionError("Expected 'sleep' to have been called.")
        self.assertFalse(self.listener_obj._stopped.is_set())
        self.listener_obj.stop()
        self.assertTrue(self.listener_obj._stopped.is_set())

    @patch('cryton.lib.services.listener.Listener._create_process_for_queue', Mock())
    @patch('time.sleep')
    def test_stop(self, mock_sleep: Mock):
        t = threading.Thread(target=self.listener_obj.start)
        mock_sleep.assert_not_called()
        t.start()
        try:
            self.assertFalse(self.listener_obj._stopped.is_set())
            self.listener_obj.stop()
            self.assertTrue(self.listener_obj._stopped.is_set())
        except:
            pass
        else:
            t.join()

    @patch('cryton.lib.util.util.rabbit_connection', Mock())
    def test_create_process_for_queue(self):
        callback = Mock()
        self.assertEqual(len(self.listener_obj._listeners.keys()), 0)
        self.listener_obj._create_process_for_queue(queue_name, callback)
        self.assertEqual(len(self.listener_obj._listeners.keys()), 1)

    @patch('cryton.lib.util.util.rabbit_send_oneway_msg')
    def test_handle_paused(self, mock_send_msg):

        stage_ex_obj = baker.make(stage.StageExecutionModel, state='PAUSING')
        step_obj = baker.make(step.StepModel)

        def set_state(*args, **kwargs):
            stage_ex_obj.state = 'PAUSED'

        mock_send_msg.side_effect = set_state

        step_exec_stats = {
            'step_model_id': step_obj.id,
            'stage_execution': stage_ex_obj
        }

        step_exec_obj = step.StepExecution(**step_exec_stats)

        self.listener_obj.handle_paused(step_exec_obj)
        self.assertEqual(stage_ex_obj.state, 'PAUSED')

    def test_get_correlation_event(self):
        correlation_id = uuid.uuid4().hex
        cor_event = baker.make(CorrelationEvent, correlation_id=correlation_id)
        ret = self.listener_obj.get_correlation_event(correlation_id)

        self.assertEqual(ret, cor_event)

    @patch('cryton.lib.models.step.StepExecution.execute_successors')
    @patch('cryton.lib.models.step.StepExecution.ignore_successors')
    @patch('cryton.lib.models.step.StepExecution.postprocess')
    def test_step_resp_callback(self, mock_post: Mock,
                                mock_ignore: Mock,
                                mock_execute: Mock):
        correlation_id = uuid.uuid4().hex
        run_obj = baker.make(run.RunModel)
        worker_obj = baker.make(worker.WorkerModel)
        plan_ex_obj = plan.PlanExecution(plan_model_id=baker.make(plan.PlanModel).id,
                                         run_id=run_obj.id,
                                         worker_id=worker_obj.id)
        stage_execution = baker.make(stage.StageExecutionModel, plan_execution=plan_ex_obj.model)

        step_obj = baker.make(step.StepModel)
        step_exec_stats = {
            'step_model_id': step_obj.id,
            'stage_execution': stage_execution
        }

        step_exec_stats_obj = step.StepExecution(**step_exec_stats)
        cor_event = baker.make(CorrelationEvent,
                               correlation_id=correlation_id,
                               step_execution_id=step_exec_stats_obj.model.id)

        message = Mock()
        message.correlation_id = correlation_id
        message.body = json.dumps({'test': 1})

        plan_ex_obj.state = states.RUNNING
        plan_ex_obj.state = states.PAUSING
        plan_ex_obj.model.save()

        stage_execution.state = states.RUNNING
        stage_execution.state = states.PAUSING
        stage_execution.save()

        step_exec_stats_obj.state = states.RUNNING
        # step_exec_stats_obj.state = states.PAUSING
        step_exec_stats_obj.model.save()

        patch('cryton.lib.models.plan.PlanExecution', Mock(return_value=plan_ex_obj))

        c1 = CorrelationEvent.objects.get(id=cor_event.id)
        self.listener_obj.step_resp_callback(message)
        with self.assertRaises(CorrelationEvent.DoesNotExist):
            c2 = CorrelationEvent.objects.get(id=cor_event.id)

        mock_post.assert_called_with(json.loads(message.body))
        mock_ignore.assert_called_once()
        mock_execute.assert_not_called()

        plan_ex_obj.state = states.PAUSED
        plan_ex_obj.state = states.RUNNING
        plan_ex_obj.model.save()
        patch('cryton.lib.models.plan.PlanExecution', Mock(return_value=plan_ex_obj))
        baker.make(CorrelationEvent,
                   correlation_id=correlation_id,
                   step_execution_id=step_exec_stats_obj.model.id)
        self.listener_obj.step_resp_callback(message)
        mock_execute.assert_called_once()

    @patch('cryton.lib.models.event.process_control_event', Mock(return_value=42))
    @patch('cryton.lib.util.util.send_response')
    def test_control_resp_callback(self, mock_send_response: Mock):
        correlation_id = uuid.uuid4().hex

        baker.make(CorrelationEvent,
                   correlation_id=correlation_id)

        message = Mock()
        message.correlation_id = correlation_id
        message.body = json.dumps({
            'event_t': 'TYPE',
            'event_v': 'VALUE'
        })
        self.listener_obj.control_resp_callback(message)

        mock_send_response.assert_called_with(message, json.dumps({"return_value": 42}))

    @patch('cryton.lib.models.event.process_control_request', Mock(return_value=42))
    @patch('cryton.lib.util.util.send_response')
    def test_control_req_callback(self, mock_send_response: Mock):
        correlation_id = uuid.uuid4().hex

        baker.make(CorrelationEvent,
                   correlation_id=correlation_id)

        message = Mock()
        message.correlation_id = correlation_id
        message.body = json.dumps({'test': 1})

        self.listener_obj.control_req_callback(message)
        mock_send_response.assert_called_with(message, json.dumps({"return_value": 42}))

    @patch('cryton.lib.models.event.process_event')
    def test_event_callback(self, mock_process_event: Mock):
        message = Mock()
        message.body = json.dumps({
            'event_t': 'TYPE',
            'event_v': 'VALUE'
        })

        self.listener_obj.event_callback(message)

        mock_process_event.assert_called_with(event.Event('TYPE', 'VALUE'))

    @patch('cryton.lib.models.stage.StageExecution.trigger', Mock())
    def test_handle_finished(self):
        worker_obj = baker.make(worker.WorkerModel)
        plan_model_obj = plan.Plan()
        run_obj = run.Run(plan_model_id=plan_model_obj.model.id,
                          workers_list=[worker_obj])
        plan_ex_obj = plan.PlanExecution(plan_execution_id=run_obj.model.plan_executions.all()[0].id)
        plan_ex_obj.state = states.RUNNING
        run_obj.state = states.RUNNING
        stage_ex_obj = stage.StageExecution(plan_execution=plan_ex_obj.model,
                                            stage_model=baker.make(stage.StageModel))
        stage_ex_obj.state = states.SCHEDULED
        stage_ex_obj.state = states.RUNNING

        step_ex_obj = step.StepExecution(stage_execution=stage_ex_obj.model,
                                         step_model=baker.make(step.StepModel))
        step_ex_obj.state = states.RUNNING
        step_ex_obj.state = states.FINISHED
        with self.assertLogs('cryton-debug', level='INFO') as cm:
            self.listener_obj.handle_finished(step_ex_obj)

        self.assertEqual(len(cm.output), 3)
        self.assertIn("stagexecution finished", cm.output[0])
        self.assertIn("planexecution finished", cm.output[1])
        self.assertIn("run finished", cm.output[2])

        self.assertEqual(stage_ex_obj.state, states.FINISHED)
        self.assertEqual(plan_ex_obj.state, states.FINISHED)
        self.assertEqual(run_obj.state, states.FINISHED)
