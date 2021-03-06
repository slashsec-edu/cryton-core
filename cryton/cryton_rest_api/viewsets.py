from threading import Thread
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
import pytz
import jinja2
import yaml
from django.http import QueryDict
from rest_framework.viewsets import GenericViewSet, ViewSet
from rest_framework import status, permissions, mixins
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.reverse import reverse
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.core.files.uploadedfile import InMemoryUploadedFile

from cryton.cryton_rest_api import serializers
from cryton.cryton_rest_api.models import PlanModel, StageModel, StepModel, RunModel, PlanExecutionModel,\
    StageExecutionModel, StepExecutionModel, WorkerModel, PlanTemplateFileModel, ExecutionVariableModel
from cryton.cryton_rest_api import exceptions

from cryton.lib.util import creator, exceptions as core_exceptions, states, util, constants
from cryton.lib.models import stage, plan, step, worker, run
from cryton import settings as cryton_settings


def filter_decorator(func):
    """
    Decorator for filtering of serializer results
    :param func:
    :return:
    """

    def inner(self):
        # Create dictionary filter
        filters_dict = {key: value for key, value in self.request.query_params.items()}
        # Get rid of parameters that would get in a way of filter

        order_by_param = filters_dict.pop('order_by', 'id')
        filters_dict.pop('limit', None)
        filters_dict.pop('offset', None)

        # Obtain queryset
        queryset = func(self)

        # Update filters (optionally with __icontains)
        unsearchable_keys = ['stage_model_id', 'plan_model_id', 'run_id', 'plan_execution_id',
                             'stage_execution_id']
        filters_dict_update = dict()
        for key, value in filters_dict.items():
            if key not in unsearchable_keys:
                filters_dict_update.update({key + '__icontains': value})
            else:
                filters_dict_update.update({key: value})

        # Filter and order
        queryset = queryset.filter(**filters_dict_update)
        queryset = queryset.order_by(order_by_param)

        return queryset

    return inner


def load_body_yaml(request) -> dict:
    try:
        received_dict = yaml.safe_load(request.body.decode('utf8'))
    except Exception as ex:
        raise exceptions.ApiInternalError(detail=str(ex))
    return received_dict


def get_start_time(request) -> datetime:
    time_zone = request.data.get('time_zone', 'utc')
    try:
        str_start_time = request.data['start_time']
    except KeyError:
        raise exceptions.ApiWrongOrMissingArgument(param_name='start_time', param_type=str)

    try:
        start_time = datetime.strptime(str_start_time, constants.TIME_FORMAT)
    except ValueError as f_ex:
        try:
            start_time = datetime.strptime(str_start_time, constants.TIME_FORMAT_DETAILED)
        except ValueError as s_ex:
            raise exceptions.ApiWrongOrMissingArgument(param_name='start_time', param_type='str',
                                                       name=f"{f_ex}; {s_ex}")

    try:
        start_time = util.convert_to_utc(start_time, time_zone)
    except pytz.exceptions.UnknownTimeZoneError as ex:
        raise exceptions.ApiWrongOrMissingArgument(param_name='time_zone', param_type='str', name=str(ex))

    return start_time


class GeneralViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin,
                     mixins.ListModelMixin, GenericViewSet):
    """
    A viewset that provides default `retrieve()`, `update()`, `partial_update()`, `destroy()` and `list()` actions.
    """
    def get_serializer_class(self):
        assert self.method_serializer_classes is not None, (
                "Expected view %s should contain method_serializer_classes "
                "to get right serializer class." %
                (self.__class__.__name__,)
        )
        for methods, serializer_cls in self.method_serializer_classes.items():
            if self.request.method in methods:
                return serializer_cls

    if cryton_settings.AUTHENTICATED_REST_API:
        permission_classes = [permissions.IsAuthenticated]

    # Needs to be overriden in subclass
    method_serializer_classes = {}


class AdvancedViewSet(mixins.CreateModelMixin, GeneralViewSet):
    pass


class ExecutionViewSet(AdvancedViewSet):
    pass


