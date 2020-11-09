from datetime import datetime

import pytz
from rpyc.utils.server import ThreadedServer
import rpyc
from apscheduler.schedulers.background import BackgroundScheduler, BlockingScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from cryton.etc import config


class SchedulerService(rpyc.Service):

    def __init__(self, scheduler: BaseScheduler):
        self.scheduler = scheduler
        self.state = 'RUNNING'

    def exposed_add_job(self, execute_function: str, function_args: list, start_time: datetime) -> str:
        """

        :param execute_function: Function/method to be scheduled
        :param function_args: Function arguments
        :param start_time: Function start time
        :return: Scheduled job ID
        """
        job_scheduled = self.scheduler.add_job(
            execute_function, 'date', misfire_grace_time=config.MISFIRE_GRACE_TIME, run_date=str(start_time),
            args=function_args
        )
        return job_scheduled.id

    def exposed_add_repeating_job(self, execute_function: str, seconds: int) -> str:
        """

        :param execute_function: Function/method to be scheduled
        :param seconds: Function interval in seconds
        :return: Scheduled job ID
        """
        job_scheduled = self.scheduler.add_job(
            execute_function, 'interval', seconds=seconds
        )
        return job_scheduled.id

    def exposed_reschedule_job(self, job_id: str):
        return self.scheduler.reschedule_job(job_id)

    def exposed_pause_job(self, job_id: str):
        return self.scheduler.pause_job(job_id)

    def exposed_resume_job(self, job_id: str):
        return self.scheduler.resume_job(job_id)

    def exposed_remove_job(self, job_id: str):
        self.scheduler.remove_job(job_id)

    def exposed_get_job(self, job_id: str):
        return self.scheduler.get_job(job_id)

    def exposed_get_jobs(self):
        return self.scheduler.get_jobs()

    def exposed_pause_scheduler(self):
        return self.scheduler.pause()

    def exposed_resume_scheduler(self):
        return self.scheduler.resume()

    def health_check(self):
        return 0


# TODO make this non blocking and add blocking when using. Return scheduler object, so it can be shutdown outside.
def start_scheduler(blocking: bool = False):

    if not blocking:
        scheduler = BackgroundScheduler()
    else:
        scheduler = BlockingScheduler()
    scheduler.timezone = pytz.timezone(config.TIME_ZONE)
    db_url = f"postgresql://{config.DB_USERNAME}:{config.DB_PASSWORD}@{config.DB_HOST}/{config.DB_NAME}"
    jobstore = SQLAlchemyJobStore(db_url)
    scheduler.add_jobstore(jobstore)
    if config.USE_PROCESS_POOL:
        scheduler.add_executor('processpool')

    protocol_config = {'allow_public_attrs': True, 'allow_pickle': True}
    scheduler.start()
    server = ThreadedServer(SchedulerService(scheduler=scheduler), hostname=config.LHOSTNAME, port=config.LPORT,
                            protocol_config=protocol_config)
    try:
        print("Starting scheduler service. Listening on {}:{}".format(config.LHOSTNAME, config.LPORT))
        server.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
