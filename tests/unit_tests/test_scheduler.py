from django.test import TestCase
from cryton.lib.services import scheduler
from cryton.lib.util import logger
from mock import patch, Mock
import os
import datetime


def run_null(*kwargs):
    return 0


mock_exc = Mock()
mock_exc.start.side_effect = run_null

devnull = open(os.devnull, 'w')


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch("sys.stdout", devnull)
@patch('cryton.lib.services.scheduler.config.MISFIRE_GRACE_TIME', 42)
class SchedulerTest(TestCase):

    def setUp(self) -> None:
        self.scheduler_obj = scheduler.SchedulerService()
        self.misfire = 42
        pass

    def test_exposed_add_job(self):
        mock_job = Mock()
        mock_job.id = '42'
        mock_add_job = Mock(return_value=mock_job)
        self.scheduler_obj.scheduler.add_job = mock_add_job

        fnc = Mock

        ret = self.scheduler_obj.exposed_add_job(fnc, [], datetime.datetime(3000, 3, 14, 15, 0))
        self.assertEqual(ret, '42')
        mock_add_job.assert_called_with(fnc, 'date', misfire_grace_time=self.misfire,
                                        run_date='3000-03-14 15:00:00', args=[], max_instances=100)

    def test_exposed_reschedule_job(self):

        mock_reschedule_job = Mock(return_value='42')
        self.scheduler_obj.scheduler.reschedule_job = mock_reschedule_job

        ret = self.scheduler_obj.exposed_reschedule_job('42')
        self.assertEqual(ret, '42')

    def test_exposed_pause_job(self):
        mock_pause_job = Mock(return_value='42')
        self.scheduler_obj.scheduler.pause_job = mock_pause_job

        ret = self.scheduler_obj.exposed_pause_job('42')
        self.assertEqual(ret, '42')
        
    def test_exposed_resume_job(self):
        mock_resume_job = Mock(return_value='42')
        self.scheduler_obj.scheduler.resume_job = mock_resume_job

        ret = self.scheduler_obj.exposed_resume_job('42')
        self.assertEqual(ret, '42')

    def test_exposed_remove_job(self):
        mock_remove_job = Mock(return_value=None)
        self.scheduler_obj.scheduler.remove_job = mock_remove_job

        ret = self.scheduler_obj.exposed_remove_job('42')
        self.assertEqual(ret, None)

        mock_remove_job.assert_called_with('42')

    def test_exposed_get_job(self):
        mock_get_job = Mock(return_value='666')
        self.scheduler_obj.scheduler.get_job = mock_get_job

        ret = self.scheduler_obj.exposed_get_job('666')
        self.assertEqual(ret, '666')

        mock_get_job.assert_called_with('666')

    def test_exposed_get_jobs(self):
        mock_get_jobs = Mock(return_value=["job1", "job2"])
        self.scheduler_obj.scheduler.get_jobs = mock_get_jobs

        ret = self.scheduler_obj.exposed_get_jobs()
        self.assertEqual(ret, ["job1", "job2"])

    def test_exposed_pause_scheduler(self):
        mock_pause = Mock(return_value=0)
        self.scheduler_obj.scheduler.pause = mock_pause

        ret = self.scheduler_obj.exposed_pause_scheduler()
        self.assertEqual(ret, 0)

        mock_pause.assert_called_once()

    def test_exposed_resume_scheduler(self):
        mock_resume = Mock(return_value=0)
        self.scheduler_obj.scheduler.resume = mock_resume

        ret = self.scheduler_obj.exposed_resume_scheduler()
        self.assertEqual(ret, 0)

        mock_resume.assert_called_once()

    def test_health_check(self):
        mock_healthcheck = Mock(return_value=0)
        self.scheduler_obj.health_check = mock_healthcheck

        ret = self.scheduler_obj.health_check()
        self.assertEqual(ret, 0)

        mock_healthcheck.assert_called_once()
