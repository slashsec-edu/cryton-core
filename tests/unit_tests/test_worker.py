from django.test import TestCase
from mock import patch, Mock

from cryton.lib.util import exceptions, logger
from cryton.lib.models import worker


@patch('cryton.lib.util.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestWorker(TestCase):

    def setUp(self) -> None:
        self.worker_obj = worker.Worker(name='test-name', address='test-address', q_prefix="test-prefix")

    def test_incorrect_id(self):
        with self.assertRaises(exceptions.WorkerObjectDoesNotExist):
            worker.Worker(worker_model_id=1000)

    def test_properties_address(self):
        self.worker_obj.address = 'some-address'
        self.assertEqual(self.worker_obj.address, 'some-address')

    def test_properties_q_prefix(self):
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

    @patch('cryton.lib.util.util.Rpc.__enter__')
    def test_healthcheck(self, mock_rab):
        mock_call = Mock()
        mock_call.call = Mock(return_value={'event_v': {'return_code': 0}})
        mock_rab.return_value = mock_call
        self.assertTrue(self.worker_obj.healthcheck())
        mock_call.call = Mock(return_value={'event_v': {'return_code': -1}})
        mock_rab.return_value = mock_call

        self.assertFalse(self.worker_obj.healthcheck())
        mock_call.call = Mock(return_value=None)
        mock_rab.return_value = mock_call
        self.assertFalse(self.worker_obj.healthcheck())

    def test_delete(self):
        worker_id = self.worker_obj.model.id
        self.assertTrue(worker.WorkerModel.objects.filter(id=worker_id).exists())
        self.worker_obj.delete()
        self.assertFalse(worker.WorkerModel.objects.filter(id=worker_id).exists())
