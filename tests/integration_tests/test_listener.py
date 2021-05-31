from django.test import TestCase
from model_bakery import baker

from unittest.mock import patch, Mock
import json
import yaml
import os

from cryton.lib.services import listener
from cryton.lib.util import creator, logger, states
from cryton.lib.models import stage, plan, step, run

from cryton.cryton_rest_api.models import (
    WorkerModel,
    PlanModel,
    RunModel,
    CorrelationEvent
)

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
@patch('cryton.lib.services.listener.Process', Mock())
@patch('cryton.lib.services.listener.Event', Mock())
@patch('cryton.lib.services.listener.SchedulerService', Mock())
@patch('amqpstorm.Connection', Mock())
@patch('amqpstorm.Message', Mock())
class TestListener(TestCase):

    def setUp(self):
        self.stage_execution = baker.make(stage.StageExecutionModel)
        self.step_model = baker.make(step.StepModel)
        self.step_execution_obj = step.StepExecutionModel.objects.create(step_model=self.step_model,
                                                                         stage_execution=self.stage_execution)

        self.properties = dict()
        self.properties["correlation_id"] = CorrelationEvent.objects.create(correlation_id='test_corr_id',
                                                                            step_execution_id=
                                                                            self.step_execution_obj.id). \
            correlation_id
        #TODO PROBLEM!
        self.listener_obj = listener.Listener()

    def tearDown(self) -> None:
        self.listener_obj.stop()

    def test_event_callback_pause(self):
        plan_obj = baker.make(PlanModel)
        worker_obj = baker.make(WorkerModel)
        run_obj = baker.make(RunModel, state=states.PAUSING)

        plan_execution_obj = plan.PlanExecution(plan_model=plan_obj, worker=worker_obj, run=run_obj,
                                                state=states.PAUSING)

        body = dict(event_t='PAUSE', event_v=dict(result='OK', plan_execution_id=plan_execution_obj.model.id))
        message = Mock()
        message.body = json.dumps(body)
        self.listener_obj.event_callback(message)

    def test_event_callback_nonexistent(self):
        body = dict(event_t='Nonexistent_event', event_v=dict(result='wut'))
        message = Mock()
        message.body = json.dumps(body)
        with self.assertLogs('cryton-test', level='WARN') as cm:
            self.listener_obj.event_callback(message)

        for log in cm.output:
            if "Nonexistent event received" in log:
                break
        else:
            raise AssertionError("String not found in any log message")

    # def test_control_callback(self):
    #     body = dict(control_t='VALIDATE_MODULES', control_v=dict(result='OK'))
    #     message = Mock()
    #     message.body = json.dumps(body)
    #     message.properties = self.properties
    #     message.correlation_id = self.properties.get('correlation_id')
    #     self.listener_obj.control_resp_callback(message)
    #
    # def test_control_callback_nonexistent(self):
    #     body = dict(control_t='Nonexistent_control_event', control_v=dict(result='wut'))
    #     message = Mock()
    #     message.body = json.dumps(body)
    #     message.properties = self.properties
    #     message.correlation_id = self.properties.get('correlation_id')
    #     with self.assertLogs('cryton-test', level='WARN') as cm:
    #         self.listener_obj.control_resp_callback(message)
    #
    #     self.assertIn("Nonexistent control event received", cm.output[0])

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
            correlation_id='unique_test_corr_id_1', step_execution_id=step_exec_obj_1.model.id).correlation_id

        step_exec_obj_1.state = states.RUNNING
        step_exec_obj_2.state = states.PENDING
        stage_exec_obj.state = states.SCHEDULED
        stage_exec_obj.state = states.RUNNING
        plan_exec_obj.state = states.RUNNING
        run_obj.state = states.RUNNING

        body = dict(std_out='test', std_err='test', mod_out='test', mod_err='test')
        message = Mock()
        message.body = json.dumps(body)
        message.properties = properties
        message.correlation_id = properties.get('correlation_id')

        with self.assertLogs('cryton-test', level='INFO') as cm:
            self.listener_obj.step_resp_callback(message)

        self.assertIn("stepexecution finished", cm.output[0])

        self.assertEqual(step_exec_obj_1.state, states.FINISHED)
        self.assertEqual(step_exec_obj_2.state, states.IGNORE)
        self.assertEqual(stage_exec_obj.state, states.FINISHED)
        self.assertEqual(plan_exec_obj.state, states.FINISHED)

        self.assertEqual(run_obj.all_plans_finished, True)
        self.assertEqual(run_obj.state, states.FINISHED)

    @patch('cryton.lib.util.util.Rpc.__enter__')
    def test_worker_healthcheck(self, mock_rpc):
        worker_tmp = creator.create_worker('test', 'address', state=states.DOWN)

        mock_call = Mock()
        mock_call.call = Mock(return_value={'event_v': {'return_code': 0}})
        mock_rpc.return_value = mock_call
        worker_tmp.healthcheck()

        self.assertEqual(worker_tmp.state, states.UP)

    def test_get_correlation_id(self):
        resp = self.listener_obj.get_correlation_event('nonexistent')
        self.assertIsNone(resp)

        correlation_obj = CorrelationEvent.objects.create(correlation_id='unique_test_corr_id_1',
                                                          step_execution_id=
                                                          self.step_execution_obj.id)

        resp = self.listener_obj.get_correlation_event(correlation_obj.correlation_id)
        self.assertEqual(resp, correlation_obj)
