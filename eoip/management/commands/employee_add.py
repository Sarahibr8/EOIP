"""Create an employee account (a Django user). There are no default accounts.

    python manage.py employee_add                      # asks for number, name and password
    python manage.py employee_add --number 1001 --name "دلال"   # asks only for the password
"""
import os
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from eoip.views.auth import normalize_employee_number


class Command(BaseCommand):
    help = "Create an active EOIP employee account (employee number + display name + password)."

    def add_arguments(self, parser):
        parser.add_argument("--number", help="employee number (digits only)")
        parser.add_argument("--name", help="display name shown in the app and the decision log")

    def handle(self, *args, **opts):
        number = normalize_employee_number(opts["number"] or input("Employee number (digits only): "))
        if not number:
            raise CommandError("The employee number must contain digits only.")
        name = " ".join((opts["name"] or input("Display name: ")).split())
        if not 1 <= len(name) <= 80:
            raise CommandError("The display name must be 1-80 characters.")
        User = get_user_model()
        if User.objects.filter(username=number).exists():
            raise CommandError("That employee number already exists.")
        password = os.environ.get("EOIP_NEW_PASSWORD") or getpass("Password (minimum 12 characters): ")
        if not os.environ.get("EOIP_NEW_PASSWORD") and password != getpass("Confirm password: "):
            raise CommandError("Passwords do not match. (Was the keyboard still in Arabic?)")
        try:
            validate_password(password)
        except ValidationError as e:
            raise CommandError(" ".join(e.messages))
        User.objects.create_user(username=number, password=password, first_name=name)
        self.stdout.write(self.style.SUCCESS(
            f"Employee {number} ({name}) created. The password is stored only as a scrypt hash."))
