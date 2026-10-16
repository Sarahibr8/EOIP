"""URL map. Pages and API live in the `eoip` app; Django admin is a read-only window on the data."""
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "EOIP · Admin"
admin.site.site_title = "EOIP"
admin.site.index_title = "Expo Operations Intelligence Platform"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("eoip.urls")),
]
