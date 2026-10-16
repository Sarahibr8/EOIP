"""Shortcut for the demo:  python run.py --host 0.0.0.0 --https
Same as:                  python manage.py runeoip --host 0.0.0.0 --https
"""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "eoip_project.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line([sys.argv[0], "runeoip", *sys.argv[1:]])
