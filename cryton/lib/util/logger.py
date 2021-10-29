import logging.config

import structlog
import yaml

from cryton.etc import config

"""
Default Cryton logger setup and configuration
"""

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

config_dict = {'version': 1,
               'disable_existing_loggers': False,
               'formatters': {'simple': {
                   'format': '%(asctime)s.%(msecs)03d %(levelname)s [%(thread)d] {%(module)s} [%(funcName)s] %(message)s, '}},
               'handlers': {
                   'console': {'class': 'logging.StreamHandler', 'level': 'DEBUG', 'formatter': 'simple',
                               'stream': 'ext://sys.stdout'},
                   'debug_logger': {'class': 'logging.handlers.RotatingFileHandler', 'level': 'DEBUG',
                                    'formatter': 'simple',
                                    'filename': config.LOG_FILE_PATH_DEBUG, 'maxBytes': 10485760, 'backupCount': 20,
                                    'encoding': 'utf8'},
                   'prod_logger': {'class': 'logging.handlers.RotatingFileHandler', 'level': 'DEBUG',
                                   'formatter': 'simple',
                                   'filename': config.LOG_FILE_PATH, 'maxBytes': 10485760, 'backupCount': 20,
                                   'encoding': 'utf8'}},
               'root': {'level': 'NOTSET', 'handlers': ['console'], 'propogate': True},
               'loggers': {
                   'cryton': {'level': 'INFO', 'handlers': ['prod_logger', 'console'], 'propagate': False},
                   'cryton-debug': {'level': 'DEBUG', 'handlers': ['debug_logger', 'console'],
                                    'propagate': True},
                   'cryton-test': {'level': 'INFO', 'handlers': ['console'], 'propagate': True}}}

logging.config.dictConfig(config_dict)

if config.LOGGER == 'prod':
    logger = structlog.get_logger("cryton")
    logger.setLevel(logging.INFO)
else:
    logger = structlog.get_logger("cryton-debug")
    logger.setLevel(logging.DEBUG)
