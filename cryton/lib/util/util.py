import os
import shutil
import json
import base64
import time
from threading import Thread
from functools import reduce
import copy
from typing import List, Union, Dict, Optional
from datetime import datetime, timedelta
import uuid
import configparser
import pytz
import amqpstorm
import jinja2
import re
import yaml

from cryton.cryton_rest_api.models import WorkerModel, PlanModel
from cryton.etc import config
from cryton.lib.util import exceptions, logger, constants
from cryton.lib.models import worker

from amqpstorm import Message
from django.utils import timezone


def rabbit_connection() -> amqpstorm.Connection:
    """
    Creates new Rabbit connection.

    :returns: rabbit connection
    """
    rabbit_username = config.RABBIT_USERNAME
    rabbit_password = config.RABBIT_PASSWORD
    rabbit_srv_addr = config.RABBIT_SRV_ADDR
    rabbit_port = config.RABBIT_SRV_PORT

    try:
        connection = amqpstorm.Connection(rabbit_srv_addr, rabbit_username, rabbit_password, port=rabbit_port)
    except amqpstorm.AMQPConnectionError as ex:
        raise exceptions.RabbitConnectionError(ex)

    return connection


def rabbit_prepare_queue(queue_name: str) -> None:
    """
    Declares Rabbit queue.

    :param queue_name: queue name to declare
    :return: None
    """
    conn = rabbit_connection()
    channel = conn.channel()

    channel.queue.declare(queue_name)

    channel.close()


def rabbit_send_oneway_msg(queue_name: str, msg: str) -> None:
    """

        :param queue_name: Queue name
        :param msg: Message to be sent
        :return: None
        """
    connection = rabbit_connection()
    channel = connection.channel()

    channel.queue.declare(queue_name)
    channel.basic.publish(exchange="", routing_key=queue_name, body=msg)
    connection.close()

    return None


def rm_path(persist_path: str) -> None:
    """
    Remove file or directory
    :param persist_path: full path to the target
    :return: None
    """
    if os.path.exists(persist_path):
        if os.path.isdir(persist_path):
            rm_func = shutil.rmtree
        else:  # is file
            rm_func = os.unlink

        try:
            rm_func(persist_path)
        except (IOError, OSError) as e:
            logger.logger.warning('When removing {}, following exception occurred: {}.'.format(persist_path, e))

    return None


def check_path(file_path: str, desired_prefix: str) -> bool:
    """
    Check if a path is correct

    :param file_path: full path to the target
    :param desired_prefix: desired prefix
    :return: True if path is correct, else False
    """
    file_abs_path = os.path.abspath(file_path)

    # Check if path exists
    dir_abs_path = os.path.dirname(file_abs_path)
    if not os.path.isdir(dir_abs_path):
        return False

    # Check correct file name (against directory traversal etc.)
    return os.path.commonprefix([file_abs_path, desired_prefix]) == desired_prefix


def save_plan_evidence_file(file_name: str, file_content: str, evidence_dir: str) -> str:
    """
    Save an evidence file to an evidence directory
    :param file_name: name of the file
    :param file_content: content of the desired file
    :param evidence_dir: path where to save the file
    :raises: RuntimeError
    :return: path to the file if success
    """
    file_path = "{}/{}".format(evidence_dir, file_name)

    # Check for wrong or malicious path
    if not check_path(file_path, config.EVIDENCE_DIR):
        timestamp = int(time.time())
        logger.logger.warning('Path {} for file storage is invalid, storing file as /tmp/{}'
                              .format(file_path, timestamp))
        file_path = '/tmp/{}'.format(timestamp)

    if type(file_content) == str:
        file_content = file_content.encode()

    # Write to file
    with open(file_path, 'bw') as f:
        try:
            f.write(file_content)
            logger.logger.info('File saved as {}'.format(file_path))

        except Exception as ex:
            msg = 'File {} not stored, unknown error. Original exception was: {}'.format(file_path, ex)
            logger.logger.warning(msg)
            raise RuntimeError(msg)

    return file_path


