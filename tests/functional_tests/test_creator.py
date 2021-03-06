import os
import pytest
import yaml

from cryton.lib.util import creator
from cryton.cryton_rest_api.models import StepModel, StageModel, DependencyModel, SuccessorModel


TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@pytest.mark.django_db
class TestCreator:
    def test_create_plan(self):
        stage_count = 3
        step_count = 5
        dependency_count = 3
        successor_count = 3

        with open(TESTS_DIR + '/test-creator.yml') as plan_yaml:
            plan_dict = yaml.safe_load(plan_yaml)
        plan_obj_id = creator.create_plan(plan_dict)
        assert plan_obj_id == 1
        assert stage_count == StageModel.objects.filter(plan_model_id=plan_obj_id).count()
        assert step_count == StepModel.objects.filter(stage_model__plan_model_id=plan_obj_id).count()
        assert dependency_count == DependencyModel.objects.filter(stage_model__plan_model_id=plan_obj_id).count()
        assert successor_count == SuccessorModel.objects.\
            filter(parent_step__stage_model__plan_model_id=plan_obj_id).count()
