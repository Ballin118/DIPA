"""URL configuration for core project."""

from django.contrib import admin
from django.urls import path

from main.views import api_insights, api_traffic_live, home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/insights/", api_insights, name="api_insights"),
    path("api/traffic/live/", api_traffic_live, name="api_traffic_live"),
    path("", home, name="home"),
]

