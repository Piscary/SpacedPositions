from django.urls import path

from . import views

app_name = "training"

urlpatterns = [
    path("train/start/", views.start, name="start"),
    path("train/launcher/", views.launcher, name="launcher"),
    path("train/flag/", views.flag, name="flag"),
    path("train/r/<str:sid>/batch/", views.batch, name="batch"),
    path("train/r/<str:sid>/attempt/", views.attempt, name="attempt"),
    path("train/r/<str:sid>/end/", views.end, name="end"),
    path("train/r/<str:sid>/result/", views.result, name="result"),
    path("puzzles/from-line/", views.from_line, name="from_line"),
]
