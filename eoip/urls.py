"""EOIP routes: the two pages, sign-in, the JSON API (/api/...) and the camera API (/api/cv/...)."""
from django.urls import path, re_path

from .views import api, auth, camera, pages

urlpatterns = [
    # pages
    path("", pages.dashboard, name="dashboard"),
    path("field", pages.field, name="field"),
    path("login", auth.login_view, name="login"),
    path("logout", auth.logout_view, name="logout"),
    path("health", pages.health, name="health"),
    re_path(r"^static/(?P<path>.+)$", pages.static, name="static"),

    # API
    path("api/health", api.health),
    path("api/layout", api.get_layout),
    path("api/catalog", api.get_catalog),
    path("api/state", api.state),
    path("api/zones", api.zones),
    path("api/teams", api.teams),
    path("api/decisions", api.decision_log),
    path("api/incidents/<int:incident_id>", api.incident),
    path("api/incidents/<int:incident_id>/decisions", api.decide),
    path("api/incidents/<int:incident_id>/simulate", api.simulate_whatif),
    path("api/incidents/<int:incident_id>/options", api.add_option),
    path("api/ingest", api.ingest),
    path("api/voice/extract", api.voice_extract),
    path("api/voice/report", api.voice_report),
    path("api/demo/reset", api.demo_reset),
    path("api/demo/start", api.demo_start),
    path("api/demo/autostart", api.demo_autostart),
    path("api/demo/stop", api.demo_stop),
    path("api/demo/tick", api.demo_tick),
    path("api/demo/skip", api.demo_skip),
    path("api/demo/cv-replay", api.demo_cv_replay),

    # camera (phone / browser camera and uploaded test videos)
    path("api/cv/status", camera.status),
    path("api/cv/sessions", camera.start_session),
    path("api/cv/sessions/<str:sid>/frame", camera.session_frame),
    path("api/cv/sessions/<str:sid>", camera.end_session),
    path("api/cv/video", camera.analyse_video),
]
