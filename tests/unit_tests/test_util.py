from django.test import TestCase
from mock import patch, MagicMock, call
import os
import yaml
import datetime
import pytz
from model_bakery import baker
import jinja2
import copy

from cryton.lib import util, logger

from cryton.cryton_rest_api.models import (
    WorkerModel
)


TESTS_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


@patch('cryton.lib.logger.logger', logger.structlog.getLogger('cryton-debug'))
class TestUtil(TestCase):

    def setUp(self) -> None:
        self.worker = baker.make(WorkerModel)

    @patch('cryton.lib.util.rabbit_connection')
    def test_execute_attack_module(self, mock_rabb):
        rabbit_channel = MagicMock()
        mock_rabb.return_value = (MagicMock(), MagicMock())
        # mock_rabb().execute().ret = json.dumps(ret_val)

        ret = util.execute_attack_module(rabbit_channel=rabbit_channel,
                                         attack_module='test', attack_module_arguments={'test': 'test'},
                                         event_identification_value=1,
                                         worker_model=self.worker)
        self.assertIsInstance(ret, str)

    def test_rm_path_file(self):
        file_name = '/tmp/file_test-for-remove0356241'
        with open(file_name, 'w'):
            pass
        util.rm_path(file_name)

        self.assertFalse(os.path.isfile(file_name))

    def test_rm_path_dir(self):
        dir_path = '/tmp/dir_test-for-remove0356241'
        os.mkdir(dir_path)
        util.rm_path(dir_path)

        self.assertFalse(os.path.isdir(dir_path))

    @patch('cryton.lib.util.shutil.rmtree')
    def test_rm_path_error(self, mock_rm):
        def raise_err(_):
            raise IOError()

        mock_rm.side_effect = raise_err
        dir_path = '/tmp/dir_test-for-remove0356241'
        os.mkdir(dir_path)
        with self.assertLogs('cryton-debug', level='INFO') as cm:
            util.rm_path(dir_path)
        os.rmdir(dir_path)

        self.assertIn("When removing", cm.output[0])

    def test_check_path(self):
        prefix = '/tmp'
        dir_name = 'dir_test-for-remove0356240'
        os.mkdir(dir_name)
        ret = util.check_path(prefix + '/' + dir_name, prefix)
        os.rmdir(dir_name)
        self.assertTrue(ret)

        ret = util.check_path('/no/' + dir_name, prefix)
        self.assertFalse(ret)

    @patch('cryton.lib.util.time.time')
    def test_save_plan_evidence_file(self, mock_time):
        mock_time.return_value = 1588344064
        ret = util.save_plan_evidence_file('test', 'test', 'test')
        os.remove(ret)
        self.assertEqual(ret, '/tmp/1588344064')

        with self.assertRaises(Exception):
            util.save_plan_evidence_file('test', 1, '')

    @patch('cryton.lib.util.save_plan_evidence_file')
    def test_store_evidence_file(self, mock_save):
        mock_save.return_value = 'path'
        ret = util.store_evidence_file('test', 'test', 'test')
        self.assertEqual(ret, 'path')

    def test_store_evidence_file_name_missing(self):
        with self.assertRaises(ValueError):
            util.store_evidence_file('', 'test', 'test')

    def test_store_evidence_file_contents_missing(self):
        with self.assertRaises(ValueError):
            util.store_evidence_file('test', '', 'test')

    @patch('cryton.lib.util.save_plan_evidence_file')
    @patch('cryton.lib.util.base64.b64decode')
    def test_store_evidence_file(self, mock_decode, mock_save):
        def raise_err():
            raise Exception()

        mock_save.return_value = 'path'
        mock_decode.side_effect = raise_err
        ret = util.store_evidence_file('test', 'test', 'test')
        self.assertEqual(ret, 'path')

    # TODO fix
    # def test_validate_attack_module_args(self):
    #     ret_val = {'return_code': 0}
    #
    #     ret = util.validate_attack_module_args('test', {'test': 'test'})
    #     ret = json.loads(ret.ret)
    #     self.assertEqual(ret, ret_val)

    def test_convert_to_utc(self):
        original_datetime = datetime.datetime.now()
        ret = util.convert_to_utc(original_datetime)
        self.assertEqual(ret, original_datetime)

    def test_convert_to_utc_localized(self):
        original_datetime = pytz.timezone('utc').localize(datetime.datetime.now())
        ret = util.convert_to_utc(original_datetime, offset_aware=True)
        self.assertEqual(ret, original_datetime)

    def test_convert_from_utc(self):
        original_datetime = datetime.datetime.now()
        ret = util.convert_from_utc(original_datetime, 'utc')
        self.assertEqual(ret, original_datetime)

    def test_convert_from_utc_localized(self):
        original_datetime = pytz.timezone('utc').localize(datetime.datetime.now())
        ret = util.convert_from_utc(original_datetime, 'utc', True)
        self.assertEqual(ret, original_datetime)

    def test_fill_template(self):
        with open(TESTS_DIR + '/plan-template.yaml') as plan_yaml:
            plan_template = plan_yaml.read()
        with open(TESTS_DIR + '/inventory.yaml') as inventory:
            plan_inventory = yaml.safe_load(inventory)
        with open(TESTS_DIR + '/inventory-part1.yaml') as inventory:
            plan_inventory_part1 = yaml.safe_load(inventory)

        filled = util.fill_template(plan_template, plan_inventory)
        self.assertIsInstance(filled, str)

        # Unfilled variables
        with self.assertRaises(jinja2.exceptions.UndefinedError):
            util.fill_template(plan_template, plan_inventory_part1, False)


    @patch("cryton.lib.util.rabbit_connection")
    def test_rabbit_prepare_queue(self, mock_rabbit_connection):
        mock_channel = MagicMock()
        mock_queue = MagicMock()
        mock_channel.queue = mock_queue
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_rabbit_connection.return_value = mock_connection

        util.rabbit_prepare_queue("testname")

        mock_connection.channel.assert_called_once()
        mock_channel.close.assert_called_once()
        mock_channel.queue.declare.assert_called_once_with("testname")

    def test_split_into_lists(self):
        input_list = [1, 2, 3]
        ret = util.split_into_lists(input_list, 3)
        self.assertEqual(ret, [[1], [2], [3]])

        input_list = [1, 2, 3, 4]
        ret = util.split_into_lists(input_list, 3)
        self.assertEqual(ret, [[1, 2], [3], [4]])

        input_list = [1, 2]
        ret = util.split_into_lists(input_list, 3)
        self.assertEqual(ret, [[1], [2], []])

    @patch("cryton.lib.util.rabbit_connection")
    @patch("cryton.lib.util.run_step_executions")
    @patch("cryton.lib.util.split_into_lists", MagicMock(return_value=["exec1", "exec2", "exec3"]))
    @patch("cryton.lib.util.Thread")
    def test_run_executions_in_threads(self, mock_thread, mock_run_step_executions, mock_rabbit_connection):
        mock_conn = MagicMock()
        mock_rabbit_connection.return_value = mock_conn
        util.run_executions_in_threads(["exec1", "exec2", "exec3"])
        calls = [call(target=mock_run_step_executions, args=(mock_conn, "exec1")),
                 call(target=mock_run_step_executions, args=(mock_conn, "exec2")),
                 call(target=mock_run_step_executions, args=(mock_conn, "exec3"))]

        mock_thread.assert_has_calls(calls)

    def test_run_step_executions(self):
        step_exec1 = MagicMock()
        step_exec2 = MagicMock()
        connection = MagicMock()
        channel = MagicMock()

        connection.channel.return_value = channel

        util.run_step_executions(connection, [step_exec1, step_exec2])

        step_exec1.execute.assert_called_with(channel)
        step_exec2.execute.assert_called_with(channel)

        channel.close.assert_called_once()

    def test_get_from_mod_in(self):
        resp = util.get_from_dict({'parent': {'output': {'username': 'admin'}}}, '$parent.output.username')
        self.assertEqual(resp, 'admin')

        resp = util.get_from_dict({'a': [{'b': 1}, {'c': 2}]}, '$a.1.c')
        self.assertEqual(resp, 2)

    def test_update_inner(self):
        mod_in = {'parent': {'t1': {'t2': 666}}}

        args = {
            'arg1': 1,
            'arg2': {
                'test': '$parent.t1.t2'
            },
            'arg3': [1, 2, 3],
            'arg4': [
                {1: '$parent.test;'}
            ],
            'arg5': {
                '1': {
                    '2': '$parent.test;'
                }
            }
        }

        util.update_inner(args, mod_in, '$parent')

        self.assertEqual(args.get('arg2').get('test'), 666)
        self.assertEqual(args.get('arg4')[0].get(1), '$parent.test;')
        self.assertEqual(args.get('arg5').get('1').get('2'), '$parent.test;')

    def test_replace_value_in_dict(self):
        mod_in = {'t1': {'t2': 666}}

        args = {
            'arg1': 1,
            'arg2': {
                'test': '$parent.t1.t2'
            },
            'arg3': [1, 2, 3],
            'arg4': [
                {1: '$parent.test;'}
            ],
            'arg5': {
                '1': {
                    '2': '$parent.test;'
                }
            }
        }
        util.replace_value_in_dict(copy.deepcopy(args), mod_in)
        with self.assertRaises(ValueError):
            util.replace_value_in_dict(copy.deepcopy(args), mod_in, '$testing')
        # Ok
        util.replace_value_in_dict(copy.deepcopy(args), None)
        with self.assertRaises(ValueError):
            util.replace_value_in_dict(None, mod_in)
        util.replace_value_in_dict(copy.deepcopy(args), {})

    def test_get_int_from_obj(self):
        dict_in = {'test_id': 1}
        self.assertEqual(util.get_int_from_obj(dict_in, 'test_id'), 1)

        dict_in = {'test_id': '2'}
        self.assertEqual(util.get_int_from_obj(dict_in, 'test_id'), 2)

        with self.assertRaises(KeyError):
            util.get_int_from_obj(dict_in, 'nonexistent')

        dict_in = {'test_id': 'Not a number'}
        self.assertEqual(util.get_int_from_obj(dict_in, 'test_id'), None)

    def test_get_int_from_str(self):
        self.assertEqual(util.get_int_from_str('12'), 12)

        self.assertEqual(util.get_int_from_str(12), 12)

        self.assertEqual(util.get_int_from_str('12abc'), None)

    def test_rename_key(self):
        dict_in = {'1': 1, '2': 2, '3': {'4': {'5': 6}, '7': 8}}
        rename_from = '3.4'
        rename_to = '9.10.11'
        expected = {'1': 1, '2': 2, '3': {'7': 8}, '9': {'10': {'11': {'5': 6}}}}

        util.rename_key(dict_in, rename_from, rename_to)
        self.assertEqual(dict_in, expected)

        dict_in = {'1': 1, '2': 2}
        rename_from = '2'
        rename_to = '6'
        expected = {'1': 1, '6': 2}

        util.rename_key(dict_in, rename_from, rename_to)
        self.assertEqual(dict_in, expected)

        dict_in = {'1': 1, '2': 2}
        rename_from = '3'
        rename_to = '6'

        with self.assertRaises(KeyError):
            util.rename_key(dict_in, rename_from, rename_to)
