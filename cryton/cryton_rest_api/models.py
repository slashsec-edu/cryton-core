from django.db import models
from cryton.lib.util import constants as co, states as st

from cryton.etc import config


class AdvancedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TimeStampedModel(AdvancedModel):
    start_time = models.DateTimeField(blank=True, null=True)
    pause_time = models.DateTimeField(blank=True, null=True)
    finish_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        abstract = True


class InstanceModel(AdvancedModel):
    name = models.TextField()

    class Meta:
        abstract = True


class PlanModel(InstanceModel):
    owner = models.TextField(blank=True, null=True)
    evidence_dir = models.TextField(blank=True, null=True)
    plan_dict = models.JSONField()

    class Meta:
        db_table = 'plan_model'
        app_label = 'cryton_rest_api'


class StageModel(InstanceModel):
    plan_model = models.ForeignKey(PlanModel, on_delete=models.CASCADE, related_name='stages')
    executor = models.TextField(null=True, blank=True)
    trigger_type = models.TextField()
    trigger_args = models.JSONField()

    class Meta:
        db_table = 'stage_model'
        app_label = 'cryton_rest_api'


class StepModel(InstanceModel):
    stage_model = models.ForeignKey(StageModel, on_delete=models.CASCADE, related_name='steps')
    attack_module = models.TextField()
    attack_module_args = models.JSONField()
    is_init = models.BooleanField(default=False)
    is_final = models.BooleanField(default=False)
    executor = models.TextField(null=True, blank=True)
    # changed to step name or user specified prefix at creation time
    output_prefix = models.TextField(blank=False, default='')

    class Meta:
        db_table = 'step_model'
        app_label = 'cryton_rest_api'


class RunModel(TimeStampedModel):
    plan_model = models.ForeignKey(PlanModel, on_delete=models.CASCADE, related_name='runs')
    # PENDING, PREPARED, SCHEDULE etc
    state = models.TextField(default=st.PENDING)
    aps_job_id = models.TextField(default=None, null=True)
    schedule_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "run"
        app_label = "cryton_rest_api"


class WorkerModel(models.Model):
    name = models.TextField()
    address = models.TextField()
    q_prefix = models.TextField()
    state = models.TextField()


class ExecutionModel(TimeStampedModel):
    state = models.TextField(default=st.PENDING)

    class Meta:
        abstract = True


class PlanExecutionModel(ExecutionModel):
    run = models.ForeignKey(RunModel, on_delete=models.CASCADE, related_name='plan_executions')
    plan_model = models.ForeignKey(PlanModel, on_delete=models.CASCADE, related_name='plan_executions')
    worker = models.ForeignKey(WorkerModel, related_name='plan_executions', on_delete=models.PROTECT)
    aps_job_id = models.TextField(default=None, null=True)
    evidence_dir = models.TextField(blank=True, null=True)
    schedule_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'plan_execution'
        app_label = 'cryton_rest_api'


class StageExecutionModel(ExecutionModel):
    plan_execution = models.ForeignKey(PlanExecutionModel, on_delete=models.CASCADE, related_name='stage_executions')
    stage_model = models.ForeignKey(StageModel, on_delete=models.CASCADE, related_name='stage_executions')
    aps_job_id = models.TextField(default=None, null=True)
    schedule_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'stage_execution'
        app_label = 'cryton_rest_api'


class StepExecutionModel(ExecutionModel):
    stage_execution = models.ForeignKey(StageExecutionModel, on_delete=models.CASCADE, related_name='step_executions')
    step_model = models.ForeignKey(StepModel, on_delete=models.CASCADE, related_name='step_executions')
    result = models.TextField(default='NONE', blank=True, null=True)
    std_out = models.TextField(default='NONE', blank=True, null=True)
    std_err = models.TextField(default='NONE', blank=True, null=True)
    mod_out = models.JSONField(default=None, blank=True, null=True)
    mod_err = models.TextField(default='NONE', blank=True, null=True)
    evidence_file = models.TextField(default='NONE', blank=True, null=True)
    valid = models.BooleanField(default=False)
    parent_id = models.IntegerField(default=None, null=True)

    class Meta:
        db_table = 'step_execution'
        app_label = 'cryton_rest_api'


class SessionModel(models.Model):
    plan_execution = models.ForeignKey(PlanExecutionModel, on_delete=models.CASCADE, related_name='namedsessionmodel')
    session_name = models.TextField(null=True, blank=True, default=None)
    session_id = models.TextField(default='0')

    class Meta:
        db_table = 'namedsessionmodel'
        app_label = 'cryton_rest_api'


class SuccessorModel(models.Model):
    # success/value
    succ_type = models.TextField(default=co.RESULT)
    # success: OK/NOK (FAIL,EXCEPTION...)
    # value: return value of parent step
    succ_value = models.TextField(default=co.RESULT_OK)
    parent_step = models.ForeignKey(StepModel, related_name="successors", on_delete=models.CASCADE)
    successor_step = models.ForeignKey(StepModel, related_name="parents", on_delete=models.CASCADE)

    class Meta:
        db_table = 'successor'
        app_label = 'cryton_rest_api'


class CorrelationEvent(models.Model):
    correlation_id = models.TextField()
    # step_execution_id, plan_execution_id, run_id etc.
    step_execution = models.ForeignKey(StepExecutionModel, on_delete=models.CASCADE,
                                          related_name="correlation_events", null=True)
    worker_q_name = models.TextField(blank=True, null=True)
    state = models.TextField(default='PENDING')


class PlanTemplateFileModel(models.Model):
    file = models.FileField(upload_to=config.FILE_UPLOAD_DIR)


class ExecutionVariableModel(models.Model):
    plan_execution = models.ForeignKey(PlanExecutionModel, on_delete=models.CASCADE, related_name='execution_variables')
    name = models.TextField()
    value = models.TextField()


class OutputMapping(models.Model):
    step_model = models.ForeignKey(StepModel, on_delete=models.CASCADE, related_name='output_mappings')
    name_from = models.TextField()
    name_to = models.TextField()


class DependencyModel(models.Model):
    stage_model = models.ForeignKey(StageModel, related_name='dependencies', on_delete=models.CASCADE)
    dependency = models.ForeignKey(StageModel, related_name='subjects_to', on_delete=models.CASCADE)
