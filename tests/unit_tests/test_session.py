from django.test import TestCase
from mock import patch
from cryton.lib.util import exceptions, logger
from cryton.lib.models import session

from cryton.cryton_rest_api.models import (
    SessionModel,
    PlanExecutionModel,
    StepModel
)

import os
from model_bakery import baker

TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.util.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestSession(TestCase):

    def setUp(self) -> None:

        self.plan_exec_obj = baker.make(PlanExecutionModel)
        self.named_session_obj = SessionModel.objects.create(plan_execution=self.plan_exec_obj,
                                                             session_id='42',
                                                             session_name='test-session')
        self.step_model = baker.make(StepModel)

        pass

    def test_create_session(self):
        # Wrong plan execution ID
        with self.assertRaises(exceptions.PlanExecutionDoesNotExist):
            session.create_session(0, '0', 'test')

        sess_obj = session.create_session(self.plan_exec_obj.id, '0', 'test')
        self.assertEqual(sess_obj.session_name, 'test')

    def test_get_msf_session_id(self):

        session_id = session.get_msf_session_id('test-session', self.plan_exec_obj.id)
        self.assertEqual(session_id, '42')

    def test_get_msf_session_id_ex(self):

        with self.assertRaises(exceptions.SessionObjectDoesNotExist):
            session.get_msf_session_id('non-existent-session', self.plan_exec_obj.id)

    def test_set_msf_session_id(self):

        session.set_msf_session_id('test-session', '666', self.plan_exec_obj.id)
        self.assertEqual(session.get_msf_session_id('test-session', self.plan_exec_obj.id), '666')

        with self.assertRaises(exceptions.SessionObjectDoesNotExist):
            session.set_msf_session_id('test-session', '666', 666)

    # @patch('cryton.lib.session.get_session_ids')
    # def test_get_session_ids(self, mock_get_sess):
    #     mock_stub = Mock()
    #     mock_stub.sessions_list().sess_list = '["1", "2"]'
    #
    #     self.step_model.use_any_session_to_target = '1.2.3.4'
    #     session_list = session.get_session_ids('1.2.3.4', self.plan_exec_obj.id)
    #
    #     self.assertEqual('2', session_list[-1])
