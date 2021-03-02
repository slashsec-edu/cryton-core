import configparser
import os

CRYTON_DIR = os.path.expanduser('/etc/cryton/')
CRYTON_CONFIG_PATH = os.getenv('CRYTON_CONFIG', '{}/config.ini'.format(CRYTON_DIR))
TIME_ZONE = 'Etc/UTC'

# Environment variables
DEBUG = True if os.getenv('CRYTON_DEBUG') == 'True' else False

DB_NAME = os.getenv('CRYTON_DB_NAME')
DB_USERNAME = os.getenv('CRYTON_DB_USERNAME')
DB_PASSWORD = os.getenv('CRYTON_DB_PASSWORD')
DB_HOST = os.getenv('CRYTON_DB_HOST')

LHOSTNAME = os.getenv('CRYTON_SCHEDULER_LHOSTNAME')
LPORT = int(os.getenv('CRYTON_SCHEDULER_LPORT'))

RABBIT_USERNAME = os.getenv('CRYTON_RABBIT_USERNAME')
RABBIT_PASSWORD = os.getenv('CRYTON_RABBIT_PASSWORD')
RABBIT_SRV_ADDR = os.getenv('CRYTON_RABBIT_SRV_ADDR')
RABBIT_SRV_PORT = int(os.getenv('CRYTON_RABBIT_SRV_PORT'))

Q_ATTACK_RESPONSE_NAME = os.getenv('Q_ATTACK_RESPONSE_NAME')
Q_CONTROL_RESPONSE_NAME = os.getenv('Q_CONTROL_RESPONSE_NAME')
Q_EVENT_RESPONSE_NAME = os.getenv('Q_EVENT_RESPONSE_NAME')

# Constants (in fact variables, but no need for changing)
config = configparser.ConfigParser(allow_no_value=True)
config.read(CRYTON_CONFIG_PATH)

API_ROOT_URL = config.get('CRYTON_REST_API', 'API_ROOT_URL')
LOG_CONFIG = config.get('LOGGING_CONFIG', 'LOG_CONFIG')

REPORT_DIR = os.path.expanduser(config.get('CRYTON', 'REPORT_DIR'))
EVIDENCE_DIR = os.path.expanduser(config.get('CRYTON', 'EVIDENCE_DIR'))
PERSISTENCE_DIR = os.path.expanduser(config.get('CRYTON', 'PERSISTENCE_DIR'))
FILE_UPLOAD_DIR = os.path.expanduser(config.get('CRYTON', 'FILE_UPLOAD_DIR'))

USE_PROCESS_POOL = config.getboolean('SCHEDULER', 'USE_PROCESS_POOL')
MISFIRE_GRACE_TIME = int(config.getint('SCHEDULER', 'MISFIRE_GRACE_TIME'))

# available cores to the process
CRYTON_CPU_CORES = os.getenv('CRYTON_CORE_CPU_CORES', len(os.sched_getaffinity(0)))
CRYTON_CORE_EXECUTION_THREADS_PER_PROCESS = os.getenv('CRYTON_CORE_EXECUTION_THREADS_PER_PROCESS', 5)

WORKER_HEALTHCHECK_TIMEOUT = int(os.getenv('CRYTON_WORKER_HEALTHCHECK_TIMEOUT', 1200))

