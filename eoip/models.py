"""Django models for the EOIP operational tables.

The tables themselves are created from eoip/schema.sql (by `python manage.py migrate`, see apps.py)
and written by the core pipeline in eoip/core with explicit transactions. These models are
`managed = False`: Django maps them for the admin and for ORM reads, but never alters the tables.
Employees are Django users (django.contrib.auth): username = employee number, first_name = name.
"""
from django.conf import settings
from django.db import models


class Zone(models.Model):
    id = models.TextField(primary_key=True)
    name_ar = models.TextField()
    name_en = models.TextField()
    kind = models.TextField()
    criticality = models.IntegerField()
    capacity = models.IntegerField()
    occupancy = models.IntegerField()
    inflow_per_min = models.FloatField()
    outflow_per_min = models.FloatField()
    staff_on_duty = models.IntegerField()
    staff_required = models.IntegerField()
    neighbors = models.TextField()

    class Meta:
        managed = False
        db_table = "zones"
        ordering = ["id"]

    def __str__(self):
        return f"{self.id} · {self.name_en}"


class Location(models.Model):
    id = models.TextField(primary_key=True)
    zone = models.ForeignKey(Zone, models.DO_NOTHING, db_column="zone_id")
    name_ar = models.TextField()
    name_en = models.TextField()

    class Meta:
        managed = False
        db_table = "locations"
        ordering = ["zone_id", "id"]

    def __str__(self):
        return f"{self.id} · {self.name_en}"


class Incident(models.Model):
    code = models.TextField(unique=True)
    type = models.TextField()
    kind = models.TextField()
    zone = models.ForeignKey(Zone, models.DO_NOTHING, db_column="zone_id")
    location = models.ForeignKey(Location, models.DO_NOTHING, db_column="location_id", null=True, blank=True)
    status = models.TextField()
    priority = models.TextField()
    priority_score = models.IntegerField()
    priority_reasons = models.TextField()
    confidence = models.FloatField()
    alert_count = models.IntegerField()
    source_count = models.IntegerField()
    opened_at = models.TextField()
    updated_at = models.TextField()
    escalated_at = models.TextField(null=True, blank=True)
    closed_at = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "incidents"
        ordering = ["priority", "-priority_score"]

    def __str__(self):
        return f"{self.code} · {self.type} · {self.priority}"


class Alert(models.Model):
    external_ref = models.TextField(null=True, blank=True)
    signal_type = models.TextField()
    source_system = models.TextField()
    category = models.TextField()
    zone = models.ForeignKey(Zone, models.DO_NOTHING, db_column="zone_id", null=True, blank=True)
    location = models.ForeignKey(Location, models.DO_NOTHING, db_column="location_id", null=True, blank=True)
    location_detail = models.TextField(null=True, blank=True)
    raw_text = models.TextField(null=True, blank=True)
    language = models.TextField(null=True, blank=True)
    severity_hint = models.IntegerField()
    confidence = models.FloatField()
    payload = models.TextField()
    origin = models.TextField()
    occurred_at = models.TextField()
    received_at = models.TextField()
    disposition = models.TextField()
    duplicate_of = models.ForeignKey("self", models.DO_NOTHING, db_column="duplicate_of", null=True, blank=True)
    incident = models.ForeignKey(Incident, models.DO_NOTHING, db_column="incident_id", null=True, blank=True)
    correlation = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "alerts"
        ordering = ["-id"]

    def __str__(self):
        return f"#{self.id} {self.source_system} · {self.category} · {self.disposition}"


class Recommendation(models.Model):
    incident = models.ForeignKey(Incident, models.DO_NOTHING, db_column="incident_id")
    code = models.TextField()
    rec_type = models.TextField()
    rank = models.IntegerField()
    params = models.TextField()
    simulation = models.TextField(null=True, blank=True)
    status = models.TextField()
    created_at = models.TextField()

    class Meta:
        managed = False
        db_table = "recommendations"
        ordering = ["incident_id", "rank"]

    def __str__(self):
        return f"{self.code} ({self.status})"


class Decision(models.Model):
    """Permanent decision log: who decided what, when and why (kept across demo resets)."""
    run_id = models.IntegerField()
    incident = models.ForeignKey(Incident, models.DO_NOTHING, db_column="incident_id", null=True, blank=True)
    recommendation = models.ForeignKey(Recommendation, models.DO_NOTHING, db_column="recommendation_id",
                                       null=True, blank=True)
    action = models.TextField()
    operator = models.TextField()
    employee = models.ForeignKey(settings.AUTH_USER_MODEL, models.DO_NOTHING, db_column="employee_id",
                                 null=True, blank=True, db_constraint=False, related_name="eoip_decisions")
    employee_number = models.TextField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    priority_at_decision = models.TextField()
    created_at = models.TextField()
    snapshot = models.TextField()

    class Meta:
        managed = False
        db_table = "decisions"
        ordering = ["-id"]

    def __str__(self):
        return f"#{self.id} {self.action} by {self.operator}"


class Team(models.Model):
    """Response teams - SYNTHETIC demo roster (data/teams.json)."""
    id = models.TextField(primary_key=True)
    name_ar = models.TextField()
    name_en = models.TextField()
    kind = models.TextField()
    base_zone = models.ForeignKey(Zone, models.DO_NOTHING, db_column="base_zone")
    base_location = models.ForeignKey(Location, models.DO_NOTHING, db_column="base_location", null=True, blank=True)
    members = models.IntegerField()
    status = models.TextField()
    incident = models.ForeignKey(Incident, models.DO_NOTHING, db_column="incident_id", null=True, blank=True)
    assigned_at = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "teams"
        ordering = ["id"]

    def __str__(self):
        return f"{self.id} · {self.name_en}"
