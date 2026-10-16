"""Shared account for the judging committee (documented in README).

Only the scrypt hash is stored here. Runs with `python manage.py migrate`; an existing account is left untouched.
"""
from django.db import migrations

JUDGE = ("990200000", "لجنة التحكيم", "scrypt$16384$AmYhD6IRUYDJA0SWthsZT4$8$5$jXRysGzJHo+yuNFj0Am6iE9R8UA7hiyqaSamyZgkM/o3auzeMpd13o4BnomDX9jXvD45/y2U/EXbGKG0aRcKqg==")


def create_judge(apps, schema_editor):
    User = apps.get_model("auth", "User")
    number, name, password_hash = JUDGE
    if not User.objects.filter(username=number).exists():
        User.objects.create(username=number, first_name=name, password=password_hash, is_active=True)


def remove_judge(apps, schema_editor):
    apps.get_model("auth", "User").objects.filter(username=JUDGE[0]).delete()


class Migration(migrations.Migration):
    dependencies = [("eoip", "0002_team_accounts")]
    operations = [migrations.RunPython(create_judge, remove_judge)]