class PlanViewSet(AdvancedViewSet):
    """
          list:
          List available Plans

          retrieve:
          Get Plan specified by ID

          destroy:
          Delete Plan specified by ID

          create:
          Create new Plan

          validate:
          Validate Plan dict
    """
    method_serializer_classes = {
        ("GET",): serializers.PlanModelSerializer,
        ("POST",): serializers.PlanModelSerializerCreate
    }

    queryset = PlanModel.objects.all()
    http_method_names = ["get", "post", "delete"]

    response_plan_id = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'plan_model_id': openapi.Schema(name='plan_model_id', type=openapi.TYPE_INTEGER),
                    'link': openapi.Schema(name='link', type=openapi.TYPE_STRING)
                }
            )
        }
    )

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    param_run_execution = openapi.Schema(type=openapi.TYPE_OBJECT, properties={
        "run_id": openapi.Schema(
            name='run_id',
            type=openapi.TYPE_INTEGER
        ),
        "worker_id": openapi.Schema(
            name='worker_id',
            type=openapi.TYPE_INTEGER
        ),
    })

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    @swagger_auto_schema(operation_description="Create new Plan. You have to provide a whole JSON/YAML "
                                               "describing all Stages and Steps",
                         responses={201: response_plan_id, 500: response_detail, 400: response_detail})
    def create(self, request, **kwargs):
        """

        :param request:
            body:
                plan_template: int
                inventory_file: list (str)
        :param kwargs:
        :return:
        """

        # Get values from request
        plan_template_id = util.get_int_from_obj(request.data, 'plan_template')
        if plan_template_id is None:
            raise exceptions.ApiWrongFormat("'plan_template' should be type 'int', was type '{}' ({})"
                                            .format(type(plan_template_id), plan_template_id))

        inventory_files = request.data.get("inventory_file", [])
        if type(inventory_files) != list:
            inventory_files = [inventory_files]
        # Read Plan template
        plan_template_obj = PlanTemplateFileModel.objects.get(id=plan_template_id)
        with open(str(plan_template_obj.file.path)) as _:
            plan_template = _.read()

        # Read all inventory files
        inventory_dict = dict()
        for inventory_file in inventory_files:
            if isinstance(inventory_file, InMemoryUploadedFile):
                inventory_file_contents = inventory_file.read()
            else:
                inventory_file_contents = inventory_file
            try:
                inv_dict = util.parse_inventory_file(inventory_file_contents)
                if inv_dict is not None:
                    inventory_dict.update(inv_dict)
            except ValueError as ex:
                raise exceptions.ApiWrongFormat("Cannot read inventory file. Original exception: {}. "
                                                "Inventory file: {}.".format(ex, inventory_file))

        # Either fill the Plan template or consider the template already filled
        if inventory_dict != {} and inventory_dict is not None:
            try:
                plan_dict = util.fill_template(plan_template, inventory_dict)
            except jinja2.exceptions.UndefinedError as ex:
                raise exceptions.ApiWrongOrMissingArgument("Some variables from template left unfilled, "
                                                           "original exception: {}".format(str(ex)), param_type="str")
            except core_exceptions.PlanValidationError as ex:
                raise exceptions.ApiWrongOrMissingArgument("File is not a Template, original exception: {}".format(ex),
                                                           param_type="str")
        else:
            plan_dict = plan_template

        # Create Plan Instance
        try:
            plan_obj_id = creator.create_plan(yaml.safe_load(plan_dict))
        except (yaml.YAMLError, AttributeError) as ex:
            raise exceptions.ApiWrongFormat(detail=str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(detail=str(ex))

        location_url = reverse('planmodel-detail', args=[plan_obj_id], request=request)
        location_hdr = {'Location': location_url}
        msg = {'detail': {'plan_model_id': plan_obj_id, 'link': location_url}}
        return Response(msg, status=status.HTTP_201_CREATED, headers=location_hdr)

    def destroy(self, request, *args, **kwargs):
        plan_id = kwargs.get('pk')
        try:
            plan.Plan(plan_model_id=plan_id).delete()
        except core_exceptions.PlanObjectDoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail="Plan with ID {} does not exist.".format(plan_id))

        return Response({'detail': 'deleted'}, status=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(operation_description="Validate Plan dictionary",
                         responses={200: response_detail, 500: response_detail, 400: response_detail}, method='post')
    @action(methods=["post"], detail=False)
    def validate(self, request):

        received_dict = load_body_yaml(request)
        try:
            plan.Plan.validate(received_dict.get('plan'))
        except (yaml.YAMLError, AttributeError, core_exceptions.ValidationError) as ex:
            raise exceptions.ApiWrongFormat(detail=str(ex))

        msg = {'detail': '{}'.format(
            "Plan is valid.")}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(method='post', request_body=param_run_execution,
                         responses={200: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def execute(self, request, **kwargs):
        plan_model_id = kwargs.get("pk")
        try:
            run_id = util.get_int_from_obj(request.data, 'run_id')
            worker_id = util.get_int_from_obj(request.data, 'worker_id')
        except KeyError as ex:
            if 'run_id' in str(ex):
                param_name = 'run_id'
            else:
                param_name = 'worker_id'
            raise exceptions.ApiWrongOrMissingArgument(param_name=param_name, param_type=int)

        if not PlanModel.objects.filter(id=plan_model_id).exists():
            raise exceptions.ApiWrongOrMissingArgument(param_name="plan_model_id", param_type=int)
        if not WorkerModel.objects.filter(id=worker_id).exists():
            raise exceptions.ApiWrongOrMissingArgument(param_name="worker_id", param_type=int)
        if not RunModel.objects.filter(id=run_id).exists():
            raise exceptions.ApiWrongOrMissingArgument(param_name="run_id", param_type=int)

        plan_exec = plan.PlanExecution(plan_model_id=plan_model_id, worker_id=worker_id, run_id=run_id)

        thread = Thread(target=plan_exec.execute)
        thread.start()

        location_url = reverse('planexecutionmodel-detail', args=[plan_exec.model.id], request=request)
        location_hdr = {'Location': location_url}

        msg = {'detail': 'Plan executed', 'plan_execution_id': plan_exec.model.id, 'link': location_url}
        return Response(msg, status=status.HTTP_200_OK, headers=location_hdr)

    response_get_plan = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "plan_model_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "plan": openapi.Schema(type=openapi.TYPE_OBJECT)
                })
        }
    )

    response_err_get_plan = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING
            )
        }
    )

    @swagger_auto_schema(responses={200: response_get_plan, 404: response_err_get_plan})
    @action(methods=["get"], detail=True)
    def get_plan(self, _, **kwargs):
        plan_model_id = kwargs.get("pk")
        try:
            plan_dict = util.get_plan_yaml(plan_model_id)
        except ObjectDoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail=f"Plan with ID {plan_model_id} does not exist.")

        msg = {"detail": {"plan_model_id": plan_model_id, "plan": plan_dict}}
        return Response(msg, status=status.HTTP_200_OK)


