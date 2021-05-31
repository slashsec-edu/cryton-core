import os

CRYTON_DIR = os.path.expanduser('/etc/cryton/')
CRYTON_CONFIG_PATH = os.getenv('CRYTON_CONFIG', '{}/config.ini'.format(CRYTON_DIR))
TIME_ZONE = os.getenv('CRYTON_TZ', 'Etc/UTC')

# Environment variables
LOGGER = os.getenv('CRYTON_LOGGER', 'prod')  # debug, prod

DB_NAME = os.getenv('CRYTON_DB_NAME', 'cryton')
DB_USERNAME = os.getenv('CRYTON_DB_USERNAME', 'cryton')
DB_PASSWORD = os.getenv('CRYTON_DB_PASSWORD', 'cryton')
DB_HOST = os.getenv('CRYTON_DB_HOST', 'cryton_pgbouncer')

RABBIT_USERNAME = os.getenv('CRYTON_RABBIT_USERNAME', 'admin')
RABBIT_PASSWORD = os.getenv('CRYTON_RABBIT_PASSWORD', 'mypass')
RABBIT_SRV_ADDR = os.getenv('CRYTON_RABBIT_SRV_ADDR', 'cryton_rabbit')
RABBIT_SRV_PORT = int(os.getenv('CRYTON_RABBIT_SRV_PORT', '5672'))

Q_ATTACK_RESPONSE_NAME = os.getenv('Q_ATTACK_RESPONSE_NAME')
Q_CONTROL_RESPONSE_NAME = os.getenv('Q_CONTROL_RESPONSE_NAME')
Q_EVENT_RESPONSE_NAME = os.getenv('Q_EVENT_RESPONSE_NAME')
Q_CONTROL_REQUEST_NAME = os.getenv('Q_CONTROL_REQUEST_NAME')

API_ROOT_URL = 'cryton/api/v1/'

CRYTON_DIR = '~/.cryton/'
REPORT_DIR = CRYTON_DIR + "reports/"
EVIDENCE_DIR = CRYTON_DIR + "evidence/"
FILE_UPLOAD_DIR = 'uploads'

USE_PROCESS_POOL = False
MISFIRE_GRACE_TIME = 60

# available cores to the process
CRYTON_CPU_CORES = os.getenv('CRYTON_CORE_CPU_CORES', len(os.sched_getaffinity(0)))
CRYTON_CORE_EXECUTION_THREADS_PER_PROCESS = os.getenv('CRYTON_CORE_EXECUTION_THREADS_PER_PROCESS', 5)

CRYTON_RPC_TIMEOUT = int(os.getenv('CRYTON_RPC_TIMEOUT', 1200))
