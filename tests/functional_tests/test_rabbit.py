from django.test import TestCase
import yaml
import os

from unittest.mock import patch, MagicMock

from cryton.lib.util import creator, logger, states, util
from cryton.lib.models import stage, plan, run, step

from cryton.etc import config
import threading
from model_bakery import baker

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
class TestRabbit(TestCase):

    def setUp(self):
        self.worker = creator.create_worker('tt', '192.168.56.130', 'tt_192.168.56.130', 'UP')
        self.workers_list = [self.worker.model]

    def test_connection(self):
        _ = util.rabbit_connection()

    @patch("cryton.lib.triggers.trigger_delta.TriggerDelta.schedule")
    @patch('django.db.connections.close_all', MagicMock)
    def test_whole_plan_execution(self, mock_stage_schedule):
        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        plan_obj = creator.create_plan(plan_dict)
        run_obj = run.Run(plan_model_id=plan_obj.model.id, workers_list=self.workers_list)
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan.PlanExecutionModel.objects.get(
            run_id=run_obj.model.id).id)
        stage_ex_obj = stage.StageExecution(stage_execution_id=stage.StageExecutionModel.objects.get(
            plan_execution_id=plan_ex_obj.model.id).id)

        def se():
            stage_ex_obj.state = states.SCHEDULED
            t = threading.Thread(stage.execution(stage_ex_obj.model.id))
            t.run()

        mock_stage_schedule.side_effect = se

        run_obj.execute()

        self.assertEqual(run_obj.state, states.RUNNING)
        self.assertEqual(plan_ex_obj.state, states.RUNNING)
        self.assertEqual(stage_ex_obj.state, states.RUNNING)