class StageViewSet(GeneralViewSet):
    """
          list:
          List available Stages

          retrieve:
          Get Stage specified by ID

          destroy:
          Delete Stage specified by ID

          create:
          Create new Stage

          validate:
          Validate Stage dict
    """

    method_serializer_classes = {
        ("GET",): serializers.StageModelSerializer,
        ("POST",): serializers.StageModelSerializerCreate
    }
    queryset = StageModel.objects.all()
    http_method_names = ["get", "post", "delete"]

    param_plan_execution = openapi.Schema(type=openapi.TYPE_OBJECT, properties={
        "plan_execution_id": openapi.Schema(
            name='plan_execution_id',
            type=openapi.TYPE_INTEGER
        ),
    })

    response_stage_id = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'stage_model_id': openapi.Schema(name='stage_model_id', type=openapi.TYPE_INTEGER),
                    'link': openapi.Schema(name='link', type=openapi.TYPE_STRING)
                }
            )
        }
    )

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    def destroy(self, request, *args, **kwargs):
        stage_id = kwargs.get('pk')
        try:
            stage.Stage(stage_model_id=stage_id).delete()
        except core_exceptions.StageObjectDoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail="Stage with ID {} does not exist.".format(stage_id))

        return Response({'detail': 'deleted'}, status=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(operation_description="Validate Stage.",
                         responses={200: response_detail, 400: response_detail})
    @action(methods=["post"], detail=False)
    def validate(self, request):

        received_dict = load_body_yaml(request)

        try:
            stage.Stage.validate(received_dict)
        except (yaml.YAMLError, core_exceptions.ValidationError) as ex:
            raise exceptions.ApiWrongFormat(detail=str(ex))

        msg = {'detail': '{}'.format(
            "Stage is valid.")}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(method='post', request_body=param_plan_execution,
                         responses={200: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def execute(self, request, **kwargs):
        stage_model_id = kwargs.get("pk")
        try:
            plan_execution_id = util.get_int_from_obj(request.data, 'plan_execution_id')
        except KeyError:
            raise exceptions.ApiWrongOrMissingArgument(param_name='plan_execution_id',
                                                       param_type=int)
        try:
            plan_ex_obj = PlanExecutionModel.objects.get(id=plan_execution_id)
        except core_exceptions.ObjectDoesNotExist:
            raise exceptions.ApiWrongOrMissingArgument(param_name='plan_execution_id',
                                                       param_type=int,
                                                       name="PlanExecution with ID {} does not exist.".
                                                       format(plan_execution_id))
        # Check state
        if plan_ex_obj.state != states.PENDING:
            raise exceptions.ApiWrongObjectState(detail="Cannot execute Stage for PlanExecution which is not in state "
                                                        "{}".format(states.PENDING))
        stage_exec = stage.StageExecution(stage_model_id=stage_model_id,
                                          plan_execution_id=plan_execution_id)
        thread = Thread(target=stage_exec.execute)
        thread.start()

        location_url = reverse('stageexecutionmodel-detail', args=[stage_exec.model.id], request=request)
        location_hdr = {'Location': location_url}

        msg = {'detail': 'Stage executed', 'stage_execution_id': stage_exec.model.id, 'link': location_url}
        return Response(msg, status=status.HTTP_200_OK, headers=location_hdr)


class StepViewSet(GeneralViewSet):
    """
          list:
          List available Steps

          retrieve:
          Get Step specified by ID

          destroy:
          Delete Step specified by ID

          create:
          Create new Step

          validate:
          Validate Step dict
    """
    queryset = StepModel.objects.all()
    http_method_names = ["get", "post", "delete"]

    method_serializer_classes = {
        ("GET",): serializers.StepModelSerializer,
        ("POST",): serializers.StepModelSerializerCreate
    }

    param_stage_execution = openapi.Schema(type=openapi.TYPE_OBJECT, properties={
        "stage_execution_id": openapi.Schema(
            name='stage_execution_id',
            type=openapi.TYPE_INTEGER
        ),
    })

    response_step_id = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'step_model_id': openapi.Schema(name='step_model_id', type=openapi.TYPE_INTEGER),
                    'link': openapi.Schema(name='link', type=openapi.TYPE_STRING)
                }
            )
        }
    )

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    def destroy(self, request, *args, **kwargs):
        step_id = kwargs.get('pk')
        try:
            step.Step(step_model_id=step_id).delete()
        except core_exceptions.StepObjectDoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail="Step with ID {} does not exist.".format(step_id))

        return Response({'detail': 'deleted'}, status=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(operation_description="Validate Step.",
                         responses={200: response_detail, 400: response_detail})
    @action(methods=["post"], detail=False)
    def validate(self, request):

        received_dict = load_body_yaml(request)

        try:
            step.Step.validate(received_dict)
        except (yaml.YAMLError, core_exceptions.ValidationError) as ex:
            raise exceptions.ApiWrongFormat(detail=str(ex))

        msg = {'detail': '{}'.format(
            "Step is valid.")}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(method='post', request_body=param_stage_execution,
                         responses={'200': response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def execute(self, request, **kwargs):
        step_model_id = kwargs.get("pk")
        stage_execution_id = None
        try:
            stage_execution_id = util.get_int_from_obj(request.data, 'stage_execution_id')
            stage_ex_obj = StageExecutionModel.objects.get(id=stage_execution_id)
        except KeyError:
            raise exceptions.ApiWrongOrMissingArgument(param_name='stage_execution_id',
                                                       param_type=int)
        except core_exceptions.ObjectDoesNotExist:
            raise exceptions.ApiWrongOrMissingArgument(param_name='stage_execution_id',
                                                       param_type=int,
                                                       name="StageExecution with ID {} does not exist.".
                                                       format(stage_execution_id))
        plan_ex_id = stage_ex_obj.plan_execution_id
        try:
            plan_ex_obj = PlanExecutionModel.objects.get(id=plan_ex_id)
        except core_exceptions.ObjectDoesNotExist:
            raise exceptions.ApiWrongOrMissingArgument(param_name='plan_execution_id',
                                                       param_type=int,
                                                       name="PlanExecution with ID {} does not exist.".
                                                       format(plan_ex_id))
        # Check state
        if plan_ex_obj.state != states.PENDING:
            raise exceptions.ApiWrongObjectState(detail="Cannot execute Stage for PlanExecution which is not in state "
                                                        "{}".format(states.PENDING))

        try:
            step_exec = step.StepExecution(step_model_id=step_model_id,
                                           stage_execution_id=stage_execution_id)
        except core_exceptions.ObjectDoesNotExist:
            raise exceptions.ApiWrongOrMissingArgument(param_name='stage_execution_id',
                                                       param_type=int)
        thread = Thread(target=step_exec.execute)
        thread.start()

        location_url = reverse('stepexecutionmodel-detail', args=[step_exec.model.id], request=request)
        location_hdr = {'Location': location_url}

        msg = {'detail': 'Step executed', 'step_execution_id': step_exec.model.id, 'link': location_url}
        return Response(msg, status=status.HTTP_200_OK, headers=location_hdr)


class RunViewSet(AdvancedViewSet):
    """
        list:
        List available Runs

        retrieve:
        Get Run specified by ID

        destroy:
        Delete Run specified by ID

        create:
        Create new Run

        report:
        Generate report

        pause:
        Pause Run

        unpause:
        Unpause Run

        schedule:
        Schedule Run

        unschedule:
        Unschedule Run

        reschedule:
        Reschedule Run

        postpone:
        Postpone Run
    """
    queryset = RunModel.objects.all()
    http_method_names = ["get", "post", "delete"]

    method_serializer_classes = {
        ("GET",): serializers.RunModelSerializer,
        ("POST",): serializers.RunModelSerializerCreate
    }

    param_start_time = openapi.Schema(type=openapi.TYPE_OBJECT, properties={
        "start_time": openapi.Schema(
            name='start_time',
            type=openapi.TYPE_STRING
        ),
    })
    param_delta = openapi.Schema(type=openapi.TYPE_OBJECT, properties={
        "delta": openapi.Schema(
            name='delta',
            type=openapi.TYPE_STRING
        ),
    })

    response_run_id = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'run_model_id': openapi.Schema(name='run_model_id', type=openapi.TYPE_INTEGER),
                    'link': openapi.Schema(name='link', type=openapi.TYPE_STRING)
                }
            )
        }
    )

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    @swagger_auto_schema(operation_description="Create new Run",
                         responses={201: response_run_id, 400: response_detail})
    def create(self, request, **kwargs):
        try:
            plan_model_id = request.data["plan_model"]
            workers = request.data["workers"]
        except KeyError as ex:
            if "workers" not in str(ex):
                raise exceptions.ApiWrongOrMissingArgument(param_name="plan_model", param_type=str)
            else:
                raise exceptions.ApiWrongOrMissingArgument(param_name="workers", param_type=list)
        if type(workers) is not list:
            raise exceptions.ApiWrongOrMissingArgument(param_name="workers", param_type=list,
                                                       name="Parameter must be"
                                                            " of type 'list(int)'"
                                                            "")
        try:
            workers_list = WorkerModel.objects.filter(id__in=workers)
        except ValueError:
            raise exceptions.ApiWrongOrMissingArgument(param_name="workers", param_type=list, name="Parameter must be"
                                                                                                   "of type list(int)")
        if workers_list is None or not workers_list.exists():
            raise exceptions.ApiWrongOrMissingArgument(param_name="workers", param_type=list, name="Nonexistent Worker"
                                                                                                   " specified")
        if type(plan_model_id) is not int:
            raise exceptions.ApiWrongOrMissingArgument(param_name="plan_model", param_type=int, name="Parameter must be"
                                                                                                     " of type 'int'")

        if not PlanModel.objects.filter(id=plan_model_id).exists():
            raise exceptions.ApiWrongOrMissingArgument(param_name="plan_model", param_type=int, name="Nonexistent Plan"
                                                                                                     " specified")

        run_obj_id = run.Run(plan_model_id=plan_model_id, workers_list=workers_list).model.id

        location_url = reverse('runmodel-detail', args=[run_obj_id], request=request)
        location_hdr = {'Location': location_url}
        msg = {'detail': {'run_model_id': run_obj_id, 'link': location_url}}
        return Response(msg, status=status.HTTP_201_CREATED, headers=location_hdr)

    def destroy(self, request, *args, **kwargs):
        run_model_id = kwargs.get('pk')
        try:
            run.Run(run_model_id=run_model_id).delete()
        except core_exceptions.RunObjectDoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail="Run with ID {} does not exist.".format(run_model_id))

        return Response({'detail': 'deleted'}, status=status.HTTP_204_NO_CONTENT)

    @swagger_auto_schema(operation_description="Generate Run report",
                         responses={200: response_detail, 500: response_detail, 400: response_detail})
    @action(methods=["get"], detail=True)
    def report(self, _, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)
        try:
            rep = run_obj.report()
        except Exception as ex:
            raise exceptions.ApiInternalError(detail=str(ex))

        return Response(rep, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Pause Run", request_body=serializers.serializers.Serializer(),
                         responses={200: response_detail, 500: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def pause(self, _, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)
        try:
            run_obj.pause()
        except core_exceptions.PlanHasNoExecution as ex:
            raise exceptions.ApiWrongObject(detail=str(ex))
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(detail=str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(detail=str(ex))

        msg = {'detail': '{}'.format("Run {} is paused.".format(run_model_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Unpause Run", request_body=serializers.serializers.Serializer(),
                         responses={200: response_detail, 500: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def unpause(self, _, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)
        try:
            run_obj.unpause()
        except core_exceptions.PlanHasNoExecution as ex:
            raise exceptions.ApiWrongObject(detail=str(ex))
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(detail=str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(detail=str(ex))

        msg = {'detail': '{}'.format("Run {} is unpaused.".format(run_model_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(method='post', request_body=param_start_time,
                         responses={200: response_detail, 400: response_detail, 500: response_detail})
    @action(methods=["post"], detail=True)
    def schedule(self, request, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)

        start_time = get_start_time(request)

        try:
            run_obj.schedule(start_time)
        except core_exceptions.RunInvalidStateError as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Run {} is scheduled for {}.".format(run_model_id, start_time))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Execute Run", request_body=serializers.serializers.Serializer(),
                         responses={200: response_detail, 500: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def execute(self, _, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)

        if run_obj.state not in states.RUN_EXECUTE_NOW_STATES:
            raise exceptions.ApiWrongObjectState('Run object in wrong state: {}, must be in: {}'
                                                 .format(run_obj.state, states.RUN_EXECUTE_NOW_STATES))

        try:
            run_obj.execute()
        except core_exceptions.RunInvalidStateError as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Run {} was executed.".format(run_model_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Reschedule Run", method='post', request_body=param_start_time,
                         responses={200: response_detail, 400: response_detail, 500: response_detail})
    @action(methods=["post"], detail=True)
    def reschedule(self, request, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)

        start_time = get_start_time(request)

        try:
            run_obj.reschedule(start_time)
        except core_exceptions.RunInvalidStateError as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Run {} is rescheduled for {}.".format(run_model_id, start_time))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(method='post', operation_description="Postpone Run",
                         request_body=param_delta, responses={200: response_detail, 400: response_detail,
                                                              500: response_detail})
    @action(methods=["post"], detail=True)
    def postpone(self, request, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)
        try:
            delta = request.data['delta']
        except KeyError:
            raise exceptions.ApiWrongOrMissingArgument(param_name='delta', param_type=str)

        try:
            delta = util.parse_delta_to_datetime(delta)
        except core_exceptions.UserInputError:
            raise exceptions.ApiWrongOrMissingArgument(param_name='delta', param_type=str)

        try:
            run_obj.postpone(delta)
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(detail=str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Run {} is postponed by {}.".format(run_model_id, delta))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Unschedule Run",
                         request_body=serializers.serializers.Serializer(),
                         responses={201: response_detail, 500: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def unschedule(self, _, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)
        try:
            run_obj.unschedule()
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Run {} is unscheduled.".format(run_model_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Kill Run",
                         request_body=serializers.serializers.Serializer(),
                         responses={201: response_detail, 500: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def kill(self, _, **kwargs):
        run_model_id = kwargs.get("pk")
        run_obj = run.Run(run_model_id=run_model_id)

        try:
            run_obj.kill()
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Run {} is terminated.".format(run_model_id))}
        return Response(msg, status=status.HTTP_200_OK)

    response_get_plan = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "run_model_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                    "plan": openapi.Schema(type=openapi.TYPE_OBJECT)
                })
        }
    )

    response_err_get_plan = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING
            )
        }
    )

    @swagger_auto_schema(responses={200: response_get_plan, 404: response_err_get_plan})
    @action(methods=["get"], detail=True)
    def get_plan(self, _, **kwargs):
        run_model_id = kwargs.get("pk")
        try:
            run_obj = RunModel.objects.get(id=run_model_id)
        except ObjectDoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail=f"Run with ID {run_model_id} does not exist.")

        plan_model_id = run_obj.plan_model_id
        plan_dict = util.get_plan_yaml(plan_model_id)

        msg = {"detail": {"run_model_id": run_model_id, "plan": plan_dict}}
        return Response(msg, status=status.HTTP_200_OK)


class PlanExecutionViewSet(ExecutionViewSet):
    """
        list:
        List available PlanExecutions

        retrieve:
        Get PlanExecution specified by ID
    """
    method_serializer_classes = {
        ("GET",): serializers.PlanExecutionModelSerializer,
        ("POST",): serializers.PlanExecutionModelSerializer
    }
    queryset = PlanExecutionModel.objects.all()
    http_method_names = ["get", "post"]

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    @action(methods=["get"], detail=True)
    def report(self, _, **kwargs):
        plan_execution_id = kwargs.get('pk')
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan_execution_id)
        report_dict = plan_ex_obj.report()

        return Response(report_dict, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True)
    def pause(self, _, **kwargs):
        plan_execution_id = kwargs.get('pk')
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan_execution_id)
        plan_ex_obj.pause()
        msg = {'detail': '{}'.format("Plan execution {} is paused.".format(plan_execution_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True)
    def unpause(self, _, **kwargs):
        plan_execution_id = kwargs.get('pk')
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan_execution_id)
        plan_ex_obj.unpause()
        msg = {'detail': '{}'.format("Plan execution {} unpaused.".format(plan_execution_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True)
    def validate_modules(self, _, **kwargs):
        plan_execution_id = kwargs.get('pk')
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan_execution_id)
        plan_ex_obj.validate_modules()

        msg = {'detail': '{}'.format("Plan's modules were validated.")}
        return Response(msg, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True)
    def kill(self, _, **kwargs):
        plan_execution_id = kwargs.get('pk')
        plan_ex_obj = plan.PlanExecution(plan_execution_id=plan_execution_id)

        try:
            plan_ex_obj.kill()
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Plan execution {} is terminated.".format(plan_execution_id))}
        return Response(msg, status=status.HTTP_200_OK)


class StageExecutionViewSet(ExecutionViewSet):
    """
        list:
        List available StageExecutions

        retrieve:
        Get StageExecution specified by ID
    """
    method_serializer_classes = {
        ("GET",): serializers.StageExecutionModelSerializer,
        ("POST",): serializers.StageExecutionModelSerializer
    }
    queryset = StageExecutionModel.objects.all()
    http_method_names = ["get", "post"]

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    request_detail = openapi.Schema(type=openapi.TYPE_OBJECT, properties={
        "immediately": openapi.Schema(
            name='immediately',
            type=openapi.TYPE_BOOLEAN
        ),
    })

    @action(methods=["get"], detail=True)
    def report(self, _, **kwargs):
        stage_execution_id = kwargs.get('pk')
        stage_ex_obj = stage.StageExecution(stage_execution_id=stage_execution_id)
        report_dict = stage_ex_obj.report()

        return Response(report_dict, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True)
    def kill(self, _, **kwargs):
        stage_execution_id = kwargs.get('pk')
        stage_ex_obj = stage.StageExecution(stage_execution_id=stage_execution_id)

        try:
            stage_ex_obj.kill()
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Stage execution {} is terminated.".format(stage_execution_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Re-execute StageExecution.", request_body=request_detail,
                         responses={200: response_detail, 400: response_detail, 500: response_detail})
    @action(methods=["post"], detail=True)
    def re_execute(self, request, **kwargs):
        stage_execution_id = kwargs.get('pk')
        stage_ex_obj = stage.StageExecution(stage_execution_id=stage_execution_id)

        immediately = request.data.get('immediately', True)
        if not isinstance(immediately, bool):
            raise exceptions.ApiWrongOrMissingArgument(param_name='immediately', param_type=bool)

        try:
            stage_ex_obj.re_execute(immediately)
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Stage execution {} re-executed.".format(stage_execution_id))}
        return Response(msg, status=status.HTTP_200_OK)


class StepExecutionViewset(ExecutionViewSet):
    """
        list:
        List available StepExecutions

        retrieve:
        Get StepExecution specified by ID
    """
    method_serializer_classes = {
        ("GET",): serializers.StepExecutionModelSerializer,
        ("POST",): serializers.StepExecutionModelSerializer
    }
    queryset = StepExecutionModel.objects.all()
    http_method_names = ["get", "post"]

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    request_detail = openapi.Schema(type=openapi.TYPE_OBJECT)

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        plan_execution_id = self.request.query_params.get('plan_execution_id')
        stage_execution_id = self.request.query_params.get('stage_execution_id')
        run_id = self.request.query_params.get('run_id')

        if plan_execution_id:
            queryset = queryset.filter(stage_execution__plan_execution_id=plan_execution_id)
        if stage_execution_id:
            queryset = queryset.filter(stage_execution_id=stage_execution_id)
        if run_id:
            queryset = queryset.filter(stage_execution__plan_execution__run_id=run_id)

        return queryset

    @action(methods=["get"], detail=True)
    def report(self, _, **kwargs):
        step_execution_id = kwargs.get('pk')
        step_ex_obj = step.StepExecution(step_execution_id=step_execution_id)
        report_dict = step_ex_obj.report()

        return Response(report_dict, status=status.HTTP_200_OK)

    @action(methods=["post"], detail=True)
    def kill(self, _, **kwargs):
        step_execution_id = kwargs.get('pk')
        step_ex_obj = step.StepExecution(step_execution_id=step_execution_id)

        try:
            step_ex_obj.kill()
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Step execution {} is terminated.".format(step_execution_id))}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Re-execute StepExecution.", request_body=request_detail,
                         responses={200: response_detail, 400: response_detail, 500: response_detail})
    @action(methods=["post"], detail=True)
    def re_execute(self, _, **kwargs):
        step_execution_id = kwargs.get('pk')
        step_ex_obj = stage.StepExecution(step_execution_id=step_execution_id)

        try:
            step_ex_obj.re_execute()
        except (core_exceptions.StateTransitionError, core_exceptions.InvalidStateError) as ex:
            raise exceptions.ApiWrongObjectState(str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(str(ex))

        msg = {'detail': '{}'.format("Step execution {} re-executed.".format(step_execution_id))}
        return Response(msg, status=status.HTTP_200_OK)


class WorkerViewset(AdvancedViewSet):
    """
        list:
        List available WorkerModels

        retrieve:
        Get WorkerModel specified by ID

        create:
        Create new WorkerModel

        destroy:
        Delete WorkerModel
    """
    method_serializer_classes = {
        ("GET",): serializers.WorkerModelSerializer,
        ("POST",): serializers.WorkerModelSerializer
    }
    queryset = WorkerModel.objects.all()
    http_method_names = ["get", "post", "delete"]

    response_worker_id = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'worker_model_id': openapi.Schema(name='worker_model_id', type=openapi.TYPE_INTEGER),
                    'link': openapi.Schema(name='link', type=openapi.TYPE_STRING)
                }
            )
        }
    )

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    @swagger_auto_schema(operation_description="Create new Worker.",
                         responses={201: response_worker_id, 500: response_detail, 400: response_detail})
    def create(self, request, **kwargs):
        try:
            params = {key: request.data.get(key) for key in ('name', 'address', 'q_prefix')}
            worker_obj_id = creator.create_worker(**params)
        except core_exceptions.WrongParameterError as ex:
            raise exceptions.ApiWrongFormat(detail=str(ex))
        except Exception as ex:
            raise exceptions.ApiInternalError(detail=str(ex))
        location_url = reverse('workermodel-detail', args=[worker_obj_id], request=request)
        location_hdr = {'Location': location_url}
        msg = {'detail': {'worker_model_id': worker_obj_id, 'link': location_url}}
        return Response(msg, status=status.HTTP_201_CREATED, headers=location_hdr)

    @action(methods=["post"], detail=True)
    def healthcheck(self, _, **kwargs):
        worker_model_id = kwargs.get('pk')

        worker_obj = worker.Worker(worker_model_id=worker_model_id)
        worker_obj.healthcheck()

        msg = {'detail': {'worker_model_id': worker_obj.model.id, 'worker_state': worker_obj.state}}

        return Response(msg, status=status.HTTP_200_OK)