def store_evidence_file(file_name: str, file_content: str, evidence_dir: str) -> str:
    """
    Store file contents as file into evidence dir
    :param evidence_dir: where the evidence file will be saved
    :param file_name: name of the file to be stored
    :param file_content: contents of the file to be stored
    :raises: ValueError
    :return: Path to saved file
    """
    # Check if values are correct
    if file_name is None or file_name == '':
        raise ValueError("Parameter 'file_name' cannot be empty.")
    if file_content is None or file_content == '':
        raise ValueError("Parameter 'file_content' cannot be empty.")

    # Decode file_content from base64
    try:
        file_content_debase = base64.b64decode(file_content)
    except Exception as ex:
        file_content_debase = "Data is not correctly base64 encoded.\n Original exception: {}.\n" \
                               "Original data received:\n {}".format(ex, file_content)

    # Save it to file
    file_path = save_plan_evidence_file(file_name, file_content_debase, evidence_dir)

    return file_path


def validate_attack_module_args(
        module_name: str,
        module_args: dict,
        worker_model: WorkerModel,
        ) -> bool:
    """

    :param module_name: Name of the module to validate
    :param module_args: Module arguments
    :param worker_model: WorkerModel object
    :return: response
    """

    worker_q_name = worker.Worker(worker_model_id=worker_model.id).control_q_name
    event_info = {constants.EVENT_T: constants.EVENT_VALIDATE_MODULE,
                  constants.EVENT_V: {"attack_module": module_name, "attack_module_arguments": module_args}}
    with Rpc() as rpc:
        resp = rpc.call(worker_q_name, event_info)

    return int(resp.get(constants.EVENT_V).get(constants.RETURN_CODE)) == 0


def convert_to_utc(original_datetime: datetime, time_zone: str = 'utc', offset_aware: bool = False) -> datetime:
    """
    Convert datetime in specified timezone to UTC timezone
    :param original_datetime: datetime to convert
    :param time_zone: timezone of the original datetime (examples: "utc"; "Europe/Prague")
    :param offset_aware: if True, utc_datetime will be offset-aware, else it will be offset-naive
    :return: datetime in UTC timezone
    """
    if not original_datetime.tzinfo:
        original_datetime = pytz.timezone(time_zone).localize(original_datetime, is_dst=None)
        # original_datetime = original_datetime.astimezone(time_zone)

    utc_datetime = original_datetime.astimezone(timezone.utc)
    if not offset_aware:
        return utc_datetime.replace(tzinfo=None)
    return utc_datetime


def convert_from_utc(utc_datetime: datetime, time_zone: str, offset_aware: bool = False) -> datetime:
    """
    Convert datetime in UTC timezone to specified timezone
    :param utc_datetime: datetime in UTC timezone to convert
    :param time_zone: timezone of the new datetime (examples: "utc"; "Europe/Prague")
    :param offset_aware: if True, utc_datetime will be offset-aware, else it will be offset-naive
    :return: datetime with the specified timezone
    """
    if not utc_datetime.tzinfo:
        utc_datetime = pytz.utc.localize(utc_datetime, is_dst=None)

    new_datetime = utc_datetime.astimezone(pytz.timezone(time_zone))
    if not offset_aware:
        return new_datetime.replace(tzinfo=None)
    return new_datetime


