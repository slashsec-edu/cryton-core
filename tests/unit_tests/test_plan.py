import os
import yaml
from datetime import datetime

from django.test import TestCase
from mock import patch, Mock, MagicMock
from model_bakery import baker

from cryton.lib import exceptions, plan, logger, stage

from cryton.cryton_rest_api.models import (
    PlanModel,
    StageModel,
    StepModel,
    StepExecutionModel,
    StageExecutionModel,
    PlanExecutionModel,
    WorkerModel,
    RunModel
)

from cryton.lib.triggers import (
    trigger_http_listener
)

@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-debug'))
class PlanTest(TestCase):
    def setUp(self):
        self.plan_obj = plan.Plan(plan_model_id=baker.make(PlanModel).id)

    def test_constructor_existing(self):
        plan_model = baker.make(PlanModel)

        plan_obj = plan.Plan(plan_model_id=plan_model.id)

        self.assertEqual(plan_obj.model, plan_model)

    def test_constructor_existing_invalid(self):
        with self.assertRaises(exceptions.PlanObjectDoesNotExist):
            plan.Plan(plan_model_id=42)

    @patch("cryton.lib.plan.config.EVIDENCE_DIR", "/tmp")
    @patch("cryton.lib.plan.os.makedirs")
    def test_constructor_create(self, mock_makedirs):
        plan_obj = plan.Plan(owner="tester", name="test name")

        self.assertEqual(plan_obj.owner, "tester")
        self.assertEqual(plan_obj.evidence_dir, "/tmp/plan_{:0>3}-test_name".format(plan_obj.model.id))
        self.assertEqual(plan_obj.plan_dict, {"name": "test name", "owner": "tester"})

        mock_makedirs.assert_called_once_with(plan_obj.evidence_dir, exist_ok=True)

    @patch("cryton.lib.plan.config.EVIDENCE_DIR", "/tmp")
    @patch("cryton.lib.plan.os.makedirs")
    def test_create_evidence_dir(self, mock_makedirs):
        plan_model = baker.make(PlanModel, name="test name")
        plan_obj = plan.Plan(plan_model_id=plan_model.id)

        plan_obj._Plan__create_evidence_dir()

        self.assertEqual(plan_obj.evidence_dir, "/tmp/plan_{:0>3}-test_name".format(plan_obj.model.id))

        mock_makedirs.assert_called_once_with(plan_obj.evidence_dir, exist_ok=True)

    def test_filter_all(self):
        plan_model1 = baker.make(PlanModel)
        plan_model2 = baker.make(PlanModel)

        ret = plan.Plan.filter()

        self.assertTrue(plan_model1 in ret)
        self.assertTrue(plan_model2 in ret)

    def test_filter_field(self):
        plan_model1 = baker.make(PlanModel, name="name 1")
        plan_model2 = baker.make(PlanModel, name="name 2")

        ret = plan.Plan.filter(name="name 1")

        self.assertTrue(plan_model1 in ret)
        self.assertTrue(plan_model2 not in ret)

    def test_filter_invalid_field(self):
        with self.assertRaises(exceptions.WrongParameterError):
            plan.Plan.filter(invalid="test")

    def test_name_property(self):
        self.plan_obj.name = "testname"
        self.assertEqual(self.plan_obj.name, "testname")

    def test_owner_property(self):
        self.plan_obj.owner = "testowner"
        self.assertEqual(self.plan_obj.owner, "testowner")

    def test_evidence_dir_property(self):
        self.plan_obj.evidence_dir = "testdir"
        self.assertEqual(self.plan_obj.evidence_dir, "testdir")

    def test_plan_dict_property(self):
        self.plan_obj.plan_dict = {"test": "dict"}
        self.assertEqual(self.plan_obj.plan_dict, {"test": "dict"})

    def test_delete(self):
        plan_model_id = self.plan_obj.model.id

        self.assertIsInstance(plan_model_id, int)

        self.plan_obj.delete()

        with self.assertRaises(exceptions.PlanObjectDoesNotExist):
            plan.Plan(plan_model_id=plan_model_id)

    @patch("cryton.lib.stage.Stage.validate")
    def test_validate_all_valid(self, mock_stage_validate):
        args = {"name": "test", "owner": "tester", "stages": [{"stage1": "..."}]}

        plan.Plan.validate(args)

        mock_stage_validate.assert_called_once()

    def test_validate_missing(self):
        args = {"owner": "tester", "stages": [{"stage1": "..."}]}

        with self.assertRaises(exceptions.PlanValidationError):
            plan.Plan.validate(args)

        args = {"name": "test", "owner": "tester"}

        with self.assertRaises(exceptions.PlanValidationError):
            plan.Plan.validate(args)

    def test_validate_invalid_type(self):
        args = {"name": "test", "owner": "tester", "stages": {}}

        with self.assertRaises(exceptions.PlanValidationError):
            plan.Plan.validate(args)

        args = {"name": "test", "owner": 42, "stages": [{"stage1": "..."}]}

        with self.assertRaises(exceptions.PlanValidationError):
            plan.Plan.validate(args)

    def test_validate_empty_stages(self):
        args = {"name": "test", "owner": "tester", "stages": []}

        with self.assertRaises(exceptions.PlanValidationError):
            plan.Plan.validate(args)


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch('cryton.lib.states.PlanStateMachine.validate_transition', MagicMock())
class PlanExecutionTest(TestCase):
    def setUp(self):
        self.pex_obj = plan.PlanExecution(plan_execution_id=baker.make(PlanExecutionModel).id)

    def test_constructor_existing(self):
        plan_execution_model = baker.make(PlanExecutionModel)

        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        self.assertEqual(plan_execution.model, plan_execution_model)

    def test_constructor_existing_invalid(self):
        with self.assertRaises(exceptions.PlanExecutionDoesNotExist):
            plan.PlanExecution(plan_execution_id=42)

    def test_constructor_create(self):
        run_model = baker.make(RunModel)
        worker_model = baker.make(WorkerModel)
        plan_instance_model = baker.make(PlanModel)

        plan_execution = plan.PlanExecution(run=run_model, worker=worker_model, plan_model_id=plan_instance_model.id)

        self.assertEqual(plan_execution.model.run, run_model)
        self.assertEqual(plan_execution.model.worker, worker_model)

    def test_state_property(self):
        self.pex_obj.state = "RUNNING"
        self.assertEqual(self.pex_obj.state, "RUNNING")

    def test_start_time_property(self):
        time = datetime(3000, 12, 12, 10, 10, 10)

        self.pex_obj.start_time = time
        self.assertEqual(self.pex_obj.start_time, time)

    def test_pause_time_property(self):
        time = datetime(3000, 12, 12, 10, 10, 10)

        self.pex_obj.pause_time = time
        self.assertEqual(self.pex_obj.pause_time, time)

    def test_finish_time_property(self):
        time = datetime(3000, 12, 12, 10, 10, 10)

        self.pex_obj.finish_time = time
        self.assertEqual(self.pex_obj.finish_time, time)

    def test_aps_job_id_property(self):
        self.pex_obj.aps_job_id = "42"
        self.assertEqual(self.pex_obj.aps_job_id, "42")

    def test_evidence_dir_property(self):
        self.pex_obj.evidence_dir = "testdir"
        self.assertEqual(self.pex_obj.evidence_dir, "testdir")

    def test_delete(self):
        pex_model_id = self.pex_obj.model.id

        self.assertIsInstance(pex_model_id, int)

        self.pex_obj.delete()

        with self.assertRaises(exceptions.PlanExecutionDoesNotExist):
            plan.PlanExecution(plan_execution_id=pex_model_id)

    @patch("cryton.lib.scheduler_client.schedule_function", Mock(return_value=1))
    def test_schedule(self):
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="delta"),
                                           state="PENDING")
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.schedule(datetime(3000, 12, 12, 10, 0, 0))

        self.assertEqual(plan_execution.state, "SCHEDULED")
        self.assertEqual(plan_execution.start_time, datetime(3000, 12, 12, 10, 0, 0))
        self.assertIn("planexecution scheduled", cm.output[0])

    @patch("cryton.lib.plan.PlanExecution.start_triggers")
    @patch('cryton.lib.plan.PlanExecution._PlanExecution__generate_evidence_dir', Mock())
    @patch('cryton.lib.util.rabbit_prepare_queue', MagicMock())
    def test_execute_delta_stage_pending(self, mock_start_triggers):
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="delta"),
                                           state="PENDING")
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.execute()

        mock_start_triggers.assert_called_once()
        self.assertEqual(plan_execution.state, "RUNNING")
        self.assertIn("planexecution executed", cm.output[0])

    @patch("cryton.lib.plan.PlanExecution.start_triggers")
    @patch('cryton.lib.plan.PlanExecution._PlanExecution__generate_evidence_dir', Mock())
    @patch('cryton.lib.util.rabbit_prepare_queue', MagicMock())
    def test_execute_delta_stage_suspended(self, mock_start_triggers):
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="delta"),
                                           state="PAUSED")
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.execute()

        mock_start_triggers.assert_called_once()
        self.assertEqual(plan_execution.state, "RUNNING")
        self.assertIn("planexecution executed", cm.output[0])

    @patch("cryton.lib.plan.PlanExecution.start_triggers")
    @patch('cryton.lib.plan.PlanExecution._PlanExecution__generate_evidence_dir', Mock())
    @patch('cryton.lib.util.rabbit_prepare_queue', MagicMock())
    def test_execute_delta_stage_running(self, mock_start_triggers):
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="delta"),
                                           state="RUNNING")
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.execute()

        mock_start_triggers.assert_called_once()
        self.assertEqual(plan_execution.state, "RUNNING")
        self.assertIn("planexecution executed", cm.output[0])

    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.schedule")
    @patch("cryton.lib.plan.PlanExecution.start_triggers")
    @patch('cryton.lib.plan.PlanExecution._PlanExecution__generate_evidence_dir', Mock())
    @patch('cryton.lib.util.rabbit_prepare_queue', MagicMock())
    def test_execute_trigger_stage(self, mock_start_triggers, mock_schedule_stage):
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="HTTPListener"))
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.execute()

        mock_start_triggers.assert_called_once()
        mock_schedule_stage.assert_not_called()
        self.assertEqual(plan_execution.state, "RUNNING")
        self.assertIn("planexecution executed", cm.output[0])

    @patch("cryton.lib.plan.PlanExecution.start_triggers", Mock())
    @patch('cryton.lib.plan.PlanExecution._PlanExecution__generate_evidence_dir', Mock())
    @patch('cryton.lib.util.rabbit_prepare_queue', MagicMock())
    def test_execute_not_pending(self):
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="HTTPListener"))
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
        plan_execution.state = "RUNNING"

        with self.assertRaises(exceptions.PlanInvalidStateError), self.assertLogs('cryton-debug', level='ERROR') as cm:
            plan_execution.execute()

        self.assertIn("invalid state detected", cm.output[0])

    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.unschedule")
    def test_unschedule(self, mock_unschedule_stage):
        plan_execution_model = baker.make(PlanExecutionModel, state="SCHEDULED",
                                          stage_executions=[baker.make(StageExecutionModel,
                                                                       stage_model=baker.make(StageModel,
                                                                                              trigger_type="delta"))])
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.unschedule()

        self.assertEqual(plan_execution.state, "PENDING")
        mock_unschedule_stage.assert_called_once()
        self.assertIn("planexecution unscheduled", cm.output[0])

    def test_unschedule_invalid_state(self):
        plan_execution_model = baker.make(PlanExecutionModel, state="RUNNING")
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertRaises(exceptions.PlanInvalidStateError), self.assertLogs('cryton-debug', level='ERROR') as cm:
            plan_execution.unschedule()

        self.assertIn("invalid state detected", cm.output[0])

    @patch("cryton.lib.plan.PlanExecution.schedule")
    @patch("cryton.lib.plan.PlanExecution.unschedule")
    def test_postpone_valid(self, mock_unschedule_plan, mock_schedule_plan):
        plan_execution_model = baker.make(PlanExecutionModel, start_time="3000-12-12 10:00:00", state="SCHEDULED")
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.postpone("1h1m1s")

        mock_schedule_plan.assert_called_with(datetime(3000, 12, 12, 11, 1, 1))
        mock_unschedule_plan.assert_called_once()
        self.assertIn("planexecution postponed", cm.output[0])

    def test_postpone_invalid(self):
        plan_execution_model = baker.make(PlanExecutionModel, start_time="3000-12-12 10:00:00", state="SCHEDULED")
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertRaises(exceptions.UserInputError), self.assertLogs('cryton-debug', level='ERROR'):
            plan_execution.postpone("invalidh1m1s")
        with self.assertRaises(exceptions.UserInputError), self.assertLogs('cryton-debug', level='ERROR'):
            plan_execution.postpone("1hms")
        with self.assertRaises(exceptions.UserInputError), self.assertLogs('cryton-debug', level='ERROR'):
            plan_execution.postpone("1h1mAs")
        with self.assertRaises(exceptions.UserInputError), self.assertLogs('cryton-debug', level='ERROR'):
            plan_execution.postpone("")

    def test_postpone_unscheduled(self):
        plan_execution_model = baker.make(PlanExecutionModel, start_time="3000-12-12 10:00:00", state="PENDING")
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertRaises(exceptions.PlanInvalidStateError), self.assertLogs('cryton-debug', level='ERROR'):
            plan_execution.postpone("1h1m1s")

    @patch("cryton.lib.plan.PlanExecution.schedule")
    @patch("cryton.lib.plan.PlanExecution.unschedule")
    def test_reschedule_valid(self, mock_unschedule_plan, mock_schedule_plan):
        plan_execution_model = baker.make(PlanExecutionModel, start_time="3000-12-12 10:00:00", state="SCHEDULED")
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.reschedule(datetime(3000, 12, 12, 11, 1, 1))

        mock_schedule_plan.assert_called_with(datetime(3000, 12, 12, 11, 1, 1))
        mock_unschedule_plan.assert_called_once()
        self.assertIn("planexecution rescheduled", cm.output[0])

    def test_reschedule_datetime_invalid(self):
        plan_execution_model = baker.make(PlanExecutionModel, start_time="3000-12-12 10:00:00", state="SCHEDULED")
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertRaises(exceptions.UserInputError), self.assertLogs('cryton-debug', level='ERROR'):
            plan_execution.reschedule(datetime(1990, 12, 12, 11, 1, 1))

    @patch("cryton.lib.plan.PlanExecution.schedule", Mock())
    @patch("cryton.lib.plan.PlanExecution.unschedule", Mock())
    def test_reschedule_notscheduled(self):
        plan_execution_model = baker.make(PlanExecutionModel, start_time="3000-12-12 10:00:00", state="PENDING")
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertRaises(exceptions.PlanInvalidStateError), self.assertLogs('cryton-debug', level='ERROR'):
            plan_execution.reschedule(datetime(3000, 12, 12, 11, 1, 1))

    @patch("cryton.lib.util.rabbit_send_oneway_msg", Mock())
    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.pause")
    def test_pause_pending_stage(self, mock_stage_pause):
        stage_execution_model = baker.make(StageExecutionModel, state="PENDING",
                                           stage_model=baker.make(StageModel, trigger_type="delta",
                                                                  trigger_args={}))
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
        plan_execution.state = "RUNNING"

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.pause()

        self.assertEqual(plan_execution.state, "PAUSED")
        mock_stage_pause.assert_called_once()
        self.assertIn("planexecution pausing", cm.output[0])

    @patch("cryton.lib.util.rabbit_send_oneway_msg", Mock())
    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.pause")
    def test_pause_suspended_stage(self, mock_stage_pause):
        stage_execution_model = baker.make(StageExecutionModel, state="PAUSED",
                                           stage_model=baker.make(StageModel, trigger_type="delta",
                                                                  trigger_args={})
                                           )
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
        plan_execution.state = "RUNNING"

        with self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_execution.pause()

        self.assertEqual(plan_execution.state, "PAUSED")
        mock_stage_pause.assert_called_once()
        self.assertIn("planexecution pausing", cm.output[0])

    @patch("cryton.lib.util.rabbit_send_oneway_msg", Mock())
    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.unschedule")
    def test_pause_running_stage(self, mock_stage_pause):
        stage_execution_model = baker.make(StageExecutionModel, state="RUNNING",
                                           stage_model=baker.make(StageModel, trigger_type="delta",
                                                                  trigger_args={})
                                           )
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
        plan_execution.state = "RUNNING"

        with self.assertLogs('cryton-debug', level='INFO'):
            plan_execution.pause()

        self.assertEqual(plan_execution.state, "PAUSING")
        mock_stage_pause.assert_not_called()

    @patch('cryton.lib.plan.datetime')
    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.unpause")
    def test_unpause_stage(self, mock_stage_unpause, mock_utcnow):
        mock_utcnow.utcnow.return_value = datetime(3000, 12, 12, 10, 0, 0)
        stage_execution_model = baker.make(StageExecutionModel, state="PAUSED",
                                           stage_model=baker.make(StageModel, trigger_type="delta",
                                                                  trigger_args={})
                                           )
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
        plan_execution.state = "PAUSED"

        plan_execution.unpause()

        self.assertEqual(plan_execution.state, "RUNNING")
        mock_stage_unpause.assert_called()

    @patch("cryton.lib.util.rabbit_send_oneway_msg", Mock())
    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.unschedule")
    def test_pause_suspending_stage(self, mock_stage_unschedule):
        stage_execution_model = baker.make(StageExecutionModel, state="PAUSING",
                                           stage_model=baker.make(StageModel, trigger_type="delta",
                                                                  trigger_args={})
                                           )
        plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
        plan_execution.state = "RUNNING"

        with self.assertLogs('cryton-debug', level='INFO'):
            plan_execution.pause()

        self.assertEqual(plan_execution.state, "PAUSING")
        mock_stage_unschedule.assert_not_called()

    # @patch("cryton.lib.stage.StageExecution.validate_modules")
    # def test_validate_modules(self, mock_stage_validate_modules):
    #     mock_stage_validate_modules.return_value = [(True, None), (False, "error 1")]
    #     stage_execution_model = baker.make(StageExecutionModel)
    #     plan_execution = plan.PlanExecution(plan_execution_id=stage_execution_model.plan_execution.id)
    #
    #     ret = plan_execution.validate_modules()
    #
    #     self.assertEqual(ret, [(True, None), (False, "error 1")])
    #
    # @patch("cryton.lib.stage.StageExecution.validate_modules")
    # def test_validate_modules_more_stages(self, mock_stage_validate_modules):
    #     mock_stage_validate_modules.side_effect = [[(True, None), (False, "error 1")],
    #                                                [(True, None), (False, "error 2")]]
    #     stage_execution_model_1 = baker.make(StageExecutionModel)
    #     stage_execution_model_2 = baker.make(StageExecutionModel)
    #     plan_execution = plan.PlanExecution(plan_execution_id=baker.make(PlanExecutionModel,
    #                                                                      stage_executions=[stage_execution_model_1,
    #                                                                                        stage_execution_model_2]).id)
    #
    #     ret = plan_execution.validate_modules()
    #
    #     self.assertEqual(ret, [(True, None), (False, "error 1"), (True, None), (False, "error 2")])

    def test_report_custom_path(self):
        expected_dict = {"plan_name": "test-plan",
                         "stages": {"test-stage": {
                             "test-step": {"executor": "test-executor", "module": "test-module", "state": "test-state",
                                           "result": "test-result", "std_out": "test-out", "std_err": "test-err",
                                           "mod_out": "test-mod", "mod_err": "test-mod_err"}}}}
        step_model = baker.make(StepModel, executor="test-executor", attack_module="test-module", name="test-step")
        step_execution_model = baker.make(StepExecutionModel, step_model=step_model, state="test-state",
                                          result="test-result",
                                          std_out="test-out", std_err="test-err", mod_out="test-mod",
                                          mod_err="test-mod_err")
        stage_execution_model = baker.make(StageExecutionModel, step_executions=[step_execution_model],
                                           stage_model=baker.make(StageModel, name="test-stage"))
        plan_execution_model = baker.make(PlanExecutionModel, stage_executions=[stage_execution_model],
                                          run=baker.make(RunModel, plan_model=baker.make(PlanModel, name="test-plan")))
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        ret = plan_execution.report_to_file('/tmp/test_cryton')

        self.assertEqual(ret, '/tmp/test_cryton')
        self.assertTrue(os.path.exists('/tmp/test_cryton'))
        with open('/tmp/test_cryton') as test_file:
            contents = yaml.safe_load(test_file)
        os.remove('/tmp/test_cryton')
        self.assertEqual(contents, expected_dict)

    @patch("cryton.lib.plan.config.REPORT_DIR", "/tmp/")
    def test_report_default_path(self):
        expected_dict = {"plan_name": "test-plan",
                         "stages": {"test-stage": {
                             "test-step": {"executor": "test-executor", "module": "test-module", "state": "test-state",
                                           "result": "test-result", "std_out": "test-out", "std_err": "test-err",
                                           "mod_out": "test-mod", "mod_err": "test-mod_err"}}}}
        step_model = baker.make(StepModel, executor="test-executor", attack_module="test-module", name="test-step")
        step_execution_model = baker.make(StepExecutionModel, step_model=step_model, state="test-state",
                                          result="test-result",
                                          std_out="test-out", std_err="test-err", mod_out="test-mod",
                                          mod_err="test-mod_err")
        stage_execution_model = baker.make(StageExecutionModel, step_executions=[step_execution_model],
                                           stage_model=baker.make(StageModel, name="test-stage"))
        plan_execution_model = baker.make(PlanExecutionModel, stage_executions=[stage_execution_model],
                                          run=baker.make(RunModel, plan_model=baker.make(PlanModel, name="test-plan")))
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)
        expected_path = "/tmp/planid-{}-runid-{}-executionid-{}.yaml".format(plan_execution_model.run.plan_model.id,
                                                                             plan_execution_model.run.id,
                                                                             plan_execution_model.id)

        ret = plan_execution.report_to_file()

        self.assertEqual(ret, expected_path)
        self.assertTrue(os.path.exists(expected_path))
        with open(expected_path) as test_file:
            contents = yaml.safe_load(test_file)
        os.remove(expected_path)
        self.assertEqual(contents, expected_dict)

    def test_report_invalid_path(self):
        plan_execution = plan.PlanExecution(plan_execution_id=baker.make(PlanExecutionModel).id)

        with self.assertRaises(IOError):
            plan_execution.report_to_file("/tmp/nonexistentdir/subdir")

    @patch("cryton.lib.plan.os.makedirs")
    def test_generate_evidence_dir(self, mock_util_create_dir):
        plan_execution_model = baker.make(PlanExecutionModel,
                                          run=baker.make(RunModel,
                                                         plan_model=baker.make(PlanModel, evidence_dir="/tmp")),
                                          worker=baker.make(WorkerModel, name='test_worker')
                                          )
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)
        expected_path = "/tmp/run_{}/worker_{}".format(plan_execution_model.run.id, plan_execution_model.worker.name)

        plan_execution._PlanExecution__generate_evidence_dir()

        self.assertEqual(plan_execution.evidence_dir, expected_path)
        mock_util_create_dir.assert_called_with(expected_path, exist_ok=True)

    def test_start_triggers(self):
        mock_start_http_listener = Mock()
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="HTTPListener",
                                                                  trigger_args={}))
        plan_execution_model = baker.make(PlanExecutionModel, stage_executions=[stage_execution_model])
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)
        # ._PlanExecution__start_http_listener = mock_start_http_listener
        trigger_http_listener.TriggerHTTPListener.start = mock_start_http_listener
        # expected_args = {"plan_execution_id": plan_execution_model.id, "stage_id": stage_execution_model.stage_model.id}

        plan_execution.start_triggers()

        # mock_start_http_listener.assert_called_once_with(expected_args)
        mock_start_http_listener.assert_called_once()

    def test_stop_triggers(self):
        mock_stop_http_listeners = Mock()
        stage_execution_model = baker.make(StageExecutionModel,
                                           stage_model=baker.make(StageModel, trigger_type="HTTPListener",
                                                                  trigger_args="{}"))
        plan_execution_model = baker.make(PlanExecutionModel, stage_executions=[stage_execution_model])
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)
        # plan_execution._PlanExecution__stop_http_listeners = mock_stop_http_listeners
        trigger_http_listener.TriggerHTTPListener.stop = mock_stop_http_listeners
        plan_execution.stop_triggers()

        mock_stop_http_listeners.assert_called_once()

    # def test_start_http_listener(self):
    #     plan_execution = plan.PlanExecution(plan_execution_id=baker.make(PlanExecutionModel).id)
    #
    #     ret = plan_execution._PlanExecution__start_http_listener({})
    #
    #     self.assertIsNotNone(ret)
    #
    # def test_stop_http_listeners(self):
    #     plan_execution = plan.PlanExecution(plan_execution_id=baker.make(PlanExecutionModel).id)
    #
    #     ret = plan_execution._PlanExecution__stop_http_listeners()
    #
    #     self.assertIsNotNone(ret)

    def test_filter_all(self):
        plan_execution_model1 = baker.make(PlanExecutionModel)
        plan_execution_model2 = baker.make(PlanExecutionModel)

        ret = plan.PlanExecution.filter()

        self.assertTrue(plan_execution_model1 in ret)
        self.assertTrue(plan_execution_model2 in ret)

    def test_filter_field(self):
        plan_execution_model1 = baker.make(PlanExecutionModel, state="PENDING")
        plan_execution_model2 = baker.make(PlanExecutionModel, state="RUNNING")

        ret = plan.PlanExecution.filter(state="PENDING")

        self.assertTrue(plan_execution_model1 in ret)
        self.assertTrue(plan_execution_model2 not in ret)

    def test_filter_invalid_field(self):
        with self.assertRaises(exceptions.WrongParameterError):
            plan.PlanExecution.filter(invalid="test")

    def test_report(self):
        plan_execution_model = baker.make(PlanExecutionModel, **{'state': 'RUNNING'})
        stage_ex = baker.make(StageExecutionModel, **{'plan_execution': plan_execution_model, 'state': 'FINISHED',
                                                      'aps_job_id': 'test_aps_id'})
        step_ex = baker.make(StepExecutionModel, **{'stage_execution': stage_ex, 'state': 'FINISHED',
                                                    'evidence_file': 'test_evidence_file'})
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)
        report_dict = plan_execution.report()

        self.assertIsInstance(report_dict, dict)
        self.assertEqual(report_dict.get('stage_executions')[0].get('state'), 'FINISHED')
        self.assertIsNotNone(report_dict.get('stage_executions')[0].get('step_executions'))
        self.assertEqual(report_dict.get('stage_executions')[0].get('step_executions')[0]
                         .get('evidence_file'), 'test_evidence_file')

    @patch("cryton.lib.plan.PlanExecution.execute", MagicMock())
    @patch('cryton.lib.util.rabbit_prepare_queue', MagicMock())
    def test_execution(self):
        plan.execution(self.pex_obj.model.id)
        self.pex_obj.execute.assert_called()

    @patch("cryton.lib.stage.StageExecution.validate_modules", MagicMock())
    def test_validate_modules(self):
        plan_execution_model = baker.make(PlanExecutionModel, **{'state': 'RUNNING'})
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)
        plan_execution.validate_modules()

    @patch('cryton.lib.plan.connections.close_all', Mock())
    @patch('cryton.lib.stage.StageExecution.kill', Mock())
    def test_kill(self):
        plan_execution_model = baker.make(PlanExecutionModel, **{'state': 'RUNNING'})
        baker.make(StageExecutionModel, **{'state': 'RUNNING', 'plan_execution': plan_execution_model})
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertLogs('cryton-debug', level='INFO'):
            plan_execution.kill()
        self.assertEqual(plan_execution.state, 'TERMINATED')

    @patch('cryton.lib.plan.PlanExecution.unschedule', Mock())
    def test_kill_scheduled(self):
        plan_execution_model = baker.make(PlanExecutionModel, **{'state': 'SCHEDULED'})
        plan_execution = plan.PlanExecution(plan_execution_id=plan_execution_model.id)

        with self.assertLogs('cryton-debug', level='INFO'):
            plan_execution.kill()
        self.assertEqual(plan_execution.state, 'TERMINATED')