class PlanTemplateViewset(AdvancedViewSet):
    """
        list:
        List available PlanTemplateModels

        retrieve:
        Get PlanTemplateModel specified by ID

        create:
        Create new PlanTemplateModel

        destroy:
        Delete PlanTemplateModel
    """
    method_serializer_classes = {
        ("GET",): serializers.PlanTemplateFileSerializer,
        ("POST",): serializers.PlanTemplateFileSerializerCreate
    }
    queryset = PlanTemplateFileModel.objects.all()
    http_method_names = ["get", "post", "delete"]

    response_get_template = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'template_model_id': openapi.Schema(name='template_model_id', type=openapi.TYPE_INTEGER),
                    'template': openapi.Schema(name='template', type=openapi.TYPE_OBJECT)
                }
            )
        }
    )

    response_update_template = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'template_model_id': openapi.Schema(name='template_model_id', type=openapi.TYPE_INTEGER)
                }
            )
        }
    )

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    @swagger_auto_schema(operation_description="Get Template (its YAML).",
                         responses={200: response_get_template, 500: response_detail, 400: response_detail})
    @action(methods=["get"], detail=True)
    def get_template(self, _, **kwargs):
        template_id = kwargs.get("pk")
        try:
            plan_template_obj = PlanTemplateFileModel.objects.get(id=template_id)
        except PlanTemplateFileModel.DoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail=f"Template with ID {template_id} does not exist.")

        try:
            with open(str(plan_template_obj.file.path), "r") as template_file:
                plan_template = yaml.safe_load(template_file)
        except IOError:
            raise exceptions.ApiInternalError("Couldn't find the Template's file.")

        msg = {"detail": {"template_model_id": template_id, "template": plan_template}}
        return Response(msg, status=status.HTTP_200_OK)

    @swagger_auto_schema(operation_description="Update Template using YAML.",
                         responses={201: response_update_template, 500: response_detail, 400: response_detail})
    @action(methods=["post"], detail=True)
    def update_template(self, request, **kwargs):
        template_id = kwargs.get("pk")
        if type(request.data) == QueryDict:
            new_data = request.data.dict()
        else:
            new_data = request.data

        try:
            plan_template_obj = PlanTemplateFileModel.objects.get(id=template_id)
        except PlanTemplateFileModel.DoesNotExist:
            raise exceptions.ApiObjectDoesNotExist(detail=f"Template with ID {template_id} does not exist.")

        try:
            with open(str(plan_template_obj.file.path), "w") as template_file:
                yaml.safe_dump(new_data, template_file)
        except IOError:
            raise exceptions.ApiInternalError("Couldn't find the Template's file.")

        msg = {"detail": {"template_model_id": template_id}}
        return Response(msg, status=status.HTTP_201_CREATED)


