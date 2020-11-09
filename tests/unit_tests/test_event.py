from cryton.lib import (
    event,
    creator,
    logger,
    states,
    plan,
    run,
    worker,
    stage,
    step
)

from cryton.cryton_rest_api.models import (
    CorrelationEvent
)

from django.test import TestCase

from unittest.mock import patch, MagicMock
from model_bakery import baker


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestProcess(TestCase):

    def setUp(self) -> None:
        self.worker_obj = creator.create_worker(name='test', address='test')

    @patch('cryton.lib.event.process_validate_module')
    def test_process_control_event(self, mock_validate):
        corr_obj = CorrelationEvent(correlation_id=1, event_identification_value=self.worker_obj.model.id)
        self.assertEqual(self.worker_obj.state, states.DOWN)
        event.process_control_event(control_event_t='HEALTHCHECK', control_event_v={'return_code': 0},
                                    correlation_event_obj=corr_obj)
        self.assertEqual(self.worker_obj.state, states.UP)

        event.process_control_event(control_event_t='VALIDATE_MODULE', control_event_v={'return_code': 0},
                                    correlation_event_obj=corr_obj)
        self.assertEqual(1, mock_validate.call_count)

        with self.assertLogs('cryton-debug', level='WARN'):
            event.process_control_event(control_event_t='NONEXISTENT', control_event_v={'return_code': 0},
                                        correlation_event_obj=corr_obj)

    def test_process_healthcheck(self):

        self.assertEqual(self.worker_obj.state, states.DOWN)

        event.process_healthcheck(event_v={'return_code': 0}, worker_model_id=self.worker_obj.model.id)

        self.assertEqual(self.worker_obj.state, states.UP)

        event.process_healthcheck(event_v={'return_code': -1}, worker_model_id=self.worker_obj.model.id)

        self.assertEqual(self.worker_obj.state, states.DOWN)

    @patch('cryton.lib.event.process_pause', MagicMock())
    def test_proces_event(self):
        self.assertIsNone(event.process_event('PAUSE', event_v=dict(t='test')))

        with self.assertLogs('cryton-debug', level='WARN'):
            event.process_event('NONEXISTENT', dict())

    def test_process_pause(self):

        plan_model_obj = baker.make(plan.PlanModel)
        run_model_obj = baker.make(run.RunModel, state=states.PAUSING)
        worker_obj = baker.make(worker.WorkerModel)
        plan_ex = plan.PlanExecution(plan_model_id=plan_model_obj.id, run_id=run_model_obj.id, worker_id=worker_obj.id)
        plan_ex.state = states.RUNNING
        plan_ex.state = states.PAUSING
        self.assertIsNone(event.process_pause(dict(result='OK', plan_execution_id=plan_ex.model.id)))
        self.assertEqual(plan_ex.state, states.PAUSED)

    def test_process_validate_modules(self):
        stage_ex_obj = baker.make(stage.StageExecutionModel)
        step_model = baker.make(step.StepModel)
        step_ex_obj = step.StepExecution(stage_execution_id=stage_ex_obj.id, step_model_id=step_model.id)

        self.assertIsNone(event.process_validate_module({'return_code': 0}, step_ex_obj.model.id))
        self.assertTrue(step_ex_obj.valid)

        self.assertIsNone(event.process_validate_module({'return_code': -1}, step_ex_obj.model.id))
        self.assertFalse(step_ex_obj.valid)
