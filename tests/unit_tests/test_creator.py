from django.test import TestCase
from copy import deepcopy

from cryton.lib.util import creator, exceptions, logger
from cryton.lib.models import stage, plan, step, worker

from cryton.cryton_rest_api.models import (
    PlanModel,
    StageModel,
    WorkerModel,
    RunModel,
    OutputMapping
)

import yaml
import os
from model_bakery import baker
from unittest.mock import patch

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestCreator(TestCase):

    def setUp(self) -> None:
        self.stage_model_obj = baker.make(StageModel)
        self.plan_model_obj = baker.make(PlanModel)
        self.worker_1 = baker.make(WorkerModel)
        self.worker_2 = baker.make(WorkerModel)
        self.run_model = baker.make(RunModel)

    def test_validate_plan(self):
        with open('{}/plan.yaml'.format(TESTS_DIR)) as fp:
            plan_file_dict = yaml.safe_load(fp)
            creator.validate_plan_dict(plan_file_dict=plan_file_dict)

        stages_dict = plan_file_dict.get('plan').pop('stages')
        with self.assertRaises(exceptions.PlanValidationError):
            creator.validate_plan_dict(plan_file_dict=plan_file_dict)

        plan_file_dict.get('plan').update({'stages': stages_dict})
        plan_file_dict.get('plan').get('stages')[0].pop('trigger_type')

        with self.assertRaises(exceptions.StageValidationError):
            creator.validate_plan_dict(plan_file_dict=plan_file_dict)

    def test_create_step(self):
        with open('{}/step.yaml'.format(TESTS_DIR)) as fp, self.assertLogs('cryton-debug', level='INFO') as cm:
            step_dict = yaml.safe_load(fp)
            step_obj = creator.create_step(step_dict, stage_model_id=self.stage_model_obj.id)
        self.assertTrue(step.Step.filter(id=step_obj.model.id).exists())
        self.assertIn('"status": "success"', cm.output[0])
        self.assertFalse(step_obj.is_final)

        step_dict.pop('next')

        step_obj = creator.create_step(step_dict, stage_model_id=self.stage_model_obj.id)
        self.assertTrue(step.Step.filter(id=step_obj.model.id).exists())
        self.assertIn('"status": "success"', cm.output[0])
        self.assertTrue(step_obj.is_final)

        step_dict.pop('is_init')

        step_obj = creator.create_step(step_dict, stage_model_id=self.stage_model_obj.id)
        self.assertTrue(step.Step.filter(id=step_obj.model.id).exists())
        self.assertIn('"status": "success"', cm.output[0])
        self.assertTrue(step_obj.is_final)

        with open('{}/step.yaml'.format(TESTS_DIR)) as fp:
            step_dict = yaml.safe_load(fp)
            step_dict.update({'nonexistent': 'arg'})
        with self.assertRaises(exceptions.StepCreationFailedError):
            step_obj = creator.create_step(step_dict, stage_model_id=self.stage_model_obj.id)

    def test_create_output_mappings_in_step(self):
        with open('{}/step.yaml'.format(TESTS_DIR)) as fp, self.assertLogs('cryton-debug', level='INFO') as cm:
            step_dict = yaml.safe_load(fp)
            step_dict.update({'output_mapping': [{'name_from': 'original', 'name_to': 'new'}]})
            step_obj = creator.create_step(step_dict, stage_model_id=self.stage_model_obj.id)

        self.assertTrue(OutputMapping.objects.filter(step_model=step_obj.model).exists())
        self.assertEqual(OutputMapping.objects.filter(step_model=step_obj.model)[0].name_from, 'original')
        self.assertEqual(OutputMapping.objects.filter(step_model=step_obj.model)[0].name_to, 'new')

    def test_create_stage(self):
        with open('{}/stage.yaml'.format(TESTS_DIR)) as fp, self.assertLogs('cryton-debug', level='INFO') as cm:
            stage_dict = yaml.safe_load(fp)
            stage_obj = creator.create_stage(stage_dict, plan_model_id=self.plan_model_obj.id)
        self.assertTrue(stage.Stage.filter(id=stage_obj.model.id).exists())
        self.assertIn('"status": "success"', cm.output[0])

        step_obj = step.StepModel.objects.get(name='scan-localhost')
        self.assertFalse(step_obj.is_final)

        step_obj = step.StepModel.objects.get(name='ssh-bruteforce')
        self.assertFalse(step_obj.is_final)

        step_obj = step.StepModel.objects.get(name='ssh-login')
        self.assertTrue(step_obj.is_final)

    def test_create_stage_successors(self):
        with open('{}/stage.yaml'.format(TESTS_DIR)) as fp, self.assertLogs('cryton-debug', level='INFO') as cm:
            stage_dict = yaml.safe_load(fp)
            stage_obj = creator.create_stage(stage_dict, plan_model_id=self.plan_model_obj.id)
        self.assertTrue(stage.Stage.filter(id=stage_obj.model.id).exists())
        self.assertIn('"status": "success"', cm.output[0])

        step_model = step.StepModel.objects.get(name='scan-localhost')
        step_obj = step.Step(step_model_id=step_model.id)
        successors = step_obj.successors
        self.assertEqual(len(successors), 2)
        self.assertEqual({step_obj.name for step_obj in successors}, {"ssh-bruteforce", "ssh-login"})

        step_model = step.StepModel.objects.get(name='ssh-bruteforce')
        step_obj = step.Step(step_model_id=step_model.id)
        successors = step_obj.successors
        self.assertEqual(len(successors), 1)
        self.assertEqual(successors[0].name, "ssh-login")

        step_model = step.StepModel.objects.get(name='ssh-login')
        step_obj = step.Step(step_model_id=step_model.id)
        successors = step_obj.successors
        self.assertEqual(len(successors), 0)

    def test_create_stage_wrong(self):
        with open('{}/stage.yaml'.format(TESTS_DIR)) as fp, self.assertLogs('cryton-debug', level='INFO') as cm, \
                self.assertRaises(exceptions.StageCreationFailedError):
            stage_dict_orig = yaml.safe_load(fp)
            stage_dict = deepcopy(stage_dict_orig)

            creator.create_stage(stage_dict, plan_model_id=1000)
        self.assertNotIn('"status": "success"', cm.output[0])

        with self.assertRaises(exceptions.StageCreationFailedError):
            creator.create_stage("Wrong", plan_model_id=self.plan_model_obj.id)

        with self.assertRaises(exceptions.StageCreationFailedError):
            stage_dict.update({'nonexistent_arg': 5})
            creator.create_stage(stage_dict, plan_model_id=self.plan_model_obj.id)

        with self.assertRaises(exceptions.StageCreationFailedError):
            stage_dict = deepcopy(stage_dict_orig)
            stage_dict.get('steps')[0].get('next')[0].update({'type': 'nonexistent'})
            creator.create_stage(stage_dict, plan_model_id=self.plan_model_obj.id)

        with self.assertRaises(exceptions.StageCreationFailedError):
            stage_dict = deepcopy(stage_dict_orig)
            stage_dict.get('steps')[0].get('next')[0].update({'step': 'nonexistent-step'})
            creator.create_stage(stage_dict, plan_model_id=self.plan_model_obj.id)

        stage_dict = deepcopy(stage_dict_orig)

        stage_dict.get('steps')[0].get('next')[0].update({'value': ['OK', 'FAIL']})
        creator.create_stage(stage_dict, plan_model_id=self.plan_model_obj.id)

    def test_create_plan(self):
        with open('{}/plan.yaml'.format(TESTS_DIR)) as fp, self.assertLogs('cryton-debug', level='INFO') as cm:
            plan_dict = yaml.safe_load(fp)
            plan_obj = creator.create_plan(plan_dict)
        self.assertTrue(plan.Plan.filter(id=plan_obj.model.id).exists())
        self.assertTrue(stage.Stage.filter(name="stage-one").exists())
        self.assertIn('"status": "success"', cm.output[0])

        step_obj = step.StepModel.objects.get(name='scan-localhost')
        self.assertFalse(step_obj.is_final)

        step_obj = step.StepModel.objects.get(name='ssh-bruteforce')
        self.assertTrue(step_obj.is_final)

        with open('{}/plan.yaml'.format(TESTS_DIR)) as fp:
            plan_dict = yaml.safe_load(fp)
        plan_dict.get('plan').update({'nonexistent': 'arg'})
        with self.assertRaises(exceptions.PlanValidationError):
            creator.create_plan(plan_dict)

        mock_validation = patch('cryton.lib.util.creator.validate_plan_dict')
        mock_validation.start()
        with self.assertRaises(exceptions.PlanCreationFailedError):
            creator.create_plan(plan_dict)
        mock_validation.stop()

        with open('{}/plan.yaml'.format(TESTS_DIR)) as fp:
            plan_dict = yaml.safe_load(fp)
        plan_dict.get('plan').get('stages')[0].update({'depends_on': ['arg']})
        with self.assertRaises(exceptions.DependencyDoesNotExist):
            creator.create_plan(plan_dict)

    def test_create_run(self):
        creator.create_run(self.plan_model_obj.id, [self.worker_1, self.worker_2])

    def test_create_run_wrong_plan(self):
        with self.assertRaises(exceptions.RunCreationFailedError):
            creator.create_run(-1, [self.worker_1, self.worker_2])

    def test_create_worker_model(self):
        self.assertIsInstance(creator.create_worker('name', 'address'), worker.Worker)

        self.assertIsInstance(creator.create_worker('name', 'address', 'prefix'), worker.Worker)

        self.assertIsInstance(creator.create_worker('name', 'address', 'prefix', 'state'), worker.Worker)

        with self.assertRaises(exceptions.WrongParameterError):
            creator.create_worker('name', '')

        with self.assertRaises(exceptions.WrongParameterError):
            creator.create_worker('', 'address')

    @patch('cryton.lib.util.creator.create_step')
    def test_create_plan_err(self, mock_create_step):
        mock_create_step.side_effect = exceptions.StepCreationFailedError('debug')
        with open('{}/plan.yaml'.format(TESTS_DIR)) as fp:
            plan_dict = yaml.safe_load(fp)
            with self.assertRaises(exceptions.PlanCreationFailedError), \
                 self.assertLogs('cryton-debug', level='ERROR') as cm:
                creator.create_plan(plan_dict)

        self.assertFalse(stage.Stage.filter(name="stage-one").exists())
        self.assertIn('"status": "fail"', cm.output[0])

    def test_create_plan_execution(self):
        # Wront plan
        with self.assertRaises(exceptions.PlanExecutionCreationFailedError):
            creator.create_plan_execution(666, self.worker_1.id, self.run_model.id)

        # Wrong worker
        with self.assertRaises(exceptions.PlanExecutionCreationFailedError):
            creator.create_plan_execution(self.plan_model_obj.id, 666, self.run_model.id)

        # Wrong run
        with self.assertRaises(exceptions.PlanExecutionCreationFailedError):
            creator.create_plan_execution(self.plan_model_obj.id, self.worker_1.id, 666)

        # Correct
        creator.create_plan_execution(self.plan_model_obj.id, self.worker_1.id, self.run_model.id)
