from django.conf.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from cryton.cryton_rest_api import viewsets
from cryton.etc import config


router = DefaultRouter()

runs_router = router.register('runs', viewsets.RunViewSet)
plans_router = router.register('plans', viewsets.PlanViewSet)
plan_exec_router = router.register('plan_executions', viewsets.PlanExecutionViewSet)
stages_router = router.register('stages', viewsets.StageViewSet)
stage_exec_router = router.register('stage_executions', viewsets.StageExecutionViewSet)
steps_router = router.register('steps', viewsets.StepViewSet)
step_exec_router = router.register('step_executions', viewsets.StepExecutionViewset)
workers_router = router.register('workers', viewsets.WorkerViewset)
template_router = router.register('templates', viewsets.PlanTemplateViewset)
exec_vars_router = router.register('execution_variables', viewsets.ExecutionVariableViewset)
logs_router = router.register('logs', viewsets.LogViewSet, "log")

schema_view = get_schema_view(
    openapi.Info(
        title="Cryton REST API",
        default_version='v1',
        description="This document provides documentation of Cryton REST API endpoints.",
        contact=openapi.Contact(email="nutar@ics.muni.cz")
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('', router.get_api_root_view()),
    path(config.API_ROOT_URL, include(router.urls)),
    path('swagger.json', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger.yaml', schema_view.without_ui(cache_timeout=0), name='schema-yaml'),
    path('doc/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui')
]
