"""WSGI entry point (used by `python manage.py runeoip` and any WSGI server)."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "eoip_project.settings")
application = get_wsgi_application()
