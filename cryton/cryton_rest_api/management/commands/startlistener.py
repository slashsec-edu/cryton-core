from cryton.lib.services import listener

from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def handle(self, *args, **options):
        listener.Listener().start()
