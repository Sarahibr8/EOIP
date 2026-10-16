"""Start a fresh event: signals, incidents and team assignments are cleared; the decision log is KEPT.

    python manage.py eoip_reset
    python manage.py eoip_reset --clear-decision-log     # also empties the decision log (asks first)
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from eoip import db


class Command(BaseCommand):
    help = "Reset the demo event (the decision log is kept unless --clear-decision-log)."

    def add_arguments(self, parser):
        parser.add_argument("--clear-decision-log", action="store_true")

    def handle(self, *args, **opts):
        keep = True
        if opts["clear_decision_log"]:
            if input("Delete ALL logged decisions permanently? Type YES to confirm: ").strip() == "YES":
                keep = False
            else:
                self.stdout.write("Decision log kept.")
        conn = db.init_db(settings.EOIP_DB)
        db.reset_all(conn, keep_decisions=keep)
        conn.close()
        self.stdout.write(self.style.SUCCESS("Fresh event ready." + ("" if keep else " Decision log cleared.")))
