from django.test import TestCase
from mock import patch
from cryton.lib import states, exceptions, logger


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestStates(TestCase):

    def test_base_state_machine_init(self):
        ret = states.StateMachine(1, ['TEST'], [('TEST', 'TEST')])
        self.assertIsInstance(ret, states.StateMachine)

    def test_check_transition_validity(self):
        machine = states.StateMachine(1, ['TEST', 'INVALID'], [('TEST', 'INVALID')])
        ret = machine.check_transition_validity('TEST', 'INVALID')
        self.assertTrue(ret)

    def test_check_transition_validity_invalid_state_from(self):
        machine = states.StateMachine(1, ['TEST'], [('TEST', 'TEST')])
        with self.assertRaises(exceptions.InvalidStateError):
            machine.check_transition_validity('INVALID', 'TEST')

    def test_check_transition_validity_invalid_state_to(self):
        machine = states.StateMachine(1, ['TEST'], [('TEST', 'TEST')])
        with self.assertRaises(exceptions.InvalidStateError):
            machine.check_transition_validity('TEST', 'INVALID')

    def test_check_transition_validity_duplicate_transition(self):
        machine = states.StateMachine(1, ['TEST'], [('TEST', 'INVALID')])
        ret = machine.check_transition_validity('TEST', 'TEST')
        self.assertFalse(ret)

    def test_check_transition_validity_invalid_transition(self):
        machine = states.StateMachine(1, ['TEST', 'INVALID'], [('TEST', 'INVALID')])
        with self.assertRaises(exceptions.StateTransitionError):
            machine.check_transition_validity('INVALID', 'TEST')

    def test_check_valid_state(self):
        state_list = ['TEST']
        machine = states.StateMachine(1, ['TEST'], [])
        self.assertIsNone(machine.check_valid_state('TEST', state_list))

    def test_check_valid_state_empty_list(self):
        state_list = []
        machine = states.StateMachine(1, ['TEST'], [])
        self.assertIsNone(machine.check_valid_state('TEST', state_list))

    def test_check_valid_state_invalid_state(self):
        state_list = ['TEST']
        machine = states.StateMachine(1, ['TEST'], [])
        with self.assertRaises(exceptions.InvalidStateError):
            machine.check_valid_state('INVALID', state_list)

    def test_run_state_machine_init(self):
        ret = states.RunStateMachine(1)
        self.assertIsInstance(ret, states.RunStateMachine)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_run_state_machine_validate_transition_valid(self, mock_check):
        mock_check.return_value = True
        machine = states.RunStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertTrue(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_run_state_machine_validate_transition_duplicate(self, mock_check):
        mock_check.return_value = False
        machine = states.RunStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertFalse(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_run_state_machine_validate_transition_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        machine = states.RunStateMachine(1)
        with self.assertRaises(exceptions.RunInvalidStateError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_run_state_machine_validate_transition_invalid_transition(self, mock_check):
        mock_check.side_effect = exceptions.StateTransitionError('', 1, '', '', [])
        machine = states.RunStateMachine(1)
        with self.assertRaises(exceptions.RunStateTransitionError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_run_state_machine_validate_state(self, mock_check):
        mock_check.return_value = None
        state_list = ['TEST']
        machine = states.RunStateMachine(1)
        self.assertIsNone(machine.validate_state('TEST', state_list))

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_run_state_machine_validate_state_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        state_list = ['TEST']
        machine = states.RunStateMachine(1)
        with self.assertRaises(exceptions.RunInvalidStateError):
            machine.validate_state('INVALID', state_list)

    def test_plan_state_machine_init(self):
        ret = states.PlanStateMachine(1)
        self.assertIsInstance(ret, states.PlanStateMachine)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_plan_state_machine_validate_transition_valid(self, mock_check):
        mock_check.return_value = True
        machine = states.PlanStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertTrue(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_plan_state_machine_validate_transition_duplicate(self, mock_check):
        mock_check.return_value = False
        machine = states.PlanStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertFalse(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_plan_state_machine_validate_transition_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        machine = states.PlanStateMachine(1)
        with self.assertRaises(exceptions.PlanInvalidStateError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_plan_state_machine_validate_transition_invalid_transition(self, mock_check):
        mock_check.side_effect = exceptions.StateTransitionError('', 1, '', '', [])
        machine = states.PlanStateMachine(1)
        with self.assertRaises(exceptions.PlanStateTransitionError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_plan_state_machine_validate_state(self, mock_check):
        mock_check.return_value = None
        state_list = ['TEST']
        machine = states.PlanStateMachine(1)
        self.assertIsNone(machine.validate_state('TEST', state_list))

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_plan_state_machine_validate_state_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        state_list = ['TEST']
        machine = states.PlanStateMachine(1)
        with self.assertRaises(exceptions.PlanInvalidStateError):
            machine.validate_state('INVALID', state_list)

    def test_stage_state_machine_init(self):
        ret = states.StageStateMachine(1)
        self.assertIsInstance(ret, states.StageStateMachine)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_stage_state_machine_validate_transition_valid(self, mock_check):
        mock_check.return_value = True
        machine = states.StageStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertTrue(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_stage_state_machine_validate_transition_duplicate(self, mock_check):
        mock_check.return_value = False
        machine = states.StageStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertFalse(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_stage_state_machine_validate_transition_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        machine = states.StageStateMachine(1)
        with self.assertRaises(exceptions.StageInvalidStateError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_stage_state_machine_validate_transition_invalid_transition(self, mock_check):
        mock_check.side_effect = exceptions.StateTransitionError('', 1, '', '', [])
        machine = states.StageStateMachine(1)
        with self.assertRaises(exceptions.StageStateTransitionError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_stage_state_machine_validate_state(self, mock_check):
        mock_check.return_value = None
        state_list = ['TEST']
        machine = states.StageStateMachine(1)
        self.assertIsNone(machine.validate_state('TEST', state_list))

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_stage_state_machine_validate_state_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        state_list = ['TEST']
        machine = states.StageStateMachine(1)
        with self.assertRaises(exceptions.StageInvalidStateError):
            machine.validate_state('INVALID', state_list)

    def test_step_state_machine_init(self):
        ret = states.StepStateMachine(1)
        self.assertIsInstance(ret, states.StepStateMachine)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_step_state_machine_validate_transition_valid(self, mock_check):
        mock_check.return_value = True
        machine = states.StepStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertTrue(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_step_state_machine_validate_transition_duplicate(self, mock_check):
        mock_check.return_value = False
        machine = states.StepStateMachine(1)
        ret = machine.validate_transition('TEST', 'TEST')
        self.assertFalse(ret)

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_step_state_machine_validate_transition_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        machine = states.StepStateMachine(1)
        with self.assertRaises(exceptions.StepInvalidStateError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_transition_validity')
    def test_step_state_machine_validate_transition_invalid_transition(self, mock_check):
        mock_check.side_effect = exceptions.StateTransitionError('', 1, '', '', [])
        machine = states.StepStateMachine(1)
        with self.assertRaises(exceptions.StepStateTransitionError):
            machine.validate_transition('TEST', 'TEST')

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_step_state_machine_validate_state(self, mock_check):
        mock_check.return_value = None
        state_list = ['TEST']
        machine = states.StepStateMachine(1)
        self.assertIsNone(machine.validate_state('TEST', state_list))

    @patch('cryton.lib.states.StateMachine.check_valid_state')
    def test_step_state_machine_validate_state_invalid_state(self, mock_check):
        mock_check.side_effect = exceptions.InvalidStateError('', 1, '', [])
        state_list = ['TEST']
        machine = states.StepStateMachine(1)
        with self.assertRaises(exceptions.StepInvalidStateError):
            machine.validate_state('INVALID', state_list)
