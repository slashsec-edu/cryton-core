from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock
import os
import datetime
from cryton.lib.util import exceptions, logger, states
from cryton.lib.models import plan, run

from cryton.cryton_rest_api.models import (
    PlanModel,
    StageModel,
    StepModel,
    WorkerModel,
    PlanExecutionModel,
    StageExecutionModel
)

from model_bakery import baker
from django.utils import timezone

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
class RunTest(TestCase):

    def setUp(self) -> None:
        self.plan_model = baker.make(PlanModel)
        self.worker1 = baker.make(WorkerModel, name='worker1')
        self.worker2 = baker.make(WorkerModel, name='worker2')

        self.workers_list = WorkerModel.objects.filter(name__in=['worker1', 'worker2'])

    def test_run_init_nonexistent_plan(self):
        with self.assertRaises(ValueError):
            run.Run(plan_model_id=-1, workers_list=self.workers_list)

    def test_run_init(self):
        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)

        self.assertIsInstance(run_obj.model.id, int)
        self.assertEqual(run_obj.workers, self.workers_list)

    def test_run_report(self):
        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)
        p_exec_1 = plan.PlanExecution(run_id=run_obj.model.id, worker_id=self.worker1.id,
                                      plan_model_id=self.plan_model.id)
        p_exec_2 = plan.PlanExecution(run_id=run_obj.model.id, worker_id=self.worker2.id,
                                      plan_model_id=self.plan_model.id)
        report = run_obj.report()
        self.assertIsInstance(report, dict)
        self.assertEqual(report.get('plan_id'), self.plan_model.id)
        self.assertEqual(report.get('plan_executions')[0].get('worker_id'), p_exec_1.model.worker_id)
        self.assertEqual(report.get('plan_executions')[1].get('worker_id'), p_exec_2.model.worker_id)

    def test_run_list(self):
        run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)

        self.assertEqual(len(run.Run.filter()), 1)
        self.assertEqual(len(run.Run.filter(plan_model_id=self.plan_model.id)), 1)
        self.assertEqual(len(run.Run.filter(plan_model_id=-1)), 0)
        with self.assertRaises(exceptions.WrongParameterError):
            self.assertEqual(len(run.Run.filter(non_existent=False)), 1)


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch('cryton.lib.util.states.RunStateMachine.validate_transition', MagicMock())
class RunTestAdvanced(TestCase):

    def setUp(self) -> None:
        self.plan_model = baker.make(PlanModel)

        self.stage_model_1 = baker.make(StageModel, plan_model_id=self.plan_model.id, trigger_type='delta')
        self.stage_model_2 = baker.make(StageModel, plan_model_id=self.plan_model.id, trigger_type='delta')

        self.step_1 = baker.make(StepModel, stage_model_id=self.stage_model_1.id)
        self.step_2 = baker.make(StepModel, stage_model_id=self.stage_model_2.id)

        self.worker1 = baker.make(WorkerModel, name='worker1')
        self.worker2 = baker.make(WorkerModel, name='worker2')
        self.worker3 = baker.make(WorkerModel, name='worker3')

        self.workers_list = WorkerModel.objects.filter(name__in=['worker1', 'worker2', 'worker3'])

    def test_prepare(self):

        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)

        plan_exec_after = len(PlanExecutionModel.objects.filter(run=run_obj.model))
        stage_exec_after = len(
            StageExecutionModel.objects.filter(plan_execution__run=run_obj.model))
        # Should be 3, one for each worker
        self.assertEqual(plan_exec_after, 3)
        # 3*2, for each worker 2 stages
        self.assertEqual(stage_exec_after, 6)
        self.assertEqual(run_obj.model.plan_executions.all().filter(worker=self.worker1).latest('id'),
                         PlanExecutionModel.objects.filter(worker=self.worker1,
                                                           run=run_obj.model).latest('id'))

    @patch('cryton.lib.util.scheduler_client.schedule_function')
    def test_schedule(self, mock_sched):
        mock_sched.return_value = 0
        schedule_time = timezone.now()
        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            run_obj.schedule(schedule_time)
        self.assertIn("run scheduled", cm.output[-1])
        self.assertEqual(run_obj.schedule_time, schedule_time)

    @patch('cryton.lib.util.scheduler_client.schedule_function', Mock(return_value=1))
    @patch('cryton.lib.util.scheduler_client.remove_job', Mock(return_value=1))
    def test_reschedule(self):
        schedule_time = timezone.now()
        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)
        # Incorrect state
        with self.assertRaises(exceptions.RunInvalidStateError), self.assertLogs('cryton-debug', level='ERROR') as cm:
            run_obj.reschedule(schedule_time)

        self.assertIn("invalid state detected", cm.output[0])

        # Correct state
        run_obj.state = states.SCHEDULED

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            run_obj.reschedule(schedule_time + datetime.timedelta(minutes=10))

        self.assertIn("run unscheduled", cm.output[0])
        self.assertIn("run scheduled", cm.output[1])
        self.assertIn("run rescheduled", cm.output[2])
        self.assertEqual(run_obj.schedule_time, schedule_time + datetime.timedelta(minutes=10))

    @patch('cryton.lib.models.plan.PlanExecution.pause', Mock())
    def test_pause(self):
        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)
        # Correct state
        run_obj.state = states.RUNNING
        run_obj.pause()

    @patch('cryton.lib.models.plan.PlanExecution.unpause', Mock())
    def test_unpause(self):
        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)

        # Correct state
        run_obj.state = states.PAUSED

        with self.assertLogs('cryton-debug', level='INFO'):
            run_obj.unpause()
        self.assertEqual(run_obj.state, states.RUNNING)

    @patch('cryton.lib.util.scheduler_client.schedule_function', Mock(return_value=1))
    @patch('cryton.lib.util.scheduler_client.remove_job', Mock(return_value=1))
    def test_postpone(self):

        dt = datetime.timedelta(hours=1)

        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)
        # Incorrect state
        with self.assertRaises(exceptions.InvalidStateError), self.assertLogs('cryton-debug', level='ERROR') as cm:
            run_obj.postpone(dt)

        self.assertIn("invalid state detected", cm.output[0])

        # Correct state
        run_obj.state = states.SCHEDULED
        run_obj.schedule_time = timezone.now()
        schedule_time_dt = run_obj.schedule_time
        for pex in run_obj.model.plan_executions.all():
            plan.PlanExecution(plan_execution_id=pex.id).state = states.SCHEDULED
        for pex in run_obj.model.plan_executions.all():
            self.assertEqual(pex.state, states.SCHEDULED)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            run_obj.postpone(dt)

        self.assertIn("run unscheduled", cm.output[0])
        self.assertIn("run scheduled", cm.output[1])
        self.assertIn("run postponed", cm.output[2])
        self.assertEqual(run_obj.schedule_time, schedule_time_dt + dt)

    @patch('cryton.lib.models.plan.PlanExecution.kill', Mock())
    def test_kill(self):
        run_obj = run.Run(plan_model_id=self.plan_model.id, workers_list=self.workers_list)
        for plan_ex_model in run_obj.model.plan_executions.all():
            plan.PlanExecution(plan_execution_id=plan_ex_model.id).state = states.RUNNING
        run_obj.state = states.RUNNING
        with self.assertLogs('cryton-debug', level='INFO'):
            run_obj.kill()
        self.assertEqual(run_obj.state, states.TERMINATED)