def parse_delta_to_datetime(time_str: str) -> timedelta:
    try:
        split_hours = time_str.split("h")
        hours = split_hours[0]

        split_minutes = split_hours[1].split("m")
        minutes = split_minutes[0]

        split_seconds = split_minutes[1].split("s")
        seconds = split_seconds[0]

        hours = int(hours)
        minutes = int(minutes)
        seconds = int(seconds)
    except Exception:
        raise exceptions.UserInputError("Invalid delta provided. Correct format is [int]h[int]m[int]s", time_str)

    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def fill_template(plan_template: str, template_variables: dict, allow_undefined: bool = True) -> str:
    """
    Fill the missing values in the yaml with variables
    :param template_variables: Template variables to fill the template with
    :param plan_template: Plan template dict
    :param allow_undefined: If undefined variables are allowed or not.
    :return: filled json or yaml plan
    """

    if allow_undefined:
        env = jinja2.Environment(undefined=jinja2.DebugUndefined)
    else:
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)

    try:
        plan_template_obj = env.from_string(plan_template)
    except TypeError:
        raise exceptions.PlanValidationError("Plan template is not a valid jinja template: {}".format(plan_template))

    # Throws jinja2.exceptions.UndefinedError
    filled_template = plan_template_obj.render(**template_variables)

    return filled_template


def parse_inventory_file(inventory_file: str) -> dict:
    """
    Reads inventory file (JSON, YAML, INI) and returns it as a dictionary
    :param inventory_file: Inventory file content
    :return: Inventory variables
    """
    # JSON
    try:
        conf_dict = json.loads(inventory_file)
        return conf_dict
    except json.decoder.JSONDecodeError:
        pass
    # YAML
    try:
        conf_dict = yaml.safe_load(inventory_file)
        return conf_dict
    except yaml.YAMLError:
        pass
    # INI
    try:
        config_parser = configparser.ConfigParser()
        config_parser.read_string(inventory_file)
        conf_dict = {section: dict(config_parser.items(section)) for section in config_parser.sections()}
        return conf_dict
    except configparser.Error:
        pass

    raise ValueError("Invalid inventory file provided: {}.".format(inventory_file))


def split_into_lists(input_list: List, target_number_of_lists: int) -> List[List]:
    """
    Evenly splits list into n lists.
    E.g split_into_lists([1,2,3,4], 4) returns [[1], [2], [3], [4]].

    :param input_list: object to split
    :param target_number_of_lists: how many lists to split into
    :returns: list of lists containing original items
    """

    quotient, reminder = divmod(len(input_list), target_number_of_lists)
    return [input_list[i * quotient + min(i, reminder):(i + 1) * quotient + min(i + 1, reminder)] for i in
            range(target_number_of_lists)]


def run_executions_in_threads(step_executions: List) -> None:
    """
    Creates new Rabbit connection, distributes step executions into threads and runs the threads.
    To set desired number of threads/process, see "CRYTON_CORE_EXECUTION_THREADS_PER_PROCESS" variable in config.

    :param step_executions: list of step execution objects
    """
    # Create rabbit connection
    rabbit_conn = rabbit_connection()

    # Split executions into threads
    thread_lists = split_into_lists(step_executions, config.CRYTON_CORE_EXECUTION_THREADS_PER_PROCESS)
    threads = []
    for thread_step_executions in thread_lists:
        new_thread = Thread(target=run_step_executions, args=(rabbit_conn, thread_step_executions))
        threads.append(new_thread)

    for thread in threads:
        thread.start()

    # Wait for threads to finish
    for thread in threads:
        thread.join()

    # Close rabbit connection
    rabbit_conn.close()


def run_step_executions(rabbit_conn: amqpstorm.Connection, step_execution_list: List) -> None:
    """
    Creates new Rabbit channel and runs step executions.

    :param rabbit_conn: Rabbit connection
    :param step_execution_list: list of step execution objects to execute
    """
    channel = rabbit_conn.channel()
    for step_execution in step_execution_list:
        step_execution.execute(channel)

    channel.close()


def getitem(obj: Union[List, Dict], key: str):
    """
    Get item from object using key.
    :param obj: Iterable accessible using key
    :param key: Key to use to get (match) Item
    :return: Matched item
    """
    match = re.match(r"^\[[0-9]+]$", key)  # Check if key matches List index.
    if match is not None:
        key = int(match.group()[1:-1])  # Convert List index to int.

    result = None
    if isinstance(key, str) and isinstance(obj, dict):  # Use key to get item from Dict.
        result = obj.get(key)
        if result is None and key.isdigit():  # May be int.
            result = obj.get(int(key))
    elif isinstance(key, int) and isinstance(obj, list):  # Use key to get item from List.
        try:
            result = obj[key]
        except IndexError:
            pass
    return result


