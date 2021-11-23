from cryton.lib.util import logger, states, constants
from cryton.lib.models import stage, plan, step, worker, run, event

from django.test import TestCase

from unittest.mock import patch, MagicMock, Mock
from model_bakery import baker


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch('amqpstorm.Connection', Mock())
class TestProcess(TestCase):

    def setUp(self) -> None:
        self.worker_obj = worker.Worker(name='test', address='test', q_prefix="test")

    # @patch('cryton.lib.models.event.process_list_sessions')
    # @patch('cryton.lib.models.event.process_list_modules')
    # @patch('cryton.lib.models.event.process_kill_execution')
    # @patch('cryton.lib.models.event.process_validate_module')
    # def test_process_control_event(self, mock_validate, mock_kill, mock_list_mod, mock_list_sess):
    #     corr_obj = CorrelationEvent(correlation_id=1, event_identification_value=self.worker_obj.model.id)
    #     self.assertEqual(self.worker_obj.state, states.DOWN)
    #     event.process_control_event(control_event_t='HEALTHCHECK', control_event_v={'return_code': 0},
    #                                 correlation_event_obj=corr_obj)
    #     self.assertEqual(self.worker_obj.state, states.UP)
    #
    #     event.process_control_event(control_event_t='VALIDATE_MODULE', control_event_v={'return_code': 0},
    #                                 correlation_event_obj=corr_obj)
    #     self.assertEqual(1, mock_validate.call_count)
    #
    #     event.process_control_event('LIST_SESSIONS', {}, corr_obj)
    #     mock_list_sess.assert_called_once()
    #
    #     event.process_control_event('LIST_MODULES', {}, corr_obj)
    #     mock_list_mod.assert_called_once()
    #
    #     event.process_control_event('KILL_EXECUTION', {}, corr_obj)
    #     mock_kill.assert_called_once()
    #
    #     with self.assertLogs('cryton-debug', level='WARN'):
    #         event.process_control_event(control_event_t='NONEXISTENT', control_event_v={'return_code': 0},
    #                                     correlation_event_obj=corr_obj)

    def test_process_healthcheck(self):
        self.assertEqual(self.worker_obj.state, states.DOWN)

        event.process_healthcheck(event.Event(constants.EVENT_HEALTH_CHECK, event_v={constants.RETURN_CODE: 0}),
                                  worker_model_id=self.worker_obj.model.id)

        self.assertEqual(self.worker_obj.state, states.UP)

        event.process_healthcheck(event.Event(constants.EVENT_HEALTH_CHECK, event_v={constants.RETURN_CODE: -1}),
                                  worker_model_id=self.worker_obj.model.id)

        self.assertEqual(self.worker_obj.state, states.DOWN)

    @patch('cryton.lib.models.event.process_pause', MagicMock())
    def test_proces_event(self):
        self.assertIsNone(event.process_event(event.Event(constants.PAUSE, event_v=dict(t='test'))))

        with self.assertLogs('cryton-debug', level='WARN'):
            event.process_event(event.Event('NONEXISTENT', dict()))

    def test_process_pause(self):
        plan_model_obj = baker.make(plan.PlanModel)
        run_model_obj = baker.make(run.RunModel, state=states.PAUSING)
        worker_obj = baker.make(worker.WorkerModel)
        plan_ex = plan.PlanExecution(plan_model_id=plan_model_obj.id, run_id=run_model_obj.id, worker_id=worker_obj.id)
        plan_ex.state = states.RUNNING
        plan_ex.state = states.PAUSING
        self.assertEqual(event.process_pause(
            event.Event(constants.PAUSE, dict(result=constants.RESULT_OK, plan_execution_id=plan_ex.model.id))), 0)
        self.assertEqual(plan_ex.state, states.PAUSED)

    def test_process_validate_modules(self):
        stage_ex_obj = baker.make(stage.StageExecutionModel)
        step_model = baker.make(step.StepModel)
        step_ex_obj = step.StepExecution(stage_execution_id=stage_ex_obj.id, step_model_id=step_model.id)

        self.assertTrue(
            event.process_validate_module(event.Event(None, {constants.RETURN_CODE: 0}), step_ex_obj.model.id))
        self.assertTrue(step_ex_obj.valid)

        self.assertFalse(
            event.process_validate_module(event.Event(None, {constants.RETURN_CODE: -1}), step_ex_obj.model.id))
        self.assertFalse(step_ex_obj.valid)

    def test_process_list_sessions(self):
        self.assertEqual(event.process_list_sessions({}, ""), [])

    def test_process_list_modules(self):
        self.assertEqual(event.process_list_modules({}, ""), [])

    def test_process_kill_execution(self):
        self.assertEqual(event.process_kill_execution({}, 1), 0)

    def test_process_scheduler(self):
        event_v = {constants.EVENT_ACTION: constants.SCHEDULER, 'args': {'test': 1}}

        resp = event.process_scheduler(event.Event(None, event_v))
        self.assertEqual(resp, -1)

    def test_process_control_request(self):
        msg = MagicMock()

        msg.body = '{"event_t":"%s", "event_v": {"%s": "test"}}' % (constants.SCHEDULER, constants.EVENT_ACTION)
        resp = event.process_control_request(msg)
        self.assertEqual(resp, -1)
