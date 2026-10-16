from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _create_operational_tables(sender, **kwargs):
    """`python manage.py migrate` also creates (or upgrades) the EOIP operational tables from
    schema.sql and seeds the demo layout, so one command prepares the whole database."""
    from django.conf import settings
    from . import db
    db.init_db(settings.EOIP_DB).close()


class EoipConfig(AppConfig):
    name = "eoip"
    verbose_name = "EOIP operations"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        post_migrate.connect(_create_operational_tables, sender=self)