def parse_dot_argument(dot_argument: str) -> List[str]:
    """
    Takes a single argument (Dict key) from dot notation and checks if it also contains list indexes.
    :param dot_argument: Dict key from dot notation possibly containing list indexes
    :return: Dict key and possible List indexes
    """
    list_indexes = re.search(r"((\[[0-9]+])+$)", dot_argument)  # Check for List indexes at the argument's end.
    if list_indexes is not None:  # Get each List index in '[index]' format and get index only.
        parsed_list_indexes = re.findall(r"(\[[0-9]+])", list_indexes.group())
        parsed_list_indexes = [index for index in parsed_list_indexes]
        return [dot_argument[0:list_indexes.start()]] + parsed_list_indexes
    return [dot_argument]  # If no List Indexes are present.


def get_from_dict(dict_in: dict, value: str):
    """
    Get value from dict_in dict
    eg:
      dict_in: {'output': {'username': 'admin'}}
      value: '$dict_in.output.username'
      return: 'admin'
    :param value: value defined in template
    :param dict_in: dict_in for this step
    :return: value from dict_in
    """
    dot_args = value.lstrip('$').split('.')  # Get keys using '.' separator.
    all_args = []  # Dict keys and List indexes.
    for dot_arg in dot_args:  # Go through dot_args and separate all args.
        all_args.extend(parse_dot_argument(dot_arg))

    try:
        res = reduce(getitem, all_args, dict_in)
    except KeyError:
        res = None

    return res


def _finditem(obj, key):
    """
    Check if giben key exists in an object
    :param obj: dictionary/list
    :param key: key
    :return: value at the key position
    """
    if key in obj:
        return obj[key]
    for k, v in obj.items():
        if isinstance(v, dict):
            item = _finditem(v, key)
            if item is not None:
                return item


