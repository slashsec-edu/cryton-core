from django.test import TestCase
from mock import patch, MagicMock, Mock
from dataclasses import asdict

from cryton.lib.util import constants, exceptions, logger, states
from cryton.lib.models import step, worker

from cryton.cryton_rest_api.models import (
    PlanModel,
    StageModel,
    StepModel,
    StepExecutionModel,
    StageExecutionModel,
    CorrelationEvent,
    ExecutionVariableModel,
    OutputMapping
)

import yaml
import os
from django.utils import timezone
from model_bakery import baker

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestStepBasic(TestCase):

    def setUp(self) -> None:
        self.plan_model = baker.make(PlanModel)
        self.stage_model = baker.make(StageModel, **{'executor': 'stage-executor'})

        step_args = {'name': 'test_step',
                     'step_type': 'cryton/execute-on-worker',
                     'stage_model_id': self.stage_model.id,
                     'is_init': True,
                     'executor': 'executor',
                     'arguments': {'attack_module': 'attack_module',
                                   'attack_module_args': {}}}
        self.step_obj = step.Step(**step_args)

    def test_step_init_delete(self):
        step_args = {'name': 'test_step',
                     'step_type': 'cryton/execute-on-worker',
                     'stage_model_id': self.stage_model.id,
                     'is_init': True,
                     'executor': 'executor',
                     'arguments': {}}
        step_obj = step.Step(**step_args)
        step_model_id = step_obj.model.id

        self.assertIsInstance(step_model_id, int)
        self.assertEqual(step_obj.executor, 'executor')

        step_obj.delete()
        with self.assertRaises(exceptions.StepObjectDoesNotExist):
            step.Step(step_model_id=step_model_id)

    def test_step_init_exec(self):
        step_args = {'name': 'test_step',
                     'step_type': 'cryton/execute-on-worker',
                     'stage_model_id': self.stage_model.id,
                     'is_init': True,
                     'executor': None,
                     'arguments': {}}
        step_obj = step.Step(**step_args)

        self.assertIsInstance(step_obj.model.id, int)
        self.assertEqual(step_obj.executor, 'stage-executor')

    def test_step_init_from_id(self):
        step_model = baker.make(StepModel)

        step.Step(step_model_id=step_model.id)

        with self.assertRaises(exceptions.StepObjectDoesNotExist):
            step.Step(step_model_id=int(step_model.id) + 1)

    def test_properties(self):
        step_args = {'name': 'test_step',
                     'step_type': 'cryton/execute-on-worker',
                     'stage_model_id': self.stage_model.id,
                     'is_init': True,
                     'executor': None,
                     'arguments': {}}
        step_obj = step.Step(**step_args)
        temp_stage_model = baker.make(StageModel)

        step_obj.stage_model_id = temp_stage_model.id
        self.assertEqual(step_obj.stage_model_id, temp_stage_model.id)

    def test_properties_arguments(self):
        step_args = step.StepArguments()
        self.step_obj.arguments = step_args
        self.assertEqual(self.step_obj.arguments, step_args)

    def test_properties_is_init(self):
        self.step_obj.is_init = False
        self.assertEqual(self.step_obj.is_init, False)

    def test_properties_is_final(self):
        self.step_obj.is_final = False
        self.assertEqual(self.step_obj.is_final, False)

    def test_properties_name(self):
        self.step_obj.name = 'some-name'
        self.assertEqual(self.step_obj.name, 'some-name')

    def test_properties_type(self):
        self.step_obj.step_type = 'some-type'
        self.assertEqual(self.step_obj.step_type, 'some-type')

    def test_properties_executor(self):
        self.step_obj.executor = 'executor_2'
        self.assertEqual(self.step_obj.executor, 'executor_2')

    def test_properties_successors(self):
        step_args = {'name': 'test_step_1',
                     'step_type': 'cryton/execute-on-worker',
                     'stage_model_id': self.stage_model.id,
                     'is_init': True,
                     'executor': None,
                     'arguments': {}}
        succ_step_args = {'name': 'test_step_2',
                          'step_type': 'cryton/execute-on-worker',
                          'stage_model_id': self.stage_model.id,
                          'is_init': True,
                          'executor': None,
                          'arguments': {}}
        step_obj = step.Step(**step_args)
        succ_step_obj = step.Step(**succ_step_args)
        step_obj.add_successor(succ_step_obj.model.id, successor_type='result', successor_value='OK')
        self.assertIsInstance(step_obj.successors, step.QuerySet)
        self.assertEqual(step_obj.successors[0].name, 'test_step_2')

    def test_step_init_from_file(self):
        f_in = open('{}/step.yaml'.format(TESTS_DIR))
        step_yaml = yaml.safe_load(f_in)
        step_yaml.update({'stage_model_id': self.stage_model.id})
        step_obj = step.Step(**step_yaml)

        self.assertIsInstance(step_obj.model.id, int)

    def test_step_delete(self):
        step_args = {'name': 'test_step',
                     'step_type': 'cryton/execute-on-worker',
                     'stage_model_id': self.stage_model.id,
                     'is_init': True,
                     'executor': None,
                     'arguments': {}}
        step_obj = step.Step(**step_args)

        step_id = step_obj.model.id
        step_obj.delete()
        with self.assertRaises(exceptions.StepObjectDoesNotExist):
            step.Step(step_model_id=step_id)

    def test_step_list(self):
        StepModel.objects.all().delete()
        step_args = {'name': 'test_step',
                     'step_type': 'cryton/execute-on-worker',
                     'stage_model_id': self.stage_model.id,
                     'is_init': True,
                     'executor': 'executor',
                     'arguments': {}}
        step.Step(**step_args)

        self.assertEqual(len(step.Step.filter()), 1)
        self.assertEqual(len(step.Step.filter(stage_model_id=-1)), 0)
        self.assertEqual(len(step.Step.filter(stage_model_id=self.stage_model.id)), 1)
        self.assertEqual(len(step.Step.filter(is_init=False)), 0)
        self.assertEqual(len(step.Step.filter(is_init=True)), 1)
        self.assertEqual(len(step.Step.filter(is_init=True, executor='executor')), 1)
        with self.assertRaises(exceptions.WrongParameterError):
            self.assertEqual(len(step.Step.filter(non_existent=False)), 0)

    def test_validate(self):
        f_in = open('{}/step.yaml'.format(TESTS_DIR))
        step_dict = yaml.safe_load(f_in)

        step.Step.validate(step_dict=step_dict)

        step_dict.pop('arguments')

        with self.assertRaises(exceptions.StepValidationError):
            step.Step.validate(step_dict=step_dict)

    def test_getter(self):
        f_in = open('{}/step.yaml'.format(TESTS_DIR))
        step_yaml = yaml.safe_load(f_in)
        step_yaml.update({'stage_model_id': self.stage_model.id})
        step_obj = step.Step(**step_yaml)

        self.assertEqual(step_obj.model.stage_model.id, self.stage_model.id)

    @patch('uuid.uuid4')
    @patch('cryton.lib.util.util.Rpc', MagicMock)
    def test_validate_modules(self, mock_uuid):
        mock_uuid.return_value.hex = 'random_string'
        step_execution_model = baker.make(StepExecutionModel, **{'step_model_id': self.step_obj.model.id})
        step_execution = step.StepExecution(step_execution_id=step_execution_model.id)
        resp = step_execution.validate_cryton_module()
        self.assertFalse(resp)


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestStepAdvanced(TestCase):

    def setUp(self) -> None:
        self.stage_model = baker.make(StageModel)

        self.f_in = open('{}/step.yaml'.format(TESTS_DIR))
        self.step_yaml = yaml.safe_load(self.f_in)
        self.f_in.seek(0)
        self.step_yaml.update({'stage_model_id': self.stage_model.id})
        self.step_obj = step.Step(**self.step_yaml)

        self.step_yaml_succ = yaml.safe_load(self.f_in)
        self.step_yaml_succ.update({'stage_model_id': self.stage_model.id})
        self.step_successor = step.Step(**self.step_yaml_succ)

        self.step_succ_1 = step.Step(**self.step_yaml)
        self.step_succ_2 = step.Step(**self.step_yaml)
        self.step_succ_3 = step.Step(**self.step_yaml)

    def test_add_successor(self):
        self.assertIsInstance(self.step_obj.add_successor(self.step_successor.model.id,
                                                          'result', 'OK'), int)

        with self.assertRaises(exceptions.InvalidSuccessorType):
            self.assertIsInstance(self.step_obj.add_successor(self.step_successor.model.id,
                                                              'bad type', 'OK'), int)

        with self.assertRaises(exceptions.InvalidSuccessorValue):
            self.assertIsInstance(self.step_obj.add_successor(self.step_successor.model.id,
                                                              'result', 'bad value'), int)

    def test_parents(self):
        self.step_obj.add_successor(self.step_successor.model.id, 'result', 'OK')
        self.assertEqual([self.step_obj.model], list(self.step_successor.parents))

    def test_successors(self):
        step_parent = step.Step(**self.step_yaml)
        step_parent.add_successor(self.step_obj.model.id, 'result', 'OK')
        self.assertEqual([self.step_obj.model], list(step_parent.successors))

    def test_get_successors(self):
        step_parent = step.Step(**self.step_yaml)
        step_parent.add_successor(self.step_obj.model.id, 'result', 'OK')
        stage_exec_obj = baker.make(StageExecutionModel)
        step_ex_obj = step.StepExecution(step_model_id=step_parent.model.id, stage_execution_id=stage_exec_obj.id)
        step_ex_obj.result = 'OK'
        successors = step_ex_obj.get_successors()
        self.assertEqual(len(successors), 1)

        step_ex_obj.result = 'FAIL'
        successors = step_ex_obj.get_successors()
        self.assertEqual(len(successors), 0)

    def test_get_regex_successors(self):
        step_parent = step.Step(**self.step_yaml)
        step_parent.add_successor(self.step_obj.model.id, 'std_out', 'r"test"')
        stage_exec_obj = baker.make(StageExecutionModel)
        step_ex_obj = step.StepExecution(step_model_id=step_parent.model.id, stage_execution_id=stage_exec_obj.id)
        step_ex_obj.std_out = 'protest'
        successors = step_ex_obj.get_regex_sucessors()

        self.assertEqual(len(successors), 1)

        step_ex_obj.std_out = 'prost'
        successors = step_ex_obj.get_regex_sucessors()
        self.assertEqual(len(successors), 0)

    def test_ignore(self):
        step_parent = step.Step(**self.step_yaml)
        step_parent.add_successor(self.step_obj.model.id, 'std_out', 'r"test"')
        stage_exec_obj = baker.make(StageExecutionModel)
        step_ex_obj_succ = step.StepExecution(step_model_id=self.step_obj.model.id,
                                              stage_execution_id=stage_exec_obj.id)
        step_ex_obj_par = step.StepExecution(step_model_id=step_parent.model.id,
                                             stage_execution_id=stage_exec_obj.id)

        step_ex_obj_par.ignore()

        self.assertEqual(step_ex_obj_par.state, states.IGNORED)
        self.assertEqual(step_ex_obj_succ.state, states.IGNORED)

    def test_ignore_adv(self):
        self.step_obj.add_successor(self.step_succ_1.model.id, 'std_out', 'r"test"')
        self.step_obj.add_successor(self.step_succ_2.model.id, 'result', constants.RESULT_OK)
        self.step_succ_1.add_successor(self.step_succ_3.model.id, 'result', constants.RESULT_OK)
        self.step_succ_2.add_successor(self.step_succ_3.model.id, 'result', constants.RESULT_OK)
        stage_exec_obj = baker.make(StageExecutionModel)

        step_ex_obj_par = step.StepExecution(step_model_id=self.step_obj.model.id,
                                             stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_1 = step.StepExecution(step_model_id=self.step_succ_1.model.id,
                                                stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_2 = step.StepExecution(step_model_id=self.step_succ_2.model.id,
                                                stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_3 = step.StepExecution(step_model_id=self.step_succ_3.model.id,
                                                stage_execution_id=stage_exec_obj.id)

        step_ex_obj_par.std_out = "test"
        step_ex_obj_succ_1.result = constants.RESULT_OK
        step_ex_obj_succ_2.ignore()

        self.assertNotEqual(step_ex_obj_succ_2.state, states.IGNORED)

        step_ex_obj_par.state = states.RUNNING
        step_ex_obj_par.state = states.FINISHED

        step_ex_obj_succ_2.ignore()

        self.assertEqual(step_ex_obj_succ_2.state, states.IGNORED)
        self.assertNotEqual(step_ex_obj_succ_3.state, states.IGNORED)

    def test_ignore_successors(self):
        self.step_obj.add_successor(self.step_succ_1.model.id, 'std_out', 'r"test"')
        self.step_obj.add_successor(self.step_succ_2.model.id, 'result', constants.RESULT_OK)
        self.step_succ_1.add_successor(self.step_succ_3.model.id, 'result', constants.RESULT_OK)
        self.step_succ_2.add_successor(self.step_succ_3.model.id, 'result', constants.RESULT_OK)
        stage_exec_obj = baker.make(StageExecutionModel)

        step_ex_obj_par = step.StepExecution(step_model_id=self.step_obj.model.id,
                                             stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_1 = step.StepExecution(step_model_id=self.step_succ_1.model.id,
                                                stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_2 = step.StepExecution(step_model_id=self.step_succ_2.model.id,
                                                stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_3 = step.StepExecution(step_model_id=self.step_succ_3.model.id,
                                                stage_execution_id=stage_exec_obj.id)

        step_ex_obj_par.std_out = "nope"
        step_ex_obj_par.result = constants.RESULT_FAIL
        step_ex_obj_par.state = states.RUNNING
        step_ex_obj_par.state = states.FINISHED
        step_ex_obj_par.ignore_successors()

        self.assertEqual(step_ex_obj_succ_1.state, states.IGNORED)
        self.assertEqual(step_ex_obj_succ_2.state, states.IGNORED)
        self.assertEqual(step_ex_obj_succ_3.state, states.IGNORED)

    @patch('cryton.lib.models.step.StepExecution.execute')
    def test_execute_successors(self, mock_execute):
        self.step_obj.add_successor(self.step_succ_1.model.id, 'std_out', 'r"test"')
        self.step_obj.add_successor(self.step_succ_2.model.id, 'result', constants.RESULT_OK)
        self.step_succ_1.add_successor(self.step_succ_3.model.id, 'result', constants.RESULT_OK)
        self.step_succ_2.add_successor(self.step_succ_3.model.id, 'result', constants.RESULT_OK)
        stage_exec_obj = baker.make(StageExecutionModel)

        step_ex_obj_par = step.StepExecution(step_model_id=self.step_obj.model.id,
                                             stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_1 = step.StepExecution(step_model_id=self.step_succ_1.model.id,
                                                stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_2 = step.StepExecution(step_model_id=self.step_succ_2.model.id,
                                                stage_execution_id=stage_exec_obj.id)
        step_ex_obj_succ_3 = step.StepExecution(step_model_id=self.step_succ_3.model.id,
                                                stage_execution_id=stage_exec_obj.id)

        step_ex_obj_par.std_out = "test"
        step_ex_obj_par.result = constants.RESULT_FAIL
        step_ex_obj_par.state = states.RUNNING
        step_ex_obj_par.state = states.FINISHED

        step_ex_obj_par.execute_successors()
        step_ex_obj_par.ignore_successors()

        mock_execute.assert_called_with()
        self.assertEqual(step_ex_obj_succ_2.state, states.IGNORED)
        self.assertEqual(step_ex_obj_succ_3.state, states.PENDING)


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch('cryton.lib.util.states.StepStateMachine.validate_transition', MagicMock())
@patch('cryton.lib.util.states.StepStateMachine.validate_state', MagicMock())
class TestStepExecution(TestCase):

    def setUp(self) -> None:
        self.stage_model = baker.make(StageModel)
        self.stage_execution = baker.make(StageExecutionModel)

        self.step_obj = baker.make(StepModel)
        step_exec_stats = {
            'step_model_id': self.step_obj.id,
            'stage_execution': self.stage_execution
        }

        self.step_exec_stats_obj = step.StepExecution(**step_exec_stats)

        self.step_args = {'name': 'test_step_1',
                          'step_type': 'cryton/execute-on-worker',
                          'stage_model_id': self.stage_model.id,
                          'is_init': True,
                          'executor': None,
                          'arguments': {}}

        self.succ_step_args = {'name': 'test_step_2',
                               'step_type': 'cryton/execute-on-worker',
                               'stage_model_id': self.stage_model.id,
                               'is_init': True,
                               'executor': None,
                               'arguments': {}}

    def test_init_delete(self):
        step_ex_args = {'step_model_id': self.step_obj.id,
                        'stage_execution': self.stage_execution}
        step_ex_obj = step.StepExecution(**step_ex_args)
        step_ex_model_id = step_ex_obj.model.id

        self.assertIsInstance(step_ex_model_id, int)

        step_ex_obj.delete()
        with self.assertRaises(exceptions.StepExecutionDoesNotExist):
            step.StepExecution(step_execution_id=step_ex_model_id)

    def test_properties_state(self):
        self.step_exec_stats_obj.state = 'test'
        self.assertEqual(self.step_exec_stats_obj.state, 'test')

    def test_properties_result(self):
        self.step_exec_stats_obj.result = 'result'
        self.assertEqual(self.step_exec_stats_obj.result, 'result')

    def test_properties_stdout(self):
        self.step_exec_stats_obj.std_out = '1'
        self.assertEqual(self.step_exec_stats_obj.std_out, '1')

    def test_properties_stderr(self):
        self.step_exec_stats_obj.std_err = '2'
        self.assertEqual(self.step_exec_stats_obj.std_err, '2')

    def test_properties_modout(self):
        self.step_exec_stats_obj.mod_out = '3'
        self.assertEqual(self.step_exec_stats_obj.mod_out, '3')

    def test_properties_moderr(self):
        self.step_exec_stats_obj.mod_err = '4'
        self.assertEqual(self.step_exec_stats_obj.mod_err, '4')

    def test_properties_evidence_file(self):
        self.step_exec_stats_obj.evidence_file = 'ev_f'
        self.assertEqual(self.step_exec_stats_obj.evidence_file, 'ev_f')

    def test_properties_start_time(self):
        cur_time = timezone.now()
        self.step_exec_stats_obj.start_time = cur_time
        self.assertEqual(self.step_exec_stats_obj.start_time, cur_time)

    def test_properties_finish_time(self):
        cur_time = timezone.now()
        self.step_exec_stats_obj.finish_time = cur_time
        self.assertEqual(self.step_exec_stats_obj.finish_time, cur_time)

    def test_filter(self):
        step_ex_list = step.StepExecution.filter(id=self.step_exec_stats_obj.model.id)
        self.assertIsInstance(step_ex_list, step.QuerySet)

        # all
        step_ex_list = step.StepExecution.filter()
        self.assertIsInstance(step_ex_list, step.QuerySet)

        # wrong field
        with self.assertRaises(exceptions.WrongParameterError):
            step.StepExecution.filter(non_ex_param='test')

    # @patch('cryton.lib.util.validate_step_obj.arguments.get(constants.ATTACK_MODULE_ARGS)')
    # def test_validate_step_obj.arguments.get(constants.ATTACK_MODULE_ARGS)(self, val_mock):
    #     val_mock.return_value = MagicMock(valid=True, reason='test')
    #
    #     val_result = self.step_exec_stats_obj.validate_step_obj.arguments.get(constants.ATTACK_MODULE_ARGS)()
    #     self.assertEqual(val_result, (True, 'test'))

    def test_step_init_from_id(self):
        step_exec_model = baker.make(StepExecutionModel, **{'stage_execution_id': self.stage_execution.id})

        step.StepExecution(step_execution_id=step_exec_model.id)

        with self.assertRaises(exceptions.StepExecutionDoesNotExist):
            step.StepExecution(step_execution_id=int(step_exec_model.id) + 1)

    def test_step_exec_stats_init(self):
        step_exec_stats = {
            'step_model_id': self.step_obj.id,
            'stage_execution': self.stage_execution
        }

        step_exec_stats_obj = StepExecutionModel.objects.create(**step_exec_stats)

        self.assertIsInstance(step_exec_stats_obj.id, int)
        pass

    def test_get_successors(self):
        step_obj = step.Step(**self.step_args)
        succ_step_obj = step.Step(**self.succ_step_args)
        step_obj.add_successor(succ_step_obj.model.id, successor_type='result', successor_value='OK')

        step_exec_stats = {
            'step_model_id': step_obj.model.id,
            'stage_execution': self.stage_execution
        }

        step_exec_stats_model = StepExecutionModel.objects.create(**step_exec_stats)
        step_exec_stats_obj = step.StepExecution(step_execution_id=step_exec_stats_model.id)
        step_exec_stats_obj.result = 'OK'

        self.assertEqual(step_exec_stats_obj.get_successors()[0].id, succ_step_obj.model.id)

    def test_get_successors_regex(self):
        step_obj = step.Step(**self.step_args)
        succ_step_obj = step.Step(**self.succ_step_args)
        step_obj.add_successor(succ_step_obj.model.id, successor_type='std_out', successor_value="r'(teststring*)'")

        step_exec_stats = {
            'step_model_id': step_obj.model.id,
            'stage_execution': self.stage_execution
        }

        step_exec_stats_model = StepExecutionModel.objects.create(**step_exec_stats)
        step_exec_stats_obj = step.StepExecution(step_execution_id=step_exec_stats_model.id)
        step_exec_stats_obj.std_out = "I contain the teststring"

        self.assertEqual(step_exec_stats_obj.get_successors()[0].id, succ_step_obj.model.id)

        step_exec_stats_obj.std_out = "I do not"

        self.assertEqual(len(step_exec_stats_obj.get_successors()), 0)

    @patch("cryton.lib.models.step.CorrelationEvent.objects.create", Mock())
    @patch('cryton.lib.util.util.Rpc.__enter__')
    def test__execute_attack_module(self, mock_rpc_enter):
        mock_rpc = Mock()
        mock_rpc.call.return_value = Mock(return_value=1)
        mock_rpc.correlation_id = "1"
        mock_rpc_enter.return_value = mock_rpc
        worker_model = baker.make(worker.WorkerModel)
        ret = self.step_exec_stats_obj._execute_step(Mock(), "test", {}, worker_model, "response_queue")
        self.assertEqual(ret, "1")


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch('cryton.lib.util.states.StepStateMachine.validate_transition', MagicMock())
@patch('cryton.lib.util.states.StepStateMachine.validate_state', MagicMock())
@patch('cryton.lib.models.session.set_msf_session_id', MagicMock())
@patch('time.sleep', MagicMock())
class TestStepExecute(TestCase):

    def setUp(self) -> None:
        self.mock_execute_attack_module = patch('cryton.lib.models.step.StepExecution._execute_step').start()
        self.mock_evidence_file = patch('cryton.lib.util.util.store_evidence_file').start()
        self.mock_get_msf_session = patch('cryton.lib.models.session.get_msf_session_id').start()
        self.mock_get_session_ids = patch('cryton.lib.models.session.get_session_ids').start()
        self.mock_step_init = patch('cryton.lib.models.step.Step')
        self.mock_step_init.start()

        self.mock_execute_attack_module.return_value = {constants.RETURN_CODE: 0, constants.STD_OUT: 'test'}

        self.stage_model = baker.make(StageModel)
        self.stage_execution = baker.make(StageExecutionModel)

        self.step_model_obj = baker.make(StepModel)
        step_exec_stats = {
            'step_model_id': self.step_model_obj.id,
            'stage_execution': self.stage_execution
        }

        self.step_exec_stats_obj = step.StepExecution(**step_exec_stats)
        self.addCleanup(patch.stopall)

    def tearDown(self) -> None:
        patch.stopall()

    def test_execute(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        self.mock_step_init.return_value = step.Step(step_model_id=self.step_model_obj.id)
        state_before = StepExecutionModel.objects.get(id=self.step_exec_stats_obj.model.id).state
        with self.assertLogs('cryton-debug', level='INFO') as cm:
            _ = self.step_exec_stats_obj.execute(rabbit_channel)
        state_after = self.step_exec_stats_obj.model.state
        # Just test if it bubbles through the function correctly
        self.assertEqual(state_before, 'PENDING')
        self.assertEqual(state_after, 'RUNNING')
        # self.assertEqual(self.step_exec_stats_obj.model.result, 'OK')
        self.assertIn("stepexecution executed", cm.output[0])

    @patch('cryton.lib.models.step.StepExecution._execute_step', MagicMock(side_effect=exceptions.RabbitConnectionError('test')))
    def test_execute_no_connection(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        self.mock_step_init.return_value = step.Step(step_model_id=self.step_model_obj.id)
        with self.assertLogs('cryton-debug', level='ERROR'), self.assertRaises(exceptions.RabbitConnectionError):
            _ = self.step_exec_stats_obj.execute(rabbit_channel)

    def test_execute_named_session(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        self.step_model_obj.arguments = {constants.ATTACK_MODULE_ARGS: {},
                                         constants.USE_NAMED_SESSION: 'test-session'}
        self.step_model_obj.save()
        with self.assertLogs('cryton-debug', level='INFO'):
            self.step_exec_stats_obj.execute(rabbit_channel)

    def test_execute_any_session(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        self.step_model_obj.arguments = {constants.ATTACK_MODULE_ARGS: {},
                                         constants.USE_ANY_SESSION_TO_TARGET: 'target'}
        self.step_model_obj.save()
        self.mock_get_session_ids.return_value = [1]
        with self.assertLogs('cryton-debug', level='INFO'):
            self.step_exec_stats_obj.execute(rabbit_channel)

    def test_execute_create_named_session(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        step_obj = step.Step(step_model_id=self.step_model_obj.id)
        step_obj.arguments = step.StepArguments(attack_module_args={}, create_named_session='named_session')
        self.mock_step_init.return_value = step_obj

        self.mock_execute_attack_module.return_value.update({constants.RET_SESSION_ID: 1,
                                                             constants.RETURN_CODE: -1})
        with self.assertLogs('cryton-debug', level='INFO'):
            self.step_exec_stats_obj.execute(rabbit_channel)

        self.mock_execute_attack_module.return_value = {constants.RETURN_CODE: -10}
        with self.assertLogs('cryton-debug', level='INFO'):
            self.step_exec_stats_obj.execute(rabbit_channel)

    def test_execute_evidence_file(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        self.mock_evidence_file.return_value = 'file_path'
        self.mock_execute_attack_module.return_value = {constants.RET_FILE: {constants.RET_FILE_NAME: 'name',
                                                                             constants.RET_FILE_CONTENT: 'contents'}}
        with self.assertLogs('cryton-debug', level='INFO'):
            self.step_exec_stats_obj.execute(rabbit_channel)

    def test_execute_use_named_session(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        mock_step_obj = step.Step(step_model_id=self.step_model_obj.id)
        mock_step_obj.arguments = step.StepArguments(use_named_session='test-session')
        self.mock_get_msf_session.return_value = None

        with self.assertLogs('cryton-debug', level='ERROR'), self.assertRaises(exceptions.SessionIsNotOpen):
            self.step_exec_stats_obj.execute(rabbit_channel)

    def test_execute_no_session_to_target(self):
        self.mock_step_init.stop()
        rabbit_channel = MagicMock()
        mock_step_obj = step.Step(step_model_id=self.step_model_obj.id)
        mock_step_obj.arguments = step.StepArguments(attack_module_args={}, use_any_session_to_target='target')

        self.mock_get_session_ids.return_value = [None]

        with self.assertLogs('cryton-debug', level='ERROR'), self.assertRaises(exceptions.SessionObjectDoesNotExist):
            self.step_exec_stats_obj.execute(rabbit_channel)

        self.mock_get_session_ids.return_value = []

        with self.assertLogs('cryton-debug', level='ERROR'), self.assertRaises(exceptions.SessionObjectDoesNotExist):
            self.step_exec_stats_obj.execute(rabbit_channel)

        self.mock_get_session_ids.return_value = [1]

        with self.assertLogs('cryton-debug', level='INFO'):
            self.step_exec_stats_obj.execute(rabbit_channel)

    @patch('cryton.lib.models.step.util.fill_template')
    def test_execute_fill_mod_args(self, mock_fill_template):
        rabbit_channel = MagicMock()
        mock_fill_template.return_value = '{"test": "test"}'
        self.mock_step_init.stop()
        mock_step_obj = step.Step(step_model_id=self.step_model_obj.id)
        mock_step_obj.arguments = step.StepArguments()
        mock_step_obj.step_type = constants.STEP_TYPE_EXECUTE_ON_WORKER
        step_ex = baker.make(StepExecutionModel, step_model=self.step_model_obj)
        baker.make(ExecutionVariableModel, name='test', value='test',
                   plan_execution_id=step_ex.stage_execution.plan_execution_id)
        step_ex_obj = step.StepExecution(step_execution_id=step_ex.id)

        step_ex_obj.execute(rabbit_channel)
        mock_fill_template.assert_called_once()

    # @patch('cryton.lib.models.step.util.execute_attack_module')
    # def test_execute_fail(self, mock_execute_attack_module):
    #     mock_execute_attack_module.return_value = {'return_code': -1}
    #     with self.assertLogs('cryton-debug', level='INFO') as cm:
    #         self.step_exec_stats_obj.execute()
    #     # Just test if it bubbles through the function correctly
    #     self.assertEqual(self.step_exec_stats_obj.model.result, 'FAIL')
    #     self.assertIn("stepexecution executed", cm.output[0])

    # @patch('cryton.lib.models.step.util.execute_attack_module')
    # def test_execute_output_values(self, mock_execute_attack_module):
    #     mock_execute_attack_module.return_value = {'return_code': 0,
    #                                                'std_out': 'test-out',
    #                                                'std_err': 'some-error',
    #                                                'mod_out': 'test-out',
    #                                                'mod_err': 'some-error',
    #                                                'evidence_file': '/file/path'}
    #     with self.assertLogs('cryton-debug', level='INFO'):
    #         self.step_exec_stats_obj.execute()
    #     # Just test if it bubbles through the function correctly
    #     self.assertEqual(self.step_exec_stats_obj.model.std_err, 'some-error')
    #     self.assertEqual(self.step_exec_stats_obj.model.std_out, 'test-out')
    #     self.assertEqual(self.step_exec_stats_obj.model.mod_out, 'test-out')
    #     self.assertEqual(self.step_exec_stats_obj.model.mod_err, 'some-error')
    #     self.assertEqual(self.step_exec_stats_obj.model.evidence_file, '/file/path')
    #
    # @patch('cryton.lib.models.step.util.execute_attack_module')
    # def test_execute_output(self, mock_execute_attack_module):
    #     mock_execute_attack_module.return_value = {'return_code': 0,
    #                                                constants.RET_SESSION_ID: '42'}
    #     step_obj = step.Step(step_model_id=self.step_model_obj.id)
    #     step_obj.create_named_session = 'named_session'
    #     self.mock_step_init.return_value = step_obj
    #     with self.assertLogs('cryton-debug', level='INFO'):
    #         self.step_exec_stats_obj.execute()
    #
    #     # get sessions
    #     sessions_id = SessionModel.objects.filter(plan_execution_id=
    #                                               self.step_exec_stats_obj.model.stage_execution.plan_execution_id,
    #                                               session_name='named_session').values('session_id')
    #
    #     self.assertNotEqual(len(sessions_id), 0)
    #
    #     self.assertEqual(sessions_id.last().get('session_id'), '42')

    def test_save_output(self):
        self.assertEqual(self.step_exec_stats_obj.save_output({'std_out': 0, 'std_err': 0}),
                         None)

    def test_save_output_with_mappings(self):
        output = {'std_out': 0, 'std_err': 0, 'mod_out': {'test': 1, 'best': 2}}
        OutputMapping.objects.create(step_model=self.step_model_obj, name_from='best', name_to='crest')
        self.step_exec_stats_obj.save_output(output)
        expected = {'test': 1, 'crest': 2}

        self.assertEqual(self.step_exec_stats_obj.mod_out, expected)

    def test_report(self):
        step_ex_model = baker.make(StepExecutionModel, **{'state': 'FINISHED',
                                                          'evidence_file': 'test_evidence_file'})
        step_execution = step.StepExecution(step_execution_id=step_ex_model.id)
        report_dict = step_execution.report()

        self.assertIsInstance(report_dict, dict)
        self.assertEqual(report_dict.get('evidence_file'), 'test_evidence_file')

    @patch('cryton.lib.models.step.StepExecution._execute_step')
    def test_mod_out_sharing_custom(self, mock_exec):
        rabbit_channel = MagicMock()
        self.mock_step_init.stop()
        successor_attack_args = step.StepArguments(attack_module_args={'password': 'root', 'test': 'username',
                                                                       'best': '$custom.out'})
        custom_mod_out = {'username': 'Jirka', 'password': 'passwd', 'out': 123}
        expected_result = {constants.ATTACK_MODULE_ARGS: {'password': 'root', 'test': 'username', 'best': 123}}

        # Bake models
        step_model = baker.make(StepModel, step_type=constants.STEP_TYPE_EXECUTE_ON_WORKER, stage_model=self.stage_model,
                                arguments=asdict(successor_attack_args))
        parent_model = baker.make(StepModel, step_type=constants.STEP_TYPE_EXECUTE_ON_WORKER, stage_model=self.stage_model,
                                  name='test', output_prefix='custom')
        # Create objects
        step_obj = step.Step(step_model_id=step_model.id)
        parent_obj = step.Step(step_model_id=parent_model.id)

        # Add successor
        parent_obj.add_successor(step_obj.model.id, successor_type='result', successor_value='OK')

        # Create execution
        step_exec = step.StepExecution(**{'step_model': step_model, 'stage_execution': self.stage_execution})

        # Create parent execution
        parent_step_exec_model = StepExecutionModel.objects.create(**{'step_model_id': parent_obj.model.id,
                                                                      'state': 'FINISHED',
                                                                      'stage_execution': self.stage_execution,
                                                                      'mod_out': custom_mod_out})
        parent_execution = step.StepExecution(step_execution_id=parent_step_exec_model.id)
        step_exec.parent_id = parent_execution.model.id

        step_exec.execute(rabbit_channel)
        mock_exec.assert_called_with(rabbit_channel, step_obj.step_type, expected_result,
                                     step_exec.model.stage_execution.plan_execution.worker, step_obj.model.executor)

    @patch('cryton.lib.models.step.StepExecution._execute_step')
    def test_mod_out_sharing_parent_and_custom(self, mock_exec):
        rabbit_channel = MagicMock()
        self.mock_step_init.stop()

        successor_attack_args = step.StepArguments(attack_module_args={'password': 'root', 'test': '$parent.username',
                                                                       'best': '$custom.out'})
        parent_mod_out = {'username': 'Jirka', 'password': 'passwd', 'out': 123}

        expected_result = {constants.ATTACK_MODULE_ARGS: {'password': 'root', 'test': 'Jirka', 'best': 123}}

        # Bake models
        step_model = baker.make(StepModel, stage_model=self.stage_model, step_type=constants.STEP_TYPE_EXECUTE_ON_WORKER,
                                arguments=asdict(successor_attack_args))
        parent_model = baker.make(StepModel, stage_model=self.stage_model, step_type=constants.STEP_TYPE_EXECUTE_ON_WORKER,
                                  name='test', output_prefix='custom')

        # Create objects
        step_obj = step.Step(step_model_id=step_model.id)
        parent_obj = step.Step(step_model_id=parent_model.id)

        # Add successor
        parent_obj.add_successor(step_obj.model.id, successor_type='result', successor_value='OK')

        # Create execution
        step_exec = step.StepExecution(**{'step_model': step_model, 'stage_execution': self.stage_execution})

        # Create parent execution
        parent_step_exec_model = StepExecutionModel.objects.create(**{'step_model_id': parent_obj.model.id,
                                                                      'state': 'FINISHED',
                                                                      'stage_execution': self.stage_execution,
                                                                      'mod_out': parent_mod_out})
        parent_execution = step.StepExecution(step_execution_id=parent_step_exec_model.id)
        step_exec.parent_id = parent_execution.model.id

        step_exec.execute(rabbit_channel)

        worker_obj = worker.Worker(worker_model_id=self.stage_execution.plan_execution.worker.id)
        mock_exec.assert_called_with(rabbit_channel, step_obj.step_type, expected_result,
                                     step_exec.model.stage_execution.plan_execution.worker, step_obj.model.executor)

    @patch('cryton.lib.util.util.Rpc.__enter__')
    def test_kill(self, mock_rpc):
        mock_call = Mock()
        mock_call.call = Mock(return_value={'event_v': {'return_code': 0}})
        mock_rpc.return_value = mock_call


        step_ex_model = baker.make(StepExecutionModel, **{'state': 'RUNNING'})
        step_ex = step.StepExecution(step_execution_id=step_ex_model.id)
        baker.make(CorrelationEvent, step_execution_id=step_ex_model.id)

        with self.assertLogs('cryton-debug', level='INFO'):
            ret = step_ex.kill()
        self.assertEqual(ret, {'return_code': 0})

    @patch("cryton.lib.models.stage.StepExecution.reset_execution_data", Mock())
    @patch("cryton.lib.models.stage.StepExecution.execute")
    def test_re_execute(self, mock_execute):
        step_ex_model = baker.make(StepExecutionModel, **{'state': 'TERMINATED'})
        step_ex = step.StepExecution(step_execution_id=step_ex_model.id)

        step_ex.re_execute()
        mock_execute.assert_called()

    def test_reset_execution_data(self):
        step_ex_model = baker.make(StepExecutionModel, **{'state': 'TERMINATED'})
        step_ex = step.StepExecution(step_execution_id=step_ex_model.id)

        step_ex.reset_execution_data()
        self.assertEqual(step_ex.state, "PENDING")

