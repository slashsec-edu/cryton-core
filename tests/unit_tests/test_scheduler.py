from django.test import TestCase
from cryton.lib import scheduler, logger
from mock import patch, Mock
import os
import datetime


def run_null(*kwargs):
    return 0


mock_exc = Mock()
mock_exc.start.side_effect = run_null

devnull = open(os.devnull, 'w')


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-debug'))
@patch("sys.stdout", devnull)
class SchedulerTest(TestCase):

    def setUp(self) -> None:
        pass

    @patch('cryton.lib.scheduler.ThreadedServer', mock_exc)
    @patch('cryton.lib.scheduler.BlockingScheduler', Mock())
    def test_start_scheduler(self):
        mock_exc.shutdown.side_effect = KeyboardInterrupt('Test')

        ret = scheduler.start_scheduler()

        self.assertIsNone(ret)

        ret = scheduler.start_scheduler(True)

        self.assertIsNone(ret)

    @patch('cryton.lib.scheduler.config.MISFIRE_GRACE_TIME')
    def test_exposed_add_job(self, config_mock):
        mock_scheduler = Mock()
        mock_job = Mock()
        mock_job.id = '42'
        mock_scheduler.add_job.return_value = mock_job
        service = scheduler.SchedulerService(mock_scheduler)
        fnc = Mock

        ret = service.exposed_add_job(fnc, [], datetime.datetime(3000, 3, 14, 15, 0))
        self.assertEqual(ret, '42')
        mock_scheduler.add_job.assert_called_with(fnc, 'date', misfire_grace_time=config_mock,
                                                  run_date='3000-03-14 15:00:00', args=[])

    def test_exposed_reschedule_job(self):
        mock_scheduler = Mock()
        mock_scheduler.reschedule_job.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.exposed_reschedule_job('42')

        mock_scheduler.reschedule_job.assert_called_with('42')
        self.assertEqual(ret, 0)

    def test_exposed_pause_job(self):
        mock_scheduler = Mock()
        mock_scheduler.pause_job.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.exposed_pause_job('42')

        mock_scheduler.pause_job.assert_called_with('42')
        self.assertEqual(ret, 0)

    def test_exposed_resume_job(self):
        mock_scheduler = Mock()
        mock_scheduler.resume_job.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.exposed_resume_job('42')

        mock_scheduler.resume_job.assert_called_with('42')
        self.assertEqual(ret, 0)

    def test_exposed_remove_job(self):
        mock_scheduler = Mock()
        mock_scheduler.remove_job.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        service.exposed_remove_job('42')

        mock_scheduler.remove_job.assert_called_with('42')

    def test_exposed_get_job(self):
        mock_scheduler = Mock()
        mock_scheduler.get_job.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.exposed_get_job('42')

        mock_scheduler.get_job.assert_called_with('42')
        self.assertEqual(ret, 0)

    def test_exposed_get_jobs(self):
        mock_scheduler = Mock()
        mock_scheduler.get_jobs.return_value = ["job1", "job2"]
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.exposed_get_jobs()

        mock_scheduler.get_jobs.assert_called_once()
        self.assertEqual(ret, ["job1", "job2"])

    def test_exposed_pause_scheduler(self):
        mock_scheduler = Mock()
        mock_scheduler.pause.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.exposed_pause_scheduler()

        mock_scheduler.pause.assert_called_once()
        self.assertEqual(ret, 0)

    def test_exposed_resume_scheduler(self):
        mock_scheduler = Mock()
        mock_scheduler.resume.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.exposed_resume_scheduler()

        mock_scheduler.resume.assert_called_once()
        self.assertEqual(ret, 0)

    def test_health_check(self):
        mock_scheduler = Mock()
        mock_scheduler.resume.return_value = 0
        service = scheduler.SchedulerService(mock_scheduler)

        ret = service.health_check()

        self.assertEqual(ret, 0)