class ExecutionVariableViewset(AdvancedViewSet):
    """
        list:
        List available ExecutionVariables

        retrieve:
        Get ExecutionVariable specified by ID

        create:
        Create new ExecutionVariable

        destroy:
        Delete ExecutionVariable
    """
    method_serializer_classes = {
        ("GET",): serializers.ExecutionVariableSerializer,
        ("POST",): serializers.ExecutionVariableSerializer
    }
    queryset = ExecutionVariableModel.objects.all()
    http_method_names = ["get", "post", "delete"]

    response_detail = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    request_detail = openapi.Schema(type=openapi.TYPE_OBJECT, properties={
        "plan_execution_id": openapi.Schema(
            name='plan_execution_id',
            type=openapi.TYPE_INTEGER
        ),
        "inventory_file": openapi.Schema(
            name='inventory_file',
            type=openapi.TYPE_STRING
        ),
    })

    @filter_decorator
    def get_queryset(self):
        queryset = self.queryset

        return queryset

    @swagger_auto_schema(operation_description="Create new execution variable.", request_body=request_detail,
                         responses={201: response_detail, 400: response_detail, 500: response_detail})
    def create(self, request, **kwargs):
        try:
            plan_execution_id = util.get_int_from_obj(request.data, 'plan_execution_id')
            inventory_file = request.data.pop('inventory_file')
        except KeyError as ex:
            raise exceptions.ApiWrongFormat(detail=str(ex))

        if isinstance(inventory_file, str):
            inventory_file_contents = inventory_file
        else:
            inventory_file_contents = inventory_file[0].read()

        created_exec_vars = list()

        try:
            inventory_dict = util.parse_inventory_file(inventory_file_contents)
        except ValueError as ex:
            raise exceptions.ApiWrongFormat("Cannot read inventory file. Original exception: {}".format(ex))
        if inventory_dict is None:
            raise exceptions.ApiWrongFormat("Could not parse inventory. Received: '{}'".
                                            format(inventory_file_contents))
        for name, value in inventory_dict.items():
            params = {'plan_execution_id': plan_execution_id, 'name': name, 'value': value}
            try:
                exec_var_model = ExecutionVariableModel.objects.create(**params)
                created_exec_vars.append(exec_var_model.id)
            except Exception as ex:
                raise exceptions.ApiInternalError(detail=str(ex))

        msg = {'detail': str(created_exec_vars)}
        return Response(msg, status=status.HTTP_201_CREATED)


