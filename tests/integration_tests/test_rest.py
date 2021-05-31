from django.test import Client
from django.urls import reverse

from cryton.cryton_rest_api.models import (
    PlanModel,
    StageModel,
    StepModel,
    PlanExecutionModel,
    RunModel,
    WorkerModel,
    StageExecutionModel,
    PlanTemplateFileModel,
    ExecutionVariableModel
)

from cryton.lib.util import creator, logger, states
from cryton.lib.models import stage, plan, step, run

from rest_framework import status
from rest_framework.test import APITestCase
import os

from unittest.mock import patch, Mock

import json
import yaml
import datetime

from model_bakery import baker
from django.utils import timezone

devnull = open(os.devnull, "w")
TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch("sys.stdout", devnull)
@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
class RestPlanTest(APITestCase):

    def setUp(self):
        self.client = Client()

        self.run_model_obj = baker.make(RunModel)
        self.run_id = self.run_model_obj.id
        self.plan_model_obj = baker.make(PlanModel)
        self.plan_id = self.plan_model_obj.id
        self.worker_model_obj = baker.make(WorkerModel)
        self.worker_id = self.worker_model_obj.id

    def test_get_plan_list(self):
        response = self.client.get(reverse("planmodel-list"))
        plans_list = list(PlanModel.objects.all().values_list('name', flat=True))
        response_plans_list = [plan_obj.get('name') for plan_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(plans_list, response_plans_list)

    def test_create_plan(self):
        # Wrong YAML
        response = self.client.post(reverse("planmodel-list"), 'not_a_dict',
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:

            args = {"file": plan_yaml}
            response = self.client.post(reverse("plantemplatefilemodel-list"), args)
            plan_filled_id = response.data.get('id')

        with open(TESTS_DIR + '/plan-template.yaml') as plan_yaml:
            args = {"file": plan_yaml}
            response = self.client.post(reverse("plantemplatefilemodel-list"), args)
            plan_template_id = response.data.get('id')

        # Correct filled
        response = self.client.post(reverse("planmodel-list"), {"plan_template": plan_filled_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)

        # Wrong format
        response = self.client.post(reverse("planmodel-list"), {"plan_template": "not_a_dict"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_delete_plan(self):
        self.assertTrue(PlanModel.objects.filter(id=self.plan_id).exists())
        response = self.client.delete(reverse("planmodel-detail", kwargs={"pk": self.plan_id}))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PlanModel.objects.filter(id=self.plan_id).exists())

        response = self.client.delete(reverse("planmodel-detail", kwargs={"pk": 666}))
        self.assertEqual(response.status_code, 404)

    def test_get_plan(self):
        response = self.client.get(reverse("planmodel-detail", kwargs={"pk": self.plan_id}),
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("name"), self.plan_model_obj.name)

    def test_validate(self):
        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        response = self.client.post(reverse('planmodel-validate'), plan_dict, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        plan_dict.get('plan').pop('stages')
        response = self.client.post(reverse('planmodel-validate'), plan_dict, content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Wrong format
        response = self.client.post(reverse("planmodel-validate"), {"plan": "not_a_dict"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Wrong format
        response = self.client.post(reverse("planmodel-validate"), "not_a_dict",
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch('threading.Thread.start', Mock())
    def test_execute_plan(self):

        # Missing run id, missing worker id
        response = self.client.post(reverse("planmodel-execute",
                                            kwargs={"pk": self.plan_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Missing worker id
        response = self.client.post(reverse("planmodel-execute",
                                            kwargs={"pk": self.plan_id}),
                                    {'run_id': self.run_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Missing run id
        response = self.client.post(reverse("planmodel-execute",
                                            kwargs={"pk": self.plan_id}),
                                    {'worker_id': self.worker_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Wrong run id
        response = self.client.post(reverse("planmodel-execute",
                                            kwargs={"pk": self.plan_id}),
                                    {'worker_id': self.worker_id,
                                     'run_id': 666},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Wrong worker id
        response = self.client.post(reverse("planmodel-execute",
                                            kwargs={"pk": self.plan_id}),
                                    {'worker_id': 666,
                                     'run_id': self.run_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Correct
        response = self.client.post(reverse("planmodel-execute",
                                            kwargs={"pk": self.plan_id}),
                                    {'worker_id': self.worker_id,
                                     'run_id': self.run_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)

        self.assertIsNotNone(response.data.get("plan_execution_id"))


@patch("sys.stdout", devnull)
@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
class RestStageTest(APITestCase):

    def setUp(self):
        self.client = Client()
        self.stage_model_obj = baker.make(StageModel)
        self.stage_id = self.stage_model_obj.id
        self.plan_model_obj = baker.make(PlanModel)
        self.plan_id = self.plan_model_obj.id
        self.plan_exec_obj = baker.make(PlanExecutionModel)

    def test_get_stage_list(self):
        response = self.client.get(reverse("stagemodel-list"))
        stages_list = list(StageModel.objects.all().values_list('name', flat=True))
        response_stages_list = [stage_obj.get('name') for stage_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(stages_list, response_stages_list)

        # URL param
        response = self.client.get(reverse("stagemodel-list"), {'plan_model__id': self.plan_id})
        stages_list = list(StageModel.objects.filter(plan_model_id=self.plan_id).values_list('name', flat=True))
        response_stages_list = [stage_obj.get('name') for stage_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(stages_list, response_stages_list)

    def test_create_stage(self):
        with open(TESTS_DIR + '/stage.yaml') as stage_yaml:
            stage_dict = yaml.safe_load(stage_yaml)

        stage_dict.update({"plan_model": self.plan_id})
        response = self.client.post(reverse("stagemodel-list"), stage_dict,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        resp_stage_name = stage.Stage(stage_model_id=int(response.data.get('detail').get('stage_id'))).name
        self.assertEqual(resp_stage_name, stage_dict.get('name'))

        # Wrong format
        response = self.client.post(reverse("stagemodel-list"), {"stage": "no_dict"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        stage_dict.update({"plan_model": -50})
        response = self.client.post(reverse("stagemodel-list"), stage_dict,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_delete_stage(self):
        self.assertTrue(StageModel.objects.filter(id=self.stage_id).exists())
        response = self.client.delete(reverse("stagemodel-detail", kwargs={"pk": self.stage_id}))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(StageModel.objects.filter(id=self.stage_id).exists())

        response = self.client.delete(reverse("stagemodel-detail", kwargs={"pk": 666}))
        self.assertEqual(response.status_code, 404)

    def test_get_stage(self):
        response = self.client.get(reverse("stagemodel-detail", kwargs={"pk": self.stage_id}),
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("name"), self.stage_model_obj.name)

    def test_validate(self):
        with open(TESTS_DIR + '/stage.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        response = self.client.post(reverse('stagemodel-validate'), plan_dict, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        plan_dict.pop('steps')
        response = self.client.post(reverse('stagemodel-validate'), plan_dict, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch('threading.Thread.start', Mock())
    def test_execute_stage(self):
        plan_execution_id = self.plan_exec_obj.id

        # Missing execution id
        response = self.client.post(reverse("stagemodel-execute",
                                            kwargs={"pk": self.stage_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Correct
        response = self.client.post(reverse("stagemodel-execute",
                                            kwargs={"pk": self.stage_id}),
                                    {'plan_execution_id': plan_execution_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data.get("stage_execution_id"))


@patch("sys.stdout", devnull)
@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
class RestStepTest(APITestCase):

    def setUp(self):
        self.client = Client()
        self.step_model_obj = baker.make(StepModel)
        self.stage_model_obj = baker.make(StageModel)
        self.plan_model_obj = baker.make(PlanModel)
        self.step_id = self.step_model_obj.id
        self.stage_id = self.stage_model_obj.id
        self.plan_id = self.plan_model_obj.id
        self.stage_exec_obj = baker.make(StageExecutionModel)

    def test_get_step_list(self):
        response = self.client.get(reverse("stepmodel-list"))
        steps_list = list(StepModel.objects.all().values_list('name', flat=True))
        response_steps_list = [step_obj.get('name') for step_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(steps_list, response_steps_list)

        response = self.client.get(reverse("stepmodel-list"), {'stage_model__id': self.stage_id})
        steps_list = list(StepModel.objects.filter(stage_model_id=self.stage_id).values_list('name', flat=True))
        response_steps_list = [step_obj.get('name') for step_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(steps_list, response_steps_list)

        response = self.client.get(reverse("stepmodel-list"), {'stage_model__plan_model__id': self.plan_id})
        steps_list = list(
            StepModel.objects.filter(stage_model__plan_model_id=self.plan_id).values_list('name', flat=True))
        response_steps_list = [step_obj.get('name') for step_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(steps_list, response_steps_list)

    def test_create_step(self):
        with open(TESTS_DIR + '/step.yaml') as step_yaml:
            step_dict = yaml.safe_load(step_yaml)

        # Missing stage_model
        response = self.client.post(reverse("stepmodel-list"),
                                    step_dict,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Correct stage_model
        step_dict.update({"stage_model": self.stage_id})
        response = self.client.post(reverse("stepmodel-list"),
                                    step_dict,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        resp_step_name = step.Step(step_model_id=int(response.data.get('detail').get('step_id'))).name
        self.assertEqual(resp_step_name, step_dict.get('name'))

    def test_delete_step(self):
        self.assertTrue(StepModel.objects.filter(id=self.step_id).exists())
        response = self.client.delete(reverse("stepmodel-detail", kwargs={"pk": self.step_id}))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(StepModel.objects.filter(id=self.step_id).exists())

        response = self.client.delete(reverse("stepmodel-detail", kwargs={"pk": 666}))
        self.assertEqual(response.status_code, 404)

    def test_get_step(self):
        response = self.client.get(reverse("stepmodel-detail", kwargs={"pk": self.step_id}),
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("name"), self.step_model_obj.name)

    def test_validate(self):
        with open(TESTS_DIR + '/step.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        response = self.client.post(reverse('stepmodel-validate'), plan_dict, content_type="application/json")
        self.assertEqual(response.status_code, 200)

        plan_dict.pop('attack_module')
        response = self.client.post(reverse('stepmodel-validate'), plan_dict, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch('threading.Thread.start', Mock())
    def test_execute_step(self):
        stage_execution_id = self.stage_exec_obj.id

        # Missing execution id
        response = self.client.post(reverse("stepmodel-execute",
                                            kwargs={"pk": self.step_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Correct
        response = self.client.post(reverse("stepmodel-execute",
                                            kwargs={"pk": self.step_id}),
                                    {'stage_execution_id': stage_execution_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.data.get("step_execution_id"))


@patch("sys.stdout", devnull)
@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
@patch("cryton.lib.models.plan.os.makedirs", Mock())
class RestRunTest(APITestCase):

    def setUp(self):
        self.client = Client()
        self.plan_model_obj = baker.make(PlanModel, **{'name': 'test_plan_name'})
        self.plan_id = self.plan_model_obj.id
        self.worker_obj_1 = baker.make(WorkerModel, **{'name': 'test_worker_name1', 'q_prefix': 'test_queue_1'})
        self.worker_obj_2 = baker.make(WorkerModel, **{'name': 'test_worker_name2', 'q_prefix': 'test_queue_2'})
        self.run_obj = run.Run(plan_model_id=self.plan_id, workers_list=[self.worker_obj_1, self.worker_obj_2])
        self.run_model_id = self.run_obj.model.id

        # self.plan_execution = baker.make(PlanExecutionModel, worker=self.worker_obj_1, run=self.run_obj.model)

    def test_get_run_list(self):
        response = self.client.get(reverse("runmodel-list"))
        runs_list = list(RunModel.objects.all().values_list('id', flat=True))
        response_runs_list = [run_obj.get('id') for run_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(runs_list, response_runs_list)

    def test_create_run(self):
        args = {"plan_model": self.plan_id, "workers": [self.worker_obj_1.id, self.worker_obj_2.id]}
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        run_model_id = int(response.data.get('detail').get('run_model_id'))
        plan_id = run.Run(run_model_id=run_model_id).model.plan_model_id
        self.assertEqual(plan_id, self.plan_id)
        self.assertEqual(response.status_code, 201)

        # Missing plan_model
        plan_model = args.pop("plan_model")
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Missing workers
        workers = args.pop("workers")
        args.update({"plan_model": plan_model})
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Missing both
        response = self.client.post(reverse("runmodel-list"),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Wrong format
        args.update({"workers": workers})
        args.update({"plan_model": "not_id"})
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        args.update({"plan_model": 1000})
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        args.update({"workers": ['test']})
        args.update({"plan_model": self.plan_id})
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        args.update({"workers": 'test'})
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        args.update({"workers": [1000]})
        response = self.client.post(reverse("runmodel-list"),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_delete_run(self):
        self.assertTrue(RunModel.objects.filter(id=self.run_model_id).exists())
        response = self.client.delete(reverse("runmodel-detail", kwargs={"pk": self.run_model_id}))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(RunModel.objects.filter(id=self.run_model_id).exists())

        response = self.client.delete(reverse("runmodel-detail", kwargs={"pk": 666}))
        self.assertEqual(response.status_code, 404)

    def test_get_run(self):
        response = self.client.get(reverse("runmodel-detail", kwargs={"pk": self.run_model_id}),
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("id"), self.run_obj.model.id)

    def test_create_single_worker(self):
        client = Client()
        response = client.post(reverse("runmodel-list"), {"workers": [self.worker_obj_1.id, self.worker_obj_2.id],
                                                          "plan_model": self.plan_id},
                               content_type="application/json")

        self.assertEqual(response.status_code, 201)
        run_model_id = response.data.get('detail').get("run_model_id")

        count_after = PlanExecutionModel.objects.filter(run_id=run_model_id).count()

        self.assertEqual(count_after, 2)
        self.assertEqual(self.run_obj.state, 'PENDING')

    def test_create_no_worker(self):
        client = Client()
        response = client.post(reverse("runmodel-list"),
                               content_type="application/json")

        self.assertEqual(response.status_code, 400)

    @patch('cryton.lib.util.scheduler_client.schedule_function', Mock(return_value=1))
    def test_schedule(self):
        # Missing schedule time
        args = {}
        response = self.client.post(reverse("runmodel-schedule", kwargs={"pk": self.run_model_id}),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.data.get('param_name'), 'start_time')
        self.assertEqual(response.status_code, 400)

        # Wrong schedule time
        args.update({"start_time": 'test'})
        response = self.client.post(reverse("runmodel-schedule", kwargs={"pk": self.run_model_id}),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # correct state
        self.run_obj.state = states.PENDING
        args.update({"start_time": timezone.now().strftime('%Y-%m-%d %H:%M:%S')})

        response = self.client.post(reverse("runmodel-schedule", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)

        # Wrong state
        self.run_obj.state = states.RUNNING
        response = self.client.post(reverse("runmodel-schedule", kwargs={"pk": self.run_model_id}),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch('cryton.lib.util.scheduler_client.schedule_function', Mock(return_value=1))
    @patch('cryton.lib.util.scheduler_client.remove_job', Mock(return_value=0))
    def test_reschedule(self):
        # Missing schedule time
        args = {}
        response = self.client.post(reverse("runmodel-reschedule", kwargs={"pk": self.run_model_id}),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.data.get('param_name'), 'start_time')
        self.assertEqual(response.status_code, 400)

        # Wrong schedule time
        args.update({"start_time": 'test'})
        response = self.client.post(reverse("runmodel-reschedule", kwargs={"pk": self.run_model_id}),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # correct state
        self.run_obj.state = states.SCHEDULED
        args.update({"start_time": timezone.now().strftime('%Y-%m-%d %H:%M:%S')})

        response = self.client.post(reverse("runmodel-reschedule", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)

        # Wrong state
        self.run_obj.state = states.RUNNING
        response = self.client.post(reverse("runmodel-reschedule", kwargs={"pk": self.run_model_id}),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch('cryton.lib.util.scheduler_client.remove_job', Mock(return_value=0))
    def test_unschedule(self):

        # correct state
        self.run_obj.state = states.SCHEDULED
        response = self.client.post(reverse("runmodel-unschedule", kwargs={"pk": self.run_obj.model.id}),
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)

        # Wrong state
        self.run_obj.state = states.RUNNING
        response = self.client.post(reverse("runmodel-unschedule", kwargs={"pk": self.run_model_id}),

                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @patch('cryton.lib.util.scheduler_client.remove_job', Mock(return_value=0))
    @patch('cryton.lib.util.scheduler_client.schedule_function', Mock(return_value=0))
    def test_postpone(self):

        self.run_obj.schedule_time = timezone.now()

        # No delta
        self.run_obj.state = states.SCHEDULED
        response = self.client.post(reverse("runmodel-postpone", kwargs={"pk": self.run_obj.model.id}),
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 400)

        # wrong delta
        self.run_obj.state = states.SCHEDULED
        args = {'delta': 'test'}
        response = self.client.post(reverse("runmodel-postpone", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 400)

        # correct state, correct delta
        args = {'delta': '1h1m1s'}
        self.run_obj.state = states.SCHEDULED
        with self.assertLogs('cryton-test', level='INFO') as cm:
            response = self.client.post(reverse("runmodel-postpone", kwargs={"pk": self.run_obj.model.id}),
                                        args,
                                        content_type="application/json"
                                        )
        self.assertIn('"status": "success"', cm.output[0])
        self.assertEqual(response.status_code, 200)

        # Wrong state, correct delta
        self.run_obj.state = states.RUNNING
        response = self.client.post(reverse("runmodel-postpone", kwargs={"pk": self.run_model_id}),
                                    args,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_execute(self):
        response = self.client.post(reverse("runmodel-execute", kwargs={"pk": self.run_model_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)

        # Invalid state
        self.run_obj.state = states.RUNNING
        response = self.client.post(reverse("runmodel-execute", kwargs={"pk": self.run_model_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        run_obj = run.Run(plan_model_id=self.plan_id, workers_list=[self.worker_obj_1, self.worker_obj_2])

        # Invalid state
        run_obj.state = states.SCHEDULED
        response = self.client.post(reverse("runmodel-execute", kwargs={"pk": self.run_model_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_report(self):
        response = self.client.get(reverse("runmodel-report", kwargs={"pk": self.run_model_id}),
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

    @patch("cryton.lib.util.util.rabbit_send_oneway_msg", Mock())
    def test_pause(self):
        # Wrong state
        self.run_obj.state = states.SCHEDULED
        response = self.client.post(reverse("runmodel-pause", kwargs={"pk": self.run_model_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Correct state
        self.run_obj.state = states.RUNNING
        for pex in PlanExecutionModel.objects.filter(run_id=self.run_obj.model.id):
            pex.state = states.RUNNING
            pex.save()
        response = self.client.post(reverse("runmodel-pause", kwargs={"pk": self.run_model_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)

    def test_unpause(self):
        # Wrong state
        self.run_obj.state = states.SCHEDULED
        response = self.client.post(reverse("runmodel-unpause", kwargs={"pk": self.run_model_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        # Correct state
        self.run_obj.state = states.RUNNING
        self.run_obj.state = states.PAUSING
        self.run_obj.state = states.PAUSED
        for pex in PlanExecutionModel.objects.filter(run_id=self.run_obj.model.id):
            pex.state = states.PAUSING
            pex.state = states.PAUSED
            pex.save()
        response = self.client.post(reverse("runmodel-unpause", kwargs={"pk": self.run_model_id}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)

    @patch('cryton.lib.util.scheduler_client.schedule_function', Mock(return_value=1))
    @patch('cryton.lib.util.scheduler_client.remove_job', Mock(return_value=1))
    @patch("cryton.lib.util.util.rabbit_send_oneway_msg", Mock())
    def test_whole_chain(self):
        # create
        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:
            args = {"file": plan_yaml}
            response = self.client.post(reverse("plantemplatefilemodel-list"), args)
            plan_filled_id = response.data.get('id')

        response = self.client.post(reverse("planmodel-list"), {"plan_template": plan_filled_id},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        plan_obj = plan.Plan(plan_model_id=int(response.data.get('detail').get('plan_model_id')))

        response = self.client.post(reverse("runmodel-list"),
                                    {"plan_model": plan_obj.model.id,
                                     "workers": [self.worker_obj_1.id, self.worker_obj_2.id]},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)
        run_model_id = int(response.data.get('detail').get('run_model_id'))
        plan_id = run.Run(run_model_id=run_model_id).model.plan_model_id
        self.assertEqual(plan_id, plan_obj.model.id)

        # schedule
        schedule_time_dt = datetime.datetime.strptime("2050-10-11 09:11:47", '%Y-%m-%d %H:%M:%S')
        args = {"start_time": "2050-10-11 09:11:47",
                "worker": "worker1"}
        response = self.client.post(reverse("runmodel-schedule", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(self.run_obj.schedule_time, schedule_time_dt)

        # reschedule
        schedule_time_dt = datetime.datetime.strptime("2040-10-11 09:11:47", '%Y-%m-%d %H:%M:%S')
        args = {"start_time": "2040-10-11 09:11:47"}
        response = self.client.post(reverse("runmodel-reschedule", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.run_obj.schedule_time, schedule_time_dt)

        # postpone
        args = {'delta': '1h0m0s'}
        response = self.client.post(reverse("runmodel-postpone", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.run_obj.schedule_time, schedule_time_dt + datetime.timedelta(hours=1))

        # unschedule
        args = {}
        response = self.client.post(reverse("runmodel-unschedule", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)

        # execute
        args = {}
        response = self.client.post(reverse("runmodel-execute", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)

        # pause
        args = {}
        response = self.client.post(reverse("runmodel-pause", kwargs={"pk": self.run_obj.model.id}),
                                    args,
                                    content_type="application/json"
                                    )
        self.assertEqual(response.status_code, 200)


@patch("sys.stdout", devnull)
@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
class RestWorkerTest(APITestCase):

    def setUp(self):
        self.client = Client()

    def test_create_worker(self):
        worker_dict = dict(name='test_worker')

        response = self.client.post(reverse("workermodel-list"),
                                    worker_dict,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

        worker_dict = dict(name='test_worker',
                           address='test_address')
        response = self.client.post(reverse("workermodel-list"),
                                    worker_dict,
                                    content_type="application/json")
        self.assertEqual(response.status_code, 201)


@patch("sys.stdout", devnull)
@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
class RestExecVarsTest(APITestCase):
    def setUp(self):
        self.client = Client()
        self.pex = baker.make(PlanExecutionModel)
        self.exec_var = baker.make(ExecutionVariableModel, name='test', value='test', plan_execution_id=self.pex.id)

    def test_create_execution_variable(self):
        with open(TESTS_DIR + "/inventory.yaml") as f:
            inventory = f.read()

        args = {'plan_execution_id': self.pex.id, 'inventory_file': inventory}
        response = self.client.post(reverse("executionvariablemodel-list"), args, content_type="application/json")

        self.assertEqual(response.status_code, 201)
        self.assertIsInstance(response.data.get('detail'), str)
        created_ids = json.loads(response.data.get('detail'))
        for each in created_ids:
            self.assertTrue(ExecutionVariableModel.objects.filter(id=each).exists())

    def test_delete_execution_variable(self):
        self.assertTrue(ExecutionVariableModel.objects.filter(id=self.exec_var.id).exists())
        response = self.client.delete(reverse("executionvariablemodel-detail", kwargs={"pk": self.exec_var.id}))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ExecutionVariableModel.objects.filter(id=self.exec_var.id).exists())

        response = self.client.delete(reverse("executionvariablemodel-detail", kwargs={"pk": self.exec_var.id}))
        self.assertEqual(response.status_code, 404)

    def test_list_execution_variables(self):
        response = self.client.get(reverse("executionvariablemodel-list"))
        exec_vars_list = list(ExecutionVariableModel.objects.all().values_list('id', flat=True))
        response_exec_vars_list = [exec_var_obj.get('id') for exec_var_obj in response.data.get('results')]
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(exec_vars_list, response_exec_vars_list)


@patch("sys.stdout", devnull)
@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-test'))
class RestFilesTest(APITestCase):

    def setUp(self):
        self.client = Client()

    def test_create_template(self):
        plan_template = open(TESTS_DIR + "/plan-template.yaml")

        args = {"file": plan_template}
        response = self.client.post(reverse("plantemplatefilemodel-list"), args)

        self.assertEqual(response.status_code, 201)
        self.assertIsInstance(response.data.get('id'), int)
        self.assertTrue(PlanTemplateFileModel.objects.filter(id=response.data.get('id')).exists())


class FilteringTest(APITestCase):

    def setUp(self) -> None:
        with open(TESTS_DIR + '/plan.yaml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)

        self.client = Client()
        self.plan_model_obj = creator.create_plan(plan_dict)
        self.worker_obj_1 = baker.make(WorkerModel)
        self.worker_obj_2 = baker.make(WorkerModel)

        self.run_obj = run.Run(plan_model_id=self.plan_model_obj.model.id,
                               workers_list=[self.worker_obj_1, self.worker_obj_2])

    def test_filtering_plan(self):
        response = self.client.get(reverse("planexecutionmodel-list"), content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 2)

        response = self.client.get(reverse("planexecutionmodel-list"),
                                   {"run__id": self.run_obj.model.id},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 2)

        response = self.client.get(reverse("planexecutionmodel-list"),
                                   {"run__id": 12345},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 0)

    def test_filtering_stage(self):
        pex = PlanExecutionModel.objects.filter(run_id=self.run_obj.model.id)[0]
        response = self.client.get(reverse("stageexecutionmodel-list"), content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 2)

        response = self.client.get(reverse("stageexecutionmodel-list"),
                                   {"plan_execution__id": pex.id},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 1)

        response = self.client.get(reverse("stageexecutionmodel-list"),
                                   {"plan_execution__id": 0},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 0)

        response = self.client.get(reverse("stageexecutionmodel-list"),
                                   {"plan_execution__run__id": self.run_obj.model.id},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 2)

        response = self.client.get(reverse("stageexecutionmodel-list"),
                                   {"plan_execution__run__id": -1},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 0)

    def test_filtering_step(self):
        pex = PlanExecutionModel.objects.filter(run_id=self.run_obj.model.id)[0]
        response = self.client.get(reverse("stepexecutionmodel-list"), content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 4)

        response = self.client.get(reverse("stepexecutionmodel-list"),
                                   {"stage_execution__plan_execution__id": pex.id},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 2)

        response = self.client.get(reverse("stepexecutionmodel-list"),
                                   {"stage_execution__plan_execution__id": -1},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 0)

        sex = StageExecutionModel.objects.filter(plan_execution_id=pex.id)[0]

        response = self.client.get(reverse("stepexecutionmodel-list"),
                                   {"stage_execution__id": sex.id},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 2)

        response = self.client.get(reverse("stepexecutionmodel-list"),
                                   {"stage_execution__id": 0},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        # TODO sometimes returns 2
        self.assertEqual(res_count, 0)

        response = self.client.get(reverse("stepexecutionmodel-list"),
                                   {"stage_execution__plan_execution__run__id": self.run_obj.model.id},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 4)

        response = self.client.get(reverse("stepmodel-list"),
                                   {"name": 'bruteforce'},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 200)

        res_count = response.data.get("count")
        self.assertEqual(res_count, 1)

    def test_ordering(self):
        last_id = step.StepModel.objects.last().id
        response = self.client.get(reverse("stepmodel-list"), {'order_by': '-id'}, content_type="application/json")
        self.assertEqual(last_id, response.data.get('results')[0].get('id'))

    def test_offset(self):
        first_id = step.StepModel.objects.first().id
        response = self.client.get(reverse("stepmodel-list"), {'offset': '1'}, content_type="application/json")
        self.assertNotEqual(first_id, response.data.get('results')[0].get('id'))

        response = self.client.get(reverse("stepmodel-list"), {'offset': '0'}, content_type="application/json")
        self.assertEqual(first_id, response.data.get('results')[0].get('id'))

    def test_limit(self):
        response = self.client.get(reverse("stepmodel-list"), {'limit': '1'}, content_type="application/json")
        self.assertEqual(1, len(response.data.get('results')))

        response = self.client.get(reverse("stepmodel-list"), {'limit': '2'}, content_type="application/json")
        self.assertEqual(2, len(response.data.get('results')))
