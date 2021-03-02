from django.test import TestCase
from mock import patch, MagicMock, Mock

from cryton.lib import (
    logger,
    worker,
    creator,
    exceptions
)

from cryton.cryton_rest_api.models import (
    CorrelationEvent
)


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestWorker(TestCase):

    def setUp(self) -> None:
        self.worker_obj = creator.create_worker('test-name', 'test-address')

    def test_incorrect_id(self):
        with self.assertRaises(exceptions.WorkerObjectDoesNotExist):
            worker.Worker(worker_model_id=1000)

    def test_properties_address(self):
        self.worker_obj.address = 'some-address'
        self.assertEqual(self.worker_obj.address, 'some-address')

    def test_properties_q_prefix(self):
        self.assertEqual(self.worker_obj.q_prefix, self.worker_obj.name + '_' + self.worker_obj.address)
        self.worker_obj.q_prefix = 'new-prefix'
        self.assertEqual(self.worker_obj.q_prefix, 'new-prefix')

    def test_properties_name(self):
        self.worker_obj.name = 'some-name'
        self.assertEqual(self.worker_obj.name, 'some-name')
        
    def test_properties_state(self):
        self.worker_obj.state = 'some-state'
        self.assertEqual(self.worker_obj.state, 'some-state')

    def test_properties_attack_q_name(self):
        self.assertEqual(self.worker_obj.attack_q_name, 'cryton_worker.{}.attack.request'
                         .format(self.worker_obj.q_prefix))

    def test_properties_control_q_name(self):
        self.assertEqual(self.worker_obj.control_q_name, 'cryton_worker.{}.control.request'
                         .format(self.worker_obj.q_prefix))

    @patch('cryton.lib.worker.sleep', return_value=None)
    @patch('cryton.lib.worker.WorkerRpc.call')
    def test_healthcheck(self, mock_rab, mock_sleep):
        mock_rab.return_value = {'event_v': {'return_code': 0}}
        self.assertTrue(self.worker_obj.healthcheck())
        mock_rab.return_value = {'event_v': {'return_code': -1}}
        self.assertFalse(self.worker_obj.healthcheck())
        mock_rab.return_value = None
        self.assertFalse(self.worker_obj.healthcheck())

    def test_delete(self):
        worker_id = self.worker_obj.model.id
        self.assertTrue(worker.WorkerModel.objects.filter(id=worker_id).exists())
        self.worker_obj.delete()
        self.assertFalse(worker.WorkerModel.objects.filter(id=worker_id).exists())

