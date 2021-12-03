# results
RESULT_OK = 'OK'
RESULT_FAIL = 'FAIL'
RESULT_EXCEPTION = 'EXCEPTION'
RESULT_UNKNOWN = 'UNKNOWN'
RESULT_TERMINATED = 'TERMINATED'

# return codes
CODE_OK = 0
CODE_FAIL = -1
CODE_EXCEPTION = -2
CODE_TERMINATED = -3

# types
RETURN_CODE = 'return_code'
RETURN_VALUE = 'return_value'
STATE = 'state'
RESULT = 'result'
STD_OUT = 'std_out'
STD_ERR = 'std_err'
MOD_OUT = 'mod_out'
MOD_ERR = 'mod_err'
ANY = 'any'

# Types with allowed regex
REGEX_TYPES = [STD_OUT, STD_ERR, MOD_OUT, MOD_ERR]

# Step main args
ARGUMENTS = 'arguments'
STEP_TYPE = 'step_type'

# Arguments for step type execute-on-worker
ATTACK_MODULE = 'attack_module'
ATTACK_MODULE_ARGS = 'attack_module_args'
SSH_CONNECTION = 'ssh_connection'

# Arguments for step type deploy-agent
STAGER_ARGUMENTS = 'stager_arguments'
STAGER_LISTENER_NAME = 'listener_name'
STAGER_LISTENER_PORT = 'listener_port'
STAGER_LISTENER_OPTIONS = 'listener_options'
STAGER_TYPE = 'stager_type'
STAGER_OPTIONS = 'stager_options'
AGENT_NAME = 'agent_name'

# Arguments for step type execute-on-agent
USE_AGENT = 'use_agent'
EMPIRE_MODULE = 'empire_module'
EMPIRE_MODULE_ARGS = 'empire_module_args'
EMPIRE_SHELL_COMMAND = 'shell_command'

# Session system keywords
SESSION_ID = 'session_id'
CREATE_NAMED_SESSION = 'create_named_session'
USE_NAMED_SESSION = 'use_named_session'
USE_ANY_SESSION_TO_TARGET = 'use_any_session_to_target'

# Step types
STEP_TYPE_EXECUTE_ON_WORKER = 'cryton/execute-on-worker'
STEP_TYPE_DEPLOY_AGENT = 'empire/deploy-agent'
STEP_TYPE_EXECUTE_ON_AGENT = 'empire/execute-on-agent'

# Step ret
RET_SESSION_ID = SESSION_ID
RET_FILE = 'file'
RET_FILE_NAME = 'file_name'
RET_FILE_CONTENT = 'file_content'
EVIDENCE_FILE = 'evidence_file'

# Stage trigger types
DELTA = 'delta'
HTTP_LISTENER = 'HTTPListener'
MSF_LISTENER = 'MSFListener'

# Step related
RET_CODE_ENUM = {
    CODE_OK: RESULT_OK,
    CODE_FAIL: RESULT_FAIL,
    CODE_EXCEPTION: RESULT_EXCEPTION,
    CODE_TERMINATED: RESULT_TERMINATED
}

# Successor related
VALID_SUCCESSOR_TYPES = [STATE, RESULT, ANY, STD_OUT, STD_ERR, MOD_OUT, MOD_ERR]
VALID_SUCCESSOR_RESULTS = [RESULT_OK, RESULT_FAIL, RESULT_EXCEPTION, RESULT_TERMINATED]

# Queue types
Q_ATTACK = 'attack'
Q_CONTROL = 'control'

# RabbitMQ message keywords
EVENT_T = "event_t"
EVENT_V = "event_v"
ACK_QUEUE = "ack_queue"
REPLY_TO = "reply_to"

# Other contants
PAUSE = 'PAUSE'
STATUS_OK = 'success'
EVENT_ACTION = 'action'
TRIGGER_TYPE = "trigger_type"
TRIGGER_ID = "trigger_id"

# Worker event types
EVENT_VALIDATE_MODULE = "VALIDATE_MODULE"
EVENT_LIST_MODULES = "LIST_MODULES"
EVENT_LIST_SESSIONS = "LIST_SESSIONS"
EVENT_KILL_STEP_EXECUTION = "KILL_STEP_EXECUTION"
EVENT_HEALTH_CHECK = "HEALTH_CHECK"
EVENT_START_TRIGGER = "START_TRIGGER"
EVENT_STOP_TRIGGER = "STOP_TRIGGER"
EVENT_TRIGGER_STAGE = "TRIGGER_STAGE"

# Scheduler
SCHEDULER = 'SCHEDULER'
ADD_REPEATING_JOB = 'add_repeating_job'
ADD_JOB = 'add_job'
REMOVE_JOB = 'remove_job'
RESUME_SCHEDULER = 'resume_scheduler'
PAUSE_SCHEDULER = 'pause_scheduler'
GET_JOBS = 'get_jobs'
RESUME_JOB = 'resume_job'
PAUSE_JOB = 'pause_job'
RESCHEDULE_JOB = 'reschedule_job'

# Datetime formats
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TIME_FORMAT_DETAILED = "%Y-%m-%dT%H:%M:%S.%fZ"
