from rpyc.utils.server import ThreadedServer
import rpyc
import subprocess
import os
import re
from dataclasses import dataclass

DOCKER_SWARM_ADDR = os.getenv('DOCKER_SWARM_ADDR')


@dataclass
class WorkerCXT:
    host_addr: str
    username: str
    password: str
    key_file: str

    def __init__(self):
        pass


def create_docker_context(ctx_name, worker_host: str, worker_username: str):
    p = subprocess.run(
        ["docker", "context", "create", ctx_name, "--docker", "host=ssh://{}@{}".format(worker_username, worker_host)],
        capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("Could not create context '{}'".format(ctx_name))


def use_docker_context(ctx_name: str, create: bool = False, ):
    p = subprocess.run(["docker", "context", "use", ctx_name], capture_output=True)
    if p.returncode != 0:
        if not create:
            raise RuntimeError("Could not switch to docker context '{}'. Original error: {}".format(ctx_name,
                                                                                                    p.stderr))
        create_docker_context(ctx_name)
        p = subprocess.run(["docker", "context", "use", ctx_name], capture_output=True)
        if p.returncode != 0:
            raise RuntimeError("Could not switch to docker context '{}'. Original error: {}".format(ctx_name,
                                                                                                    p.stderr))


class DeploymentService(rpyc.Service):

    def exposed_deploy_worker(self, worker_name: str, worker_host: str, worker_user: str, worker_pass: str = None,
                              worker_key=None):
        if not re.match('^[a-zA-Z0-9_\- ]+$', worker_name):
            raise ValueError("Worker name contains forbidden characters.")

        ctx_name = "cryton_ctx_{}".format(worker_name)

        use_docker_context(ctx_name, create=True)

        subprocess.run(["docker", ""])


def start_scheduler(blocking: bool = False):
    LHOSTNAME = 'localhost'
    LPORT = 12001
    protocol_config = {'allow_public_attrs': True, 'allow_pickle': True}

    server = ThreadedServer(DeploymentService(), hostname=LHOSTNAME, port=LPORT,
                            protocol_config=protocol_config)
    try:
        print("Starting scheduler service. Listening on {}:{}".format(LHOSTNAME, LPORT))
        server.start()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
