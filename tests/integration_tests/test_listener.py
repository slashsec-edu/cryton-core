from django.test import TestCase
from model_bakery import baker

from unittest.mock import patch, Mock, MagicMock
import json
import yaml
import os

from cryton.lib import (
    listener,
    plan,
    states,
    stage,
    step,
    logger,
    run,
    creator
)

from cryton.cryton_rest_api.models import (
    WorkerModel,
    PlanModel,
    RunModel,
    CorrelationEvent
)

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-test'))
class TestListener(TestCase):

    def setUp(self):
        self.step_execution_obj = baker.make(step.StepExecutionModel)

        self.properties = dict()
        self.properties["correlation_id"] = CorrelationEvent.objects.create(correlation_id='test_corr_id',
                                                                            event_identification_value=
                                                                            self.step_execution_obj.id). \
            correlation_id

    def test_event_callback_pause(self):
        plan_obj = baker.make(PlanModel)
        worker_obj = baker.make(WorkerModel)
        run_obj = baker.make(RunModel, state=states.PAUSING)

        plan_execution_obj = plan.PlanExecution(plan_model=plan_obj, worker=worker_obj, run=run_obj,
                                                state=states.PAUSING)

        body = dict(event_t='PAUSE', event_v=dict(result='OK', plan_execution_id=plan_execution_obj.model.id))
        message = Mock()
        message.body = json.dumps(body)
        listener.event_callback(message)

    def test_event_callback_nonexistent(self):
        body = dict(event_t='Nonexistent_event', event_v=dict(result='wut'))
        message = Mock()
        message.body = json.dumps(body)
        with self.assertLogs('cryton-test', level='WARN') as cm:
            listener.event_callback(message)

        self.assertIn("Nonexistent event received", cm.output[0])

    def test_control_callback(self):
        body = dict(control_t='VALIDATE_MODULES', control_v=dict(result='OK'))
        message = Mock()
        message.body = json.dumps(body)
        message.properties = self.properties
        message.correlation_id = self.properties.get('correlation_id')
        listener.control_resp_callback(message)

    def test_control_callback_nonexistent(self):
        body = dict(control_t='Nonexistent_control_event', control_v=dict(result='wut'))
        message = Mock()
        message.body = json.dumps(body)
        message.properties = self.properties
        message.correlation_id = self.properties.get('correlation_id')
        with self.assertLogs('cryton-test', level='WARN') as cm:
            listener.control_resp_callback(message)

        self.assertIn("Nonexistent control event received", cm.output[0])

    def test_step_resp_callback(self):
        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        worker_obj = baker.make(WorkerModel)
        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=[worker_obj])

        plan_exec_obj = plan.PlanExecution(plan_execution_id=
                                           plan.PlanExecutionModel.objects.get(run_id=run_obj.model.id).id)
        stage_exec_obj = stage.StageExecution(stage_execution_id=plan_exec_obj.model.stage_executions.all()[0].id)
        step_exec_obj_1 = step.StepExecution(step_execution_id=stage_exec_obj.model.step_executions.all()[0].id)
        step_exec_obj_2 = step.StepExecution(step_execution_id=stage_exec_obj.model.step_executions.all()[1].id)

        properties = dict()
        properties["correlation_id"] = CorrelationEvent.objects.create(
            correlation_id='unique_test_corr_id_1', event_identification_value=step_exec_obj_1.model.id).correlation_id

        step_exec_obj_1.state = states.RUNNING
        step_exec_obj_2.state = states.PENDING
        stage_exec_obj.state = states.RUNNING
        plan_exec_obj.state = states.RUNNING
        run_obj.state = states.RUNNING

        body = dict(std_out='test', std_err='test', mod_out='test', mod_err='test')
        message = Mock()
        message.body = json.dumps(body)
        message.properties = properties
        message.correlation_id = properties.get('correlation_id')

        with self.assertLogs('cryton-test', level='INFO') as cm:
            listener.step_resp_callback(message)

        self.assertIn("stepexecution finished", cm.output[0])

        self.assertEqual(step_exec_obj_1.state, states.FINISHED)
        self.assertEqual(step_exec_obj_2.state, states.IGNORE)
        self.assertEqual(stage_exec_obj.state, states.FINISHED)
        self.assertEqual(plan_exec_obj.state, states.FINISHED)

        self.assertEqual(run_obj.all_plans_finished, True)
        self.assertEqual(run_obj.state, states.FINISHED)

    def test_worker_healthcheck(self):
        worker_tmp = creator.create_worker('test', 'address', state=states.DOWN)
        properties = dict()
        properties["correlation_id"] = CorrelationEvent.objects.create(correlation_id='unique_test_corr_id_1',
                                                                       event_identification_value=
                                                                       worker_tmp.model.id).correlation_id
        body = dict(event_t='HEALTHCHECK', event_v={'return_code': 0})
        message = Mock()
        message.body = json.dumps(body)
        message.properties = properties
        message.correlation_id = properties.get('correlation_id')
        listener.control_resp_callback(message)

        self.assertEqual(worker_tmp.state, states.UP)

    def test_get_correlation_id(self):
        resp = listener.get_correlation_event('nonexistent')
        self.assertIsNone(resp)

        worker_obj = baker.make(WorkerModel)
        correlation_obj = CorrelationEvent.objects.create(correlation_id='unique_test_corr_id_1',
                                                          event_identification_value=
                                                          worker_obj.id)

        resp = listener.get_correlation_event(correlation_obj.correlation_id)
        self.assertEqual(resp, correlation_obj)

    @patch('cryton.lib.listener.Listener')
    def test_start(self, mock_listener):
        listener.start()
        mock_listener.assert_called()


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-test'))
class TestRabbitListener(TestCase):
    @patch('amqpstorm.Connection')
    def test_rabbit_listener(self, mock_connection):
        test_callback = Mock()
        mock_connection.is_open.return_value = True

        listener_obj = listener.Listener()
        listener_obj.start({'test_que': test_callback})
        listener_obj.stop()

    @patch('cryton.lib.util.rabbit_connection')
    def test_process_listener(self, mock_connection):
        test_callback = Mock()
        listener_obj = listener.ProcessListener('test_que', test_callback)
        listener_obj._stopped.is_set = Mock(side_effect=[False, False, True])
        channel = Mock()
        mock_connection.channel.return_value = channel
        channel.start_consuming.side_effect = listener_obj._execute_custom_callback(Mock())

        listener_obj.start()
        listener_obj.stop()
