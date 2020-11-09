# results
RESULT_OK = 'OK'
RESULT_FAIL = 'FAIL'
RESULT_EXCEPTION = 'EXCEPTION'
RESULT_UNKNOWN = 'UNKNOWN'


# return codes
CODE_OK = 0
CODE_FAIL = -1
CODE_EXCEPTION = -2


# types
RETURN_CODE = 'return_code'
STATE = 'state'
RESULT = 'result'
STD_OUT = 'std_out'
STD_ERR = 'std_err'
MOD_OUT = 'mod_out'
MOD_ERR = 'mod_err'
ANY = 'any'

# Types with allowed regex
REGEX_TYPES = [STD_OUT, STD_ERR, MOD_OUT, MOD_ERR]

# Step args
SESSION_ID = 'session_id'
ARGUMENTS = 'arguments'

# Step ret
RET_SESSION_ID = SESSION_ID
RET_FILE = 'file'
RET_FILE_NAME = 'file_name'
RET_FILE_CONTENTS = 'file_contents'
EVIDENCE_FILE = 'evidence_file'


# Stage trigger types
DELTA = 'delta'
HTTP_LISTENER = 'HTTPListener'


# Step related
RET_CODE_ENUM = {
    CODE_OK: RESULT_OK,
    CODE_FAIL: RESULT_FAIL,
    CODE_EXCEPTION: RESULT_EXCEPTION
}


# Successor related
VALID_SUCCESSOR_TYPES = [STATE, RESULT, ANY, STD_OUT, STD_ERR, MOD_OUT, MOD_ERR]
VALID_SUCCESSOR_RESULTS = [RESULT_OK, RESULT_FAIL, RESULT_EXCEPTION]

# Queue types
Q_ATTACK = 'attack'
Q_CONTROL = 'control'
