import pickle

from django.core.management.base import BaseCommand
from django.db import connection

from cryton.lib import scheduler_client, worker


def monitoring():
    worker_model_list = worker.WorkerModel.objects.all()
    for worker_model_obj in worker_model_list:
        worker.Worker(worker_model_id=worker_model_obj.id).healthcheck()


class Command(BaseCommand):

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute('select job_state from django_apscheduler_djangojob')
            for row in cursor.fetchall():
                job_dict = pickle.loads(row[0])
                if job_dict.get('func') == 'cryton.cryton_rest_api.management.commands.startmonitoring:monitoring':
                    # Monitoring already scheduled
                    return

        scheduler_client.schedule_repeating_function('cryton.cryton_rest_api.management.'
                                                     'commands.startmonitoring:monitoring', seconds=30)

        return None
