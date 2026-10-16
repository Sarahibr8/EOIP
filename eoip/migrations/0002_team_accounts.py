"""Team accounts for the demo (employee number = username, display name = first name).

Only scrypt password hashes are stored here, never the passwords themselves.
Runs once with `python manage.py migrate`; existing accounts are left untouched.
"""
from django.db import migrations

TEAM = [
    ("990203002", "دلال القرني", "scrypt$16384$FC6ZdvjWtmUG5A9Qp0wChx$8$5$+xeRDlq9W/6ZVA+wqcuGTg10dU/OUjIIql6gBbQCvhfsjWnDNGcn5CQTEZCym84ntE8qMmigWymTTgJaCbc/+A=="),
    ("990203003", "خديجه العبيدالله", "scrypt$16384$y9oi7gxEiV8zPY5QgUECbx$8$5$gbpLD1LksxWApW2blf8A5D67rzKM2hcNOY9eXMgCBEfzRrcCaAaAfUki69yKinCBqbQnmWjMws8uFerq07AUKg=="),
    ("990203004", "روان السبيعي", "scrypt$16384$oZ1lxkqe73zpr3wJ0lEtUX$8$5$wu2YP9hRCRW6m9r/ityhjQD93E1/OAgEg65BMAq43GEt1uczWpebOz5VMGDiAhvS44gIdiGxRyGkSSAP49CA/w=="),
    ("990203005", "نجد العتيبي", "scrypt$16384$uyNFJBEGFecoEa9GqrNF0e$8$5$HP6woR7LS5gqFW1+e4heuWt9TrGt5sPmk3/f/WtaTZ76VqAYxmnWUnCE34TgTOqE33JJrPKpunLNTeF7XaJE1w=="),
    ("990203006", "سارة السبيعي", "scrypt$16384$ZZBbFbjeOWJKoQ3WLjhsGD$8$5$7TKnWJGcPkgG3gTdQD49zdQkpl4q3W8lBzj8A/Sz6VZA1SeM0Zv3lkEgcmyz+sbg3perWpzZ0soEiqhDr4oSJQ=="),
]


def create_team(apps, schema_editor):
    User = apps.get_model("auth", "User")
    for number, name, password_hash in TEAM:
        if not User.objects.filter(username=number).exists():
            User.objects.create(username=number, first_name=name, password=password_hash, is_active=True)


def remove_team(apps, schema_editor):
    apps.get_model("auth", "User").objects.filter(username__in=[t[0] for t in TEAM]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("eoip", "0001_initial"),
    ]
    operations = [migrations.RunPython(create_team, remove_team)]
