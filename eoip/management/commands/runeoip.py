"""Run EOIP for the demo (Django app served by Werkzeug, optionally over self-signed HTTPS).

    python manage.py runeoip                          # http://localhost:8000
    python manage.py runeoip --host 0.0.0.0 --https   # phone on the same Wi-Fi: microphone + camera need HTTPS
    python manage.py runeoip --reset                  # fresh event first (decision log kept)

Django's own `runserver` cannot serve HTTPS, and the phone's microphone and camera only work over
HTTPS (or on localhost), so this command uses Werkzeug's development server with an ad-hoc
certificate (needs the `cryptography` package).
"""
import socket

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from eoip import db


def lan_ip():
    """Best guess of this laptop's Wi-Fi address (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "<this-laptop-ip>"


def disable_console_pause():
    """Windows: clicking inside the console window starts a text selection ("QuickEdit"), which
    pauses this process until Esc is pressed — the dashboard then times out. Turn QuickEdit off for
    this window so an accidental click can never freeze the server. No effect on other systems."""
    import sys
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)                 # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS = 0x0040, 0x0080
            kernel32.SetConsoleMode(handle, (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS)
    except Exception:   # never stop the server because of a console setting
        pass


class Command(BaseCommand):
    help = "Serve EOIP (use --host 0.0.0.0 --https for the phone)."

    def add_arguments(self, parser):
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--https", action="store_true", help="self-signed HTTPS (needed for the phone mic/camera)")
        parser.add_argument("--phone-port", type=int, default=0,
                            help="also serve HTTPS on this port for the phone (the laptop keeps plain HTTP on --port)")
        parser.add_argument("--reset", action="store_true", help="start a fresh event; the decision log is kept")

    def handle(self, *args, **opts):
        disable_console_pause()
        try:
            from werkzeug.serving import run_simple
        except ImportError:
            raise CommandError("Install werkzeug first:  pip install werkzeug cryptography")
        from django.db import connection
        if "django_session" not in connection.introspection.table_names():
            raise CommandError("The database is not ready. Run:  python manage.py migrate")
        conn = db.init_db(settings.EOIP_DB)
        if opts["reset"]:
            db.reset_all(conn, keep_decisions=True)
        conn.close()
        from django.contrib.auth import get_user_model
        if not get_user_model().objects.filter(is_active=True).exists():
            self.stdout.write(self.style.WARNING(
                "No employee account yet. Create one first:  python manage.py employee_add"))

        import logging
        # The dashboard polls every 1.5 s: printing every request floods the terminal (and a busy or
        # paused console can stall the server). Only warnings and errors are printed.
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        from eoip_project.wsgi import application
        _preload_camera_model()
        port, phone_port = opts["port"], opts["phone_port"]
        if phone_port:
            # Laptop: plain http://localhost (no certificate warning; localhost may use the mic/camera).
            # Phone: same app over HTTPS on a second port (its microphone and camera need HTTPS).
            import threading
            threading.Thread(target=run_simple, daemon=True, args=(opts["host"], phone_port, application),
                             kwargs=dict(threaded=True, ssl_context="adhoc", use_reloader=False, use_debugger=False)).start()
            self.stdout.write(f"\n  EOIP ops app   : http://localhost:{port}/")
            self.stdout.write(f"  Phone (radio)  : https://{lan_ip()}:{phone_port}/field")
            self.stdout.write("  Stop          : Ctrl + C   (keep this window open and do not type in it)\n")
            run_simple(opts["host"], port, application, threaded=True, use_reloader=False, use_debugger=False)
            return
        ssl = "adhoc" if opts["https"] else None
        scheme = "https" if ssl else "http"
        self.stdout.write(f"\n  EOIP ops app   : {scheme}://localhost:{port}/")
        if opts["host"] == "0.0.0.0":
            self.stdout.write(f"  Phone (radio)  : {scheme}://{lan_ip()}:{port}/field")
            if not ssl:
                self.stdout.write("  Note: the phone microphone and camera need --https (typing works without it)")
        else:
            self.stdout.write("  Phone (radio)  : start with --host 0.0.0.0 to allow the phone to connect")
        self.stdout.write("  Stop          : Ctrl + C   (keep this window open and do not type in it)\n")
        run_simple(opts["host"], port, application, threaded=True, ssl_context=ssl,
                   use_reloader=False, use_debugger=False)


def _preload_camera_model():
    """Load the YOLO model in the background when the server starts, so the first camera frame or
    uploaded video is analysed at once instead of waiting several seconds for the model."""
    import threading

    def load():
        try:
            from eoip.views.camera import _cv
            if _cv():
                import analyzer
                analyzer.create_detector().load()
        except Exception:   # the camera is optional: the rest of the app works without it
            pass
    threading.Thread(target=load, daemon=True).start()
