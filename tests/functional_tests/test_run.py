from django.test import TestCase
from model_bakery import baker
import datetime
import os
import yaml
from unittest.mock import patch, Mock, MagicMock

from cryton.lib.util import creator, exceptions, logger, states
from cryton.lib.models import step, run, plan, worker

from cryton.cryton_rest_api.models import (
    PlanModel,
    WorkerModel,
    StepExecutionModel
)
from django.utils import timezone


TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
@patch("cryton.lib.models.plan.os.makedirs", Mock())
class TestRun(TestCase):

    def setUp(self) -> None:
        self.plan_obj = baker.make(PlanModel)

        self.worker_1 = baker.make(WorkerModel, **{'name': 'test_worker_name1', 'q_prefix': 'test_queue_1'})
        self.worker_2 = baker.make(WorkerModel, **{'name': 'test_worker_name2', 'q_prefix': 'test_queue_2'})
        self.worker_3 = baker.make(WorkerModel, **{'name': 'test_worker_name3', 'q_prefix': 'test_queue_3'})

        self.workers_list = [self.worker_1, self.worker_2, self.worker_3]
        self.workers_id_list = [self.worker_1.id, self.worker_2.id, self.worker_3.id]
        self.run_obj = run.Run(plan_model_id=self.plan_obj.id, workers_list=self.workers_list)

    @patch('cryton.lib.util.scheduler_client.schedule_function', Mock(return_value=1))
    @patch('cryton.lib.util.scheduler_client.remove_job', Mock(return_value=1))
    @patch("cryton.lib.util.util.rabbit_send_oneway_msg", Mock())
    def test_schedule(self):
        self.assertEqual(self.run_obj.state, states.PENDING)

        with self.assertRaises(exceptions.RunInvalidStateError):
            self.run_obj.reschedule(timezone.now())

        schedule_time_dt = timezone.now()
        self.run_obj.schedule(schedule_time_dt)

        self.assertEqual(self.run_obj.state, states.SCHEDULED)
        self.assertEqual(self.run_obj.schedule_time, schedule_time_dt)

        self.run_obj.reschedule(timezone.now() + datetime.timedelta(minutes=5))
        self.assertEqual(self.run_obj.state, states.SCHEDULED)

        self.run_obj.unschedule()
        self.assertEqual(self.run_obj.state, states.PENDING)
        self.assertIsNone(self.run_obj.schedule_time)

        self.run_obj.state = states.RUNNING
        for pex in self.run_obj.model.plan_executions.all():
            pex.state = states.RUNNING
            pex.save()

        self.run_obj.pause()

        self.assertEqual(self.run_obj.state, states.PAUSED)


    @patch("cryton.lib.util.util.rabbit_send_oneway_msg", Mock())
    @patch('cryton.lib.util.scheduler_client.schedule_function')
    @patch('cryton.lib.util.scheduler_client.remove_job')
    def test_execute(self, moc_remove, mock_sched):
        mock_sched.return_value = 0
        moc_remove.return_value = 0
        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=self.workers_list)

        run_obj.execute()

        self.assertEqual(run_obj.state, states.RUNNING)
        for exec_obj in run_obj.model.plan_executions.filter(worker_id__in=self.workers_id_list):
            self.assertEqual(exec_obj.state, states.RUNNING)

        run_obj.pause()
        for exec_obj in run_obj.model.plan_executions.filter(worker_id__in=self.workers_id_list):
            self.assertEqual(exec_obj.state, states.PAUSED)

        # this is a replacement for __change_conditional_state cause threading and django don't work well in tests
        for exec_obj in run_obj.model.plan_executions.all():
            plan.PlanExecution(plan_execution_id=exec_obj.id).state = states.PAUSED

        run_obj.unpause()
        for exec_obj in run_obj.model.plan_executions.filter(worker_id__in=self.workers_id_list):
            self.assertEqual(exec_obj.state, states.RUNNING)

    @patch('cryton.lib.util.scheduler_client.schedule_function')
    def test_plan_run(self, mock_sched):
        mock_sched.return_value = 0
        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=self.workers_list)

        run_obj.schedule(timezone.now())

        self.assertEqual(run_obj.state, states.SCHEDULED)

    def test_with_rabbit(self):
        with open(TESTS_DIR + '/complicated-test-plan.yml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        worker_obj = creator.create_worker('test', '1.2.3.4')

        run_obj = creator.create_run(plan_obj.model.id, [worker_obj.model])


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
@patch("cryton.lib.models.plan.os.makedirs", Mock())
@patch("cryton.lib.util.util.rabbit_send_oneway_msg", Mock())
class TestVariables(TestCase):

    def setUp(self) -> None:
        self.worker_1 = baker.make(WorkerModel, **{'name': 'test_worker_name1', 'q_prefix': 'test_queue_1'})

        self.workers_list = [self.worker_1]
        pass

    @patch('cryton.lib.util.scheduler_client.schedule_function')
    @patch('cryton.lib.util.scheduler_client.remove_job')
    @patch('cryton.lib.models.step.StepExecution._execute_step')
    def test_use_var(self, moc_exec, moc_remove, mock_sched):
        mock_sched.return_value = 0
        moc_remove.return_value = 0
        with open(TESTS_DIR + '/plan-vars.yml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=self.workers_list)

        # Get StepExecutions
        step_ex_obj = step.StepExecution(step_execution_id=StepExecutionModel.objects.get(
            stage_execution__plan_execution__run=run_obj.model,
            step_model__name='step1').id)

        output = {'std_out': 0, 'std_err': 0, 'mod_out': {'cmd_output': 'testing'}}
        step_ex_obj.save_output(output)

        step_ex_obj_2 = StepExecutionModel.objects.get(stage_execution__plan_execution__run=run_obj.model,
                                                       step_model__name='step2')

        rabbit_channel = MagicMock()
        step_ex = step.StepExecution(step_execution_id=step_ex_obj_2.id)
        step_ex.execute(rabbit_channel=rabbit_channel)

        step_arguments = {'attack_module': 'mod_cmd', 'attack_module_args': {'cmd': 'testing'}}

        moc_exec.assert_called_with(rabbit_channel, step_ex_obj_2.step_model.step_type, step_arguments,
                                    step_ex.model.stage_execution.plan_execution.worker,
                                    step_ex_obj_2.step_model.executor)


    @patch('cryton.lib.util.scheduler_client.schedule_function')
    @patch('cryton.lib.util.scheduler_client.remove_job')
    @patch('cryton.lib.models.step.StepExecution._execute_step')
    def test_use_var_prefix(self, moc_exec, moc_remove, mock_sched):
        mock_sched.return_value = 0
        moc_remove.return_value = 0
        with open(TESTS_DIR + '/plan-vars-prefix.yml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=self.workers_list)

        # Get StepExecutions
        step_ex_obj = step.StepExecution(step_execution_id=StepExecutionModel.objects.get(
            stage_execution__plan_execution__run=run_obj.model,
            step_model__name='step1').id)

        output = {'std_out': 0, 'std_err': 0, 'mod_out': {'cmd_output': 'testing'}}
        step_ex_obj.save_output(output)

        step_ex_obj_2 = StepExecutionModel.objects.get(stage_execution__plan_execution__run=run_obj.model,
                                                       step_model__name='step2')

        rabbit_channel = MagicMock()
        step_ex = step.StepExecution(step_execution_id=step_ex_obj_2.id)
        step_ex.execute(rabbit_channel=rabbit_channel)

        step_arguments = {'attack_module': 'mod_cmd', 'attack_module_args': {'cmd': 'testing'}}

        moc_exec.assert_called_with(rabbit_channel, step_ex_obj_2.step_model.step_type, step_arguments,
                                    step_ex.model.stage_execution.plan_execution.worker,
                                    step_ex_obj_2.step_model.executor)


    @patch('cryton.lib.util.scheduler_client.schedule_function')
    @patch('cryton.lib.util.scheduler_client.remove_job')
    @patch('cryton.lib.models.step.StepExecution._execute_step')
    def test_use_var_mapping(self, moc_exec, moc_remove, mock_sched):
        mock_sched.return_value = 0
        moc_remove.return_value = 0
        with open(TESTS_DIR + '/plan-vars-mapping.yml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=self.workers_list)

        # Get StepExecutions
        step_ex_obj = step.StepExecution(step_execution_id=StepExecutionModel.objects.get(
            stage_execution__plan_execution__run=run_obj.model,
            step_model__name='step1').id)

        output = {'std_out': 0, 'std_err': 0, 'mod_out': {'cmd_output': 'testing'}}
        step_ex_obj.save_output(output)

        step_ex_obj_2 = StepExecutionModel.objects.get(stage_execution__plan_execution__run=run_obj.model,
                                                       step_model__name='step2')

        rabbit_channel = MagicMock()
        step_ex = step.StepExecution(step_execution_id=step_ex_obj_2.id)
        step_ex.execute(rabbit_channel=rabbit_channel)

        step_arguments = {'attack_module': 'mod_cmd', 'attack_module_args': {'cmd': 'testing'}}

        moc_exec.assert_called_with(rabbit_channel, step_ex_obj_2.step_model.step_type, step_arguments,
                                    step_ex.model.stage_execution.plan_execution.worker,
                                    step_ex_obj_2.step_model.executor)

    @patch('cryton.lib.util.scheduler_client.schedule_function')
    @patch('cryton.lib.util.scheduler_client.remove_job')
    @patch('cryton.lib.models.step.StepExecution._execute_step')
    def test_use_var_parent(self, moc_exec, moc_remove, mock_sched):
        mock_sched.return_value = 0
        moc_remove.return_value = 0
        with open(TESTS_DIR + '/plan-vars-parent.yml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=self.workers_list)

        # Get StepExecutions
        step_ex_obj = step.StepExecution(step_execution_id=StepExecutionModel.objects.get(
            stage_execution__plan_execution__run=run_obj.model,
            step_model__name='step1').id)

        output = {'std_out': 0, 'std_err': 0, 'mod_out': {'cmd_output': 'testing'}}
        step_ex_obj.save_output(output)

        step_ex_obj_2 = StepExecutionModel.objects.get(stage_execution__plan_execution__run=run_obj.model,
                                                       step_model__name='step2')

        rabbit_channel = MagicMock()
        succ_step_ex_obj = step.StepExecution(step_execution_id=step_ex_obj_2.id)
        succ_step_ex_obj.parent_id = step_ex_obj.model.id
        succ_step_ex_obj.execute(rabbit_channel=rabbit_channel)

        step_arguments = {'attack_module': 'mod_cmd', 'attack_module_args': {'cmd': 'testing'}}
        moc_exec.assert_called_with(rabbit_channel, step_ex_obj_2.step_model.step_type, step_arguments,
                                    step_ex_obj_2.stage_execution.plan_execution.worker,
                                    step_ex_obj_2.step_model.executor)