class LogViewSet(ViewSet):
    """
        list:
        List existing logs
    """
    http_method_names = ["get"]

    response_ok = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            "count": openapi.Schema(type=openapi.TYPE_STRING),
            "results": openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.TYPE_STRING
            )
        }
    )

    response_error = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'detail': openapi.Schema(
                type=openapi.TYPE_STRING)
        }
    )

    parameters_list = [
        openapi.Parameter("offset", openapi.IN_QUERY, type=openapi.TYPE_NUMBER),
        openapi.Parameter("limit", openapi.IN_QUERY, type=openapi.TYPE_NUMBER),
        openapi.Parameter("filter", openapi.IN_QUERY, type=openapi.TYPE_STRING)
    ]

    @swagger_auto_schema(operation_description="Get logs.", responses={200: response_ok, 500: response_error},
                         manual_parameters=parameters_list)
    def list(self, request):
        filter_param = request.query_params.get("filter")
        try:
            offset = int(request.query_params.get("offset", 0))
            limit = int(request.query_params.get("limit", 0))
        except ValueError:
            raise exceptions.ApiWrongFormat()

        try:
            all_logs = util.get_logs()
        except (IOError, Exception) as ex:
            raise exceptions.ApiInternalError(str(ex))

        if filter_param is not None:
            filtered_logs = []
            for log in all_logs:
                if filter_param in log:
                    filtered_logs.append(log)
        else:
            filtered_logs = all_logs

        filtered_logs_count = len(filtered_logs)
        if limit > 0 or offset > 0:
            logs_to_show = filtered_logs[offset:offset + limit if limit > 0 else filtered_logs_count]
        else:
            logs_to_show = filtered_logs

        msg = {"count": filtered_logs_count, "results": logs_to_show}
        return Response(msg, status=status.HTTP_200_OK)
