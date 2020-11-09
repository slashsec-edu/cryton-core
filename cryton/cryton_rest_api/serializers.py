from rest_framework import serializers
from cryton.cryton_rest_api.models import (
    PlanModel,
    StageModel,
    StepModel,
    PlanExecutionModel,
    StageExecutionModel,
    StepExecutionModel,
    RunModel,
    WorkerModel,
    PlanTemplateFileModel,
    ExecutionVariableModel
)


class IdSerializer(serializers.HyperlinkedModelSerializer):
    id = serializers.ReadOnlyField()


class RunModelSerializer(IdSerializer):
    plan_executions = serializers.HyperlinkedRelatedField(many=True,
                                                          view_name='planexecutionmodel-detail',
                                                          read_only=True)

    class Meta:
        model = RunModel
        fields = '__all__'


class RunModelSerializerCreate(IdSerializer):

    workers = serializers.PrimaryKeyRelatedField(many=True, queryset=WorkerModel.objects.all())

    class Meta:
        model = RunModel
        fields = ('plan_model', 'workers')


class PlanModelSerializer(IdSerializer):
    runs = serializers.HyperlinkedRelatedField(many=True,
                                               view_name='runmodel-detail',
                                               read_only=True)
    stages = serializers.HyperlinkedRelatedField(many=True,
                                                 view_name='stagemodel-detail',
                                                 read_only=True)

    class Meta:
        model = PlanModel
        exclude = ('plan_dict',)


class StageModelSerializer(IdSerializer):
    steps = serializers.HyperlinkedRelatedField(many=True,
                                                view_name='stepmodel-detail',
                                                read_only=True)
    stage_executions = serializers.HyperlinkedRelatedField(many=True,
                                                           view_name='stageexecutionmodel-detail',
                                                           read_only=True)

    class Meta:
        model = StageModel
        fields = '__all__'


class StepModelSerializer(IdSerializer):
    step_executions = serializers.HyperlinkedRelatedField(many=True,
                                                          view_name='stepexecutionmodel-detail',
                                                          read_only=True)

    class Meta:
        model = StepModel
        fields = '__all__'


class StepModelSerializerCreate(IdSerializer):
    id = None

    class Meta:
        model = StepModel
        exclude = ('created_at', 'updated_at', 'url')


class StepModelSerializerCreateExcl(StepModelSerializerCreate):
    id = None

    class Meta:
        model = StepModel
        exclude = ('stage_model', 'created_at', 'updated_at', 'url')


class StageModelSerializerCreate(IdSerializer):
    steps = serializers.ListField(child=StepModelSerializerCreateExcl())
    id = None

    class Meta:
        model = StageModel
        exclude = ('created_at', 'updated_at', 'url')


class StageModelSerializerCreateExcl(StageModelSerializerCreate):
    id = None

    class Meta:
        model = StageModel
        exclude = ('plan_model', 'created_at', 'updated_at', 'url')


class PlanModelSerializerCreate(IdSerializer):

    plan_template = serializers.PrimaryKeyRelatedField(many=False, queryset=PlanTemplateFileModel.objects.all())

    class Meta:
        model = PlanModel
        fields = ('plan_template',)


class WorkerModelSerializer(IdSerializer):
    class Meta:
        model = WorkerModel
        fields = '__all__'


class WorkerModelSerializerCreate(IdSerializer):
    id = None

    class Meta:
        model = WorkerModel
        fields = ('name', 'address', 'state', 'q_prefix')


class ExecutionModelSerializer(IdSerializer):
    class Meta:
        fields = '__all__'


class PlanExecutionModelSerializer(ExecutionModelSerializer):
    class Meta:
        model = PlanExecutionModel
        fields = '__all__'


class StageExecutionModelSerializer(ExecutionModelSerializer):
    class Meta:
        model = StageExecutionModel
        fields = '__all__'


class StepExecutionModelSerializer(ExecutionModelSerializer):
    class Meta:
        model = StepExecutionModel
        fields = '__all__'


class PlanTemplateFileSerializer(IdSerializer):

    class Meta:
        model = PlanTemplateFileModel
        fields = '__all__'


class PlanTemplateFileSerializerCreate(IdSerializer):

    file = serializers.FileField()

    class Meta:
        model = PlanTemplateFileModel
        fields = '__all__'


class ExecutionVariableSerializer(IdSerializer):

    class Meta:
        model = ExecutionVariableModel
        fields = '__all__'
