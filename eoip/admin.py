"""Read-only Django admin over the EOIP data (for review and the jury; all changes go through the app,
so the pipeline's rules, priorities and the decision log stay consistent)."""
from django.contrib import admin

from .models import Alert, Decision, Incident, Location, Recommendation, Team, Zone


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Zone)
class ZoneAdmin(ReadOnly):
    list_display = ("id", "name_en", "name_ar", "capacity", "occupancy", "staff_on_duty", "staff_required")


@admin.register(Location)
class LocationAdmin(ReadOnly):
    list_display = ("id", "zone", "name_en", "name_ar")


@admin.register(Incident)
class IncidentAdmin(ReadOnly):
    list_display = ("code", "type", "kind", "zone", "location", "priority", "priority_score", "status",
                    "alert_count", "source_count", "opened_at")
    list_filter = ("priority", "status", "kind", "zone")
    search_fields = ("code",)


@admin.register(Alert)
class AlertAdmin(ReadOnly):
    list_display = ("id", "signal_type", "source_system", "category", "zone", "location", "disposition",
                    "incident", "origin", "received_at")
    list_filter = ("disposition", "signal_type", "source_system", "origin", "zone")
    search_fields = ("raw_text", "category")


@admin.register(Recommendation)
class RecommendationAdmin(ReadOnly):
    list_display = ("id", "incident", "code", "rec_type", "rank", "status", "created_at")
    list_filter = ("status", "rec_type")


@admin.register(Decision)
class DecisionAdmin(ReadOnly):
    list_display = ("id", "created_at", "action", "operator", "employee_number", "priority_at_decision",
                    "incident", "run_id")
    list_filter = ("action", "run_id")
    search_fields = ("operator", "employee_number", "note")


@admin.register(Team)
class TeamAdmin(ReadOnly):
    list_display = ("id", "name_en", "kind", "base_zone", "base_location", "status", "incident")
    list_filter = ("kind", "status")