def update_inner(obj: dict, dict_in: dict, startswith: str):
    """

    Update value inside the object with one specified by prefix and path from dict_in
    eg.: $dict_in.test replaces with dict_in.get('test')

    :param obj: Object
    :param dict_in: dict_in dictioanry
    :param startswith: prefix, eg. $
    :return:
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                if v.startswith(startswith):
                    new_val = get_from_dict(dict_in, v)
                    if new_val is not None:
                        obj.update({k: new_val})
            elif isinstance(v, dict):
                update_inner(v, dict_in, startswith)
            elif isinstance(v, list):
                for value in v:
                    update_inner(value, dict_in, startswith)


def replace_value_in_dict(dict_to_repl: dict,
                          dict_in: dict,
                          startswith: str = '$'):
    """
    Replace value in dictionary
    :param dict_to_repl:
    :param dict_in: dict_in
    :param startswith: prefix
    :return:
    """

    if startswith not in str(dict_to_repl):
        raise ValueError("No value starting with {} in dictionary".format(startswith))
    if dict_in is None:
        # Nothing to replace
        return None
    update_inner(dict_to_repl, dict_in, startswith)


def get_int_from_obj(obj: dict, name: str) -> int or None:
    """
    Convert variable from dictionary to int, if numeric, else return None
    :param obj: object
    :param name: name of var
    :return: int or None
    """
    var = obj.get(name)
    if var is None:
        raise KeyError("{} not in dictionary".format(name))
    return get_int_from_str(var)


def get_int_from_str(var) -> int or None:
    """
    Get int from string
    :param var: variable
    :return: int or None
    """

    if isinstance(var, int):
        return var
    elif isinstance(var, str):
        if var.isnumeric():
            return int(var)
        else:
            return None
    else:
        return None


def fill_dynamic_variables(in_dict, var_dict):
    """

    Fill variables in in_dict with var_dict.

    :param in_dict:
    :param var_dict:
    :return:
    """
    in_dict_copy = copy.deepcopy(in_dict)
    update_inner(in_dict_copy, var_dict, '$')

    return in_dict_copy


def get_all_values(input_container):
    """
    Get all values (recursively) from a dict
    :param input_container: input dict or list
    :return: yields elements, use as list(get_all_values(d))
    """
    if isinstance(input_container, dict):
        for value in input_container.values():
            yield from get_all_values(value)
    elif isinstance(input_container, list):
        for item in input_container:
            yield from get_all_values(item)
    else:
        yield input_container


def get_dynamic_variables(in_dict, prefix='$'):
    """
    Get list of dynamic variables for input dict
    :param in_dict:
    :param prefix:
    :return:
    """
    vars_list = list(get_all_values(in_dict))

    for i in vars_list:
        if isinstance(i, str) and i.startswith(prefix):
            yield i


def get_prefixes(vars_list):
    """
    Get list of prefixes from list of dynamic variables
    :param vars_list:
    :return:
    """
    for i in vars_list:
        yield i.split('.')[0].lstrip('$')


def pop_key(in_dict, val):
    """
    Pop key at specified position (eg. 'k1.k2.k3')
    :param in_dict:
    :param val:
    :return: Nothing, changes in_dict inplace
    """
    if type(in_dict) != dict:
        return in_dict
    if type(val) == list and len(val) > 1:
        if len(val) != 2:
            return pop_key(in_dict.get(val[0]), val[1:])
        else:
            return in_dict.get(val[0]).pop(val[1])
    else:
        print(val)
        return in_dict.pop(val[0])


def add_key(in_dict, path, val):
    """
    Add value on specified key position
    :param in_dict: eg. {a: 1, b:2}
    :param path: 'c.d.e'
    :param val: '3
    :return: changes in place, eg. {a:1, b:2, c:{d:{e:3}}}
    """
    first = True
    tmp_dict = {}

    for i in path.split('.')[::-1]:
        if first is True:
            tmp_dict = {i: val}
            first = False
        else:
            tmp_dict = {i: tmp_dict}
    in_dict.update(tmp_dict)


def rename_key(in_dict, rename_from, rename_to):
    """
    Rename key (= move to different place)

    eg.
    in_dict = {a: 1, b: 2, c: {d: 3}}
    rename_from = 'c.d'
    rename_to = 'e.f.g'

    result = {a: 1, b: 2, e: {f: {g: 3}}}

    :param in_dict:
    :param rename_from:
    :param rename_to:
    :return: Changes inplace
    :raises KeyError, if rename_from key is not found
    """
    new_val = pop_key(in_dict, rename_from.split('.'))
    add_key(in_dict, rename_to, new_val)


class Rpc:
    def __init__(self, channel: Optional[amqpstorm.Channel] = None):
        """
        RPC client.
        :param channel: Existing RabbitMQ channel
        """
        self.channel = channel
        self.response = None
        self.connection = None
        self.queue_name = str(uuid.uuid1())
        self.message = None
        self.correlation_id = None

        self.open()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self) -> None:
        """
        Setup queue and channel, optionally create new connection.
        :return: None
        """
        if self.channel is None:  # Create new connection and channel if not given.
            self.connection = rabbit_connection()
            self.channel = self.connection.channel()

        self.channel.queue.declare(queue=self.queue_name)
        self.channel.basic.consume(self.on_response, no_ack=True, queue=self.queue_name)

    def close(self) -> None:
        """
        Clean up channel, optionally close created connection.
        :return: None
        """
        self.channel.queue.delete(self.queue_name)

        if self.connection is not None:  # Stop channel and connection only if created new one was created.
            self.channel.stop_consuming()
            self.channel.close()
            self.connection.close()

    def prepare_message(self, msg_body: dict, reply_queue: str = None) -> str:
        """
        Create message.
        :param msg_body: Message contents
        :param reply_queue: Custom queue to send the reply to (moves self.queue to msg_body["ack_queue"])
        """
        if reply_queue is not None:  # Update message content and reply_queue.
            msg_body.update({constants.ACK_QUEUE: self.queue_name})
        else:
            reply_queue = self.queue_name

        msg_body = json.dumps(msg_body)  # Create send and process message.
        self.message = Message.create(self.channel, msg_body)
        self.message.reply_to = reply_queue

        self.correlation_id = self.message.correlation_id
        return self.correlation_id

    def call(self, queue_name: str, msg_body: dict = None, time_limit: float = config.CRYTON_RPC_TIMEOUT) -> dict:
        """
        Create RPC call and wait for response.
        :param queue_name: Target RabbitMQ queue
        :param msg_body: Message contents
        :param time_limit: Time limit for response
        and is used for message acknowledgment)
        :return: Call's response
        """
        if self.message is None:
            self.prepare_message(msg_body)

        self.message.publish(queue_name)
        self.wait_for_response(time_limit)
        
        self.message = None
        self.correlation_id = None
        return self.response

    def wait_for_response(self, time_limit: float, sleep_time: float = 0.2) -> None:
        """
        Wait for response.
        :param time_limit: Time limit for response
        :param sleep_time: Duration between response checks
        :return: None
        """
        while not self.response:
            if time_limit <= 0:
                break
            self.channel.process_data_events()
            time_limit -= sleep_time
            time.sleep(sleep_time)

    def on_response(self, message: Message) -> None:
        """
        Save response for correct message.
        :param message: Received RabbitMQ message
        :return: None
        """
        if self.correlation_id == message.correlation_id or self.correlation_id == message.json().get("correlation_id"):
            self.response = message.json()


def send_response(message: Message, response: str) -> None:
    """
    Update properties and send message containing response to reply_to.
    :param message: Received message
    :param response: Response from callback
    :return: None
    """
    logger.logger.debug("Sending RPC response", response=response)
    if isinstance(response, dict):
        response = json.dumps(response)
    if not isinstance(response, str):
        response = str(response)

    properties = {
        'correlation_id': message.correlation_id,
        'content_encoding': 'utf-8',
        'timestamp': timezone.now()
    }

    msg = Message.create(message.channel, response, properties)
    logger.logger.info("sending message", response=response, reply_to=message.reply_to)
    try:
        msg.publish(message.reply_to)
    except Exception as ex:
        logger.logger.info("EXCEPTION", ex=str(ex))
    logger.logger.info("message sent", response=response, reply_to=message.reply_to)

    message.ack()


def get_logs() -> list:
    """
    Retrieve logs from log file.
    :return: Parsed Logs
    """
    if config.LOGGER == 'prod':
        log_file_path = config.LOG_FILE_PATH
    else:
        log_file_path = config.LOG_FILE_PATH_DEBUG

    with open(log_file_path, "r") as log_file:
        return [log.rstrip(", \n") for log in log_file]

def get_plan_yaml(plan_model_id: int) -> dict:
    """
    Get Plan's YAML (template filled with variables).
    :param plan_model_id: Plan ID
    :return: Plan's dictionary
    """
    plan_obj = PlanModel.objects.get(id=plan_model_id)
    plan_dict: dict = plan_obj.plan_dict
    stages = []
    for stage_obj in plan_obj.stages.all():
        steps = []
        for step_obj in stage_obj.steps.all():
            step_dict = {"name": step_obj.name, "step_type": step_obj.step_type,
                         "arguments": step_obj.arguments, "comment": step_obj.comment, "is_init": step_obj.is_init,
                         "output_prefix": step_obj.output_prefix}
            steps.append(step_dict)

        stage_dict = {"name": stage_obj.name, "trigger_type": stage_obj.trigger_type,
                      "trigger_args": stage_obj.trigger_args, "steps": steps}
        stages.append(stage_dict)

    plan_dict.update({"stages": stages})

    return plan_dict