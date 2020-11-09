from cryton.lib import exceptions


# states
PENDING = 'PENDING'
SCHEDULED = 'SCHEDULED'
RUNNING = 'RUNNING'
PAUSING = 'PAUSING'
PAUSED = 'PAUSED'
FINISHED = 'FINISHED'
IGNORE = 'IGNORE'
UP = 'UP'
DOWN = 'DOWN'
ERROR = 'ERROR'

# Final states
STEP_FINAL_STATES = [FINISHED, IGNORE, ERROR]
STAGE_FINAL_STATES = [FINISHED]
PLAN_FINAL_STATES = [FINISHED]

# Worker related
SLAVE_STATES = [
    UP, DOWN
]

SLAVE_TRANSITIONS = [
    (UP, DOWN), (DOWN, UP)
]


# Run related
RUN_STATES = [
    PENDING, SCHEDULED, RUNNING, FINISHED, PAUSED, PAUSING
]

RUN_TRANSITIONS = [
    (PENDING, SCHEDULED), (SCHEDULED, PENDING), (PENDING, RUNNING), (SCHEDULED, RUNNING),
    (RUNNING, PAUSING), (PAUSING, PAUSED), (PAUSED, RUNNING), (RUNNING, FINISHED)
]

RUN_PREPARE_STATES = [PENDING]
RUN_SCHEDULE_STATES = [PENDING]
RUN_UNSCHEDULE_STATES = [SCHEDULED]
RUN_RESCHEDULE_STATES = [SCHEDULED]
RUN_POSTPONE_STATES = [SCHEDULED]
RUN_EXECUTE_STATES = [PENDING, SCHEDULED]
RUN_PAUSE_STATES = [RUNNING]
RUN_UNPAUSE_STATES = [PAUSED]
RUN_EXECUTE_REST_STATES = [PENDING]


# Plan and PlanExecution related
PLAN_STATES = [
    PENDING, SCHEDULED, RUNNING, FINISHED, PAUSING, PAUSED
]

PLAN_TRANSITIONS = [
    (PENDING, SCHEDULED), (PENDING, RUNNING), (SCHEDULED, PENDING), (SCHEDULED, RUNNING), (RUNNING, FINISHED),
    (RUNNING, PAUSING), (PAUSING, PAUSED), (PAUSED, RUNNING)
]

PLAN_SCHEDULE_STATES = [PENDING]
PLAN_EXECUTE_STATES = [PENDING]
PLAN_UNSCHEDULE_STATES = [SCHEDULED]
PLAN_RESCHEDULE_STATES = [SCHEDULED]
PLAN_POSTPONE_STATES = [SCHEDULED]
PLAN_PAUSE_STATES = [RUNNING]
PLAN_UNPAUSE_STATES = [PAUSED]


# Stage and StageExecution related
STAGE_STATES = [
    PENDING, RUNNING, FINISHED, PAUSING, PAUSED
]

STAGE_TRANSITIONS = [
    (PENDING, RUNNING), (RUNNING, FINISHED), (RUNNING, PAUSING), (PAUSING, PAUSED), (PAUSED, RUNNING),
    (PAUSING, FINISHED)
]

STAGE_EXECUTE_STATES = [PENDING, PAUSED]
STAGE_SCHEDULE_STATES = [PENDING]
STAGE_UNSCHEDULE_STATES = [PENDING, PAUSED]
STAGE_PAUSE_STATES = [RUNNING]
STAGE_UNPAUSE_STATES = [PAUSED]

# Step and StepExecution related
STEP_STATES = [
    PENDING, RUNNING, FINISHED, IGNORE, PAUSED
]

STEP_TRANSITIONS = [
    (PENDING, RUNNING), (PENDING, IGNORE), (RUNNING, FINISHED), (RUNNING, ERROR), (PENDING, ERROR),
    (PENDING, PAUSED), (PAUSED, RUNNING)
]

STEP_EXECUTE_STATES = [PENDING, PAUSED]


# Successor related
VALID_SUCCESSOR_STATES = [FINISHED]


WORKER_STATES = [UP, DOWN, ERROR]


class StateMachine:
    """Base state machine"""
    def __init__(self, execution_id: int, valid_states: list, valid_transitions: list):
        """
        :param valid_states: list of valid states that can be used for transitions
        :param valid_transitions: list of valid transitions that can be made
        """
        self.execution_id = execution_id
        self.valid_states: list = valid_states
        self.valid_transitions: list = valid_transitions

    def check_transition_validity(self, state_from: str, state_to: str) -> bool:
        """
        Check if the transition is valid
        :param state_from: from what state will be the transition made
        :param state_to: to what state will be the transition made
        :raises:
            InvalidStateError
            StateTransitionError
        :return: True if transition is valid, False if transition is duplicate
        """
        if state_from not in self.valid_states:
            raise exceptions.InvalidStateError(
                'Invalid state {}!'.format(state_from), self.execution_id, state_from, self.valid_states
            )
        if state_to not in self.valid_states:
            raise exceptions.InvalidStateError(
                'Invalid state {}!'.format(state_to), self.execution_id, state_to, self.valid_states
            )
        if state_from == state_to:
            return False

        if (state_from, state_to) not in self.valid_transitions:
            raise exceptions.StateTransitionError(
                'Invalid state transition from {} to {}!'.format(state_from, state_to), self.execution_id, state_from,
                state_to, self.valid_transitions
            )

        return True

    def check_valid_state(self, state, valid_states):
        """
        Check if the state is in valid states, if valid_states are empty don't check
        :param state: state to check
        :param valid_states: list of valid states
        :raises:
            InvalidStateError
        :return: None
        """
        if valid_states and state not in valid_states:
            raise exceptions.InvalidStateError(
                "Desired action cannot be performed due to incorrect state.", self.execution_id, state, valid_states
            )

        return None


class RunStateMachine(StateMachine):
    """Run state machine"""
    def __init__(self, execution_id: int):
        super().__init__(execution_id, RUN_STATES, RUN_TRANSITIONS)

    def validate_transition(self, state_from: str, state_to: str) -> bool:
        """
        Check if the transition is valid
        :param state_from: from what state will be the transition made
        :param state_to: to what state will be the transition made
        :raises:
            RunStateTransitionError
            RunInvalidStateError
        :return: True if transition is valid, False if transition is duplicate
        """
        try:
            return self.check_transition_validity(state_from, state_to)
        except exceptions.StateTransitionError as e:
            raise exceptions.RunStateTransitionError(
                e.message.get('message'), self.execution_id, state_from, state_to, RUN_TRANSITIONS
            )
        except exceptions.InvalidStateError as e:
            raise exceptions.RunInvalidStateError(
                e.message.get('message'), self.execution_id, e.message.get('state'), RUN_STATES
            )

    def validate_state(self, state: str, valid_states: list) -> None:
        """
        Check if the state is in valid states, if valid_states are empty don't check
        :param state: state to check
        :param valid_states: list of valid states
        :raises:
            RunInvalidStateError
        :return: None
        """
        try:
            return self.check_valid_state(state, valid_states)
        except exceptions.InvalidStateError:
            raise exceptions.RunInvalidStateError(
                "Desired action cannot be performed due to Run's incorrect state.", self.execution_id, state,
                valid_states
            )


