from datetime import datetime
import pytz

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ProcessPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from cryton.etc import config
from cryton.lib.util import logger

SCHED_MAX_THREADS = 20
SCHED_MAX_PROCESSES = 5
JOB_MAX_INSTANCES = 3


class SchedulerService:

    def __init__(self):

        db_url = f"postgresql://{config.DB_USERNAME}:{config.DB_PASSWORD}@{config.DB_HOST}/{config.DB_NAME}"
        jobstores = {
            'default': SQLAlchemyJobStore(url=db_url)
        }
        executors = {
            'default': {'type': 'threadpool', 'max_workers': SCHED_MAX_THREADS},
            'processpool': ProcessPoolExecutor(max_workers=SCHED_MAX_PROCESSES)
        }
        job_defaults = {
            'coalesce': False,
            'max_instances': JOB_MAX_INSTANCES
        }
        self.scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults,
                                             timezone=pytz.timezone(config.TIME_ZONE))
        self.scheduler.start()
        self.state = 'RUNNING'

    def __del__(self):
        logger.logger.debug("SCHEDULER DELETED", scheduler=self.scheduler.state)

    def exposed_add_job(self, execute_function: str, function_args: list, start_time: datetime) -> str:
        """

        :param execute_function: Function/method to be scheduled
        :param function_args: Function arguments
        :param start_time: Function start time
        :return: Scheduled job ID
        """
        logger.logger.debug("Scheduling job in scheduler service", execute_function=execute_function)
        job_scheduled = self.scheduler.add_job(
            execute_function, 'date', misfire_grace_time=config.MISFIRE_GRACE_TIME, run_date=str(start_time),
            args=function_args, max_instances=100
        )

        return job_scheduled.id

    def exposed_add_repeating_job(self, execute_function: str, seconds: int) -> str:
        """

        :param execute_function: Function/method to be scheduled
        :param seconds: Function interval in seconds
        :return: Scheduled job ID
        """
        logger.logger.debug("Scheduling repeating job in scheduler service", execute_function=execute_function)
        job_scheduled = self.scheduler.add_job(
            execute_function, 'interval', seconds=seconds
        )
        return job_scheduled.id

    def exposed_reschedule_job(self, job_id: str):
        logger.logger.debug("Rescheduling job in scheduler service", job_id=job_id)
        return self.scheduler.reschedule_job(job_id)

    def exposed_pause_job(self, job_id: str):
        logger.logger.debug("Pausing job in scheduler service", job_id=job_id)
        return self.scheduler.pause_job(job_id)

    def exposed_resume_job(self, job_id: str):
        logger.logger.debug("Resuming job in scheduler service", job_id=job_id)
        return self.scheduler.resume_job(job_id)

    def exposed_remove_job(self, job_id: str):
        logger.logger.debug("Removing job in scheduler service", job_id=job_id)
        return self.scheduler.remove_job(job_id)

    def exposed_get_job(self, job_id: str):
        logger.logger.debug("Getting job in scheduler service", job_id=job_id)
        return self.scheduler.get_job(job_id)

    def exposed_get_jobs(self):
        logger.logger.debug("Getting multiple jobs in scheduler service")
        return self.scheduler.get_jobs()

    def exposed_pause_scheduler(self):
        logger.logger.debug("Pausing scheduler service")
        return self.scheduler.pause()

    def exposed_resume_scheduler(self):
        logger.logger.debug("Resuming scheduler service")
        return self.scheduler.resume()

    def health_check(self):
        return 0
