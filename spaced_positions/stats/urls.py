from django.urls import path

from . import views

app_name = "stats"

urlpatterns = [
    path("stats/sections/", views.stats_sections, name="sections"),
    path("stats/seen/", views.seen, name="seen"),
]