class PlanStateMachine(StateMachine):
    """Plan state machine"""
    def __init__(self, execution_id: int):
        super().__init__(execution_id, PLAN_STATES, PLAN_TRANSITIONS)

    def validate_transition(self, state_from: str, state_to: str) -> bool:
        """
        Check if the transition is valid
        :param state_from: from what state will be the transition made
        :param state_to: to what state will be the transition made
        :raises:
            PlanStateTransitionError
            PlanInvalidStateError
        :return: True if transition is valid, False if transition is duplicate
        """
        try:
            return self.check_transition_validity(state_from, state_to)
        except exceptions.StateTransitionError as e:
            raise exceptions.PlanStateTransitionError(
                e.message.get('message'), self.execution_id, state_from, state_to, PLAN_TRANSITIONS
            )
        except exceptions.InvalidStateError as e:
            raise exceptions.PlanInvalidStateError(
                e.message.get('message'), self.execution_id, e.message.get('state'), PLAN_STATES
            )

    def validate_state(self, state: str, valid_states: list) -> None:
        """
        Check if the state is in valid states, if valid_states are empty don't check
        :param state: state to check
        :param valid_states: list of valid states
        :raises:
            PlanInvalidStateError
        :return: None
        """
        try:
            return self.check_valid_state(state, valid_states)
        except exceptions.InvalidStateError:
            raise exceptions.PlanInvalidStateError(
                "Desired action cannot be performed due to PlanExecution's incorrect state.", self.execution_id, state,
                valid_states
            )


class StageStateMachine(StateMachine):
    """Stage state machine"""
    def __init__(self, execution_id: int):
        super().__init__(execution_id, STAGE_STATES, STAGE_TRANSITIONS)

    def validate_transition(self, state_from: str, state_to: str) -> bool:
        """
        Check if the transition is valid
        :param state_from: from what state will be the transition made
        :param state_to: to what state will be the transition made
        :raises:
            StageStateTransitionError
            StageInvalidStateError
        :return: True if transition is valid, False if transition is duplicate
        """
        try:
            return self.check_transition_validity(state_from, state_to)
        except exceptions.StateTransitionError as e:
            raise exceptions.StageStateTransitionError(
                e.message.get('message'), self.execution_id, state_from, state_to, STAGE_TRANSITIONS
            )
        except exceptions.InvalidStateError as e:
            raise exceptions.StageInvalidStateError(
                e.message.get('message'), self.execution_id, e.message.get('state'), STAGE_STATES
            )

    def validate_state(self, state: str, valid_states: list) -> None:
        """
        Check if the state is in valid states, if valid_states are empty don't check
        :param state: state to check
        :param valid_states: list of valid states
        :raises:
            StageInvalidStateError
        :return: None
        """
        try:
            return self.check_valid_state(state, valid_states)
        except exceptions.InvalidStateError:
            raise exceptions.StageInvalidStateError(
                "Desired action cannot be performed due to StageExecution's incorrect state.", self.execution_id, state,
                valid_states
            )


class StepStateMachine(StateMachine):
    """Step state machine"""
    def __init__(self, execution_id: int):
        super().__init__(execution_id, STEP_STATES, STEP_TRANSITIONS)

    def validate_transition(self, state_from: str, state_to: str) -> bool:
        """
        Check if the transition is valid
        :param state_from: from what state will be the transition made
        :param state_to: to what state will be the transition made
        :raises:
            StepStateTransitionError
            StepInvalidStateError
        :return: True if transition is valid, False if transition is duplicate
        """
        try:
            return self.check_transition_validity(state_from, state_to)
        except exceptions.StateTransitionError as e:
            raise exceptions.StepStateTransitionError(
                e.message.get('message'), self.execution_id, state_from, state_to, STEP_TRANSITIONS
            )
        except exceptions.InvalidStateError as e:
            raise exceptions.StepInvalidStateError(
                e.message.get('message'), self.execution_id, e.message.get('state'), STEP_STATES
            )

    def validate_state(self, state: str, valid_states: list) -> None:
        """
        Check if the state is in valid states, if valid_states are empty don't check
        :param state: state to check
        :param valid_states: list of valid states
        :raises:
            StepInvalidStateError
        :return: None
        """
        try:
            return self.check_valid_state(state, valid_states)
        except exceptions.InvalidStateError:
            raise exceptions.StepInvalidStateError(
                "Desired action cannot be performed due to StepExecution's incorrect state.", self.execution_id, state,
                valid_states
            )
