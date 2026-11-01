from django.urls import path

from . import commands, views  # noqa: F401 (commands registers the lesson commands)

app_name = "coaching"

urlpatterns = [
    path("coach/lessons/", views.lessons, name="lessons"),
    path("coach/lessons/<int:pk>/", views.lesson, name="lesson"),
    path("coach/lessons/<int:pk>/homework/", views.homework_file, name="homework_file"),
    path("coach/complete/", views.complete, name="complete"),
    path("coach/results/", views.results_in, name="results_in"),
    path("coach/homework/<str:assignment>/cards/", views.homework_cards, name="homework_cards"),
    path("coach/homework/<str:assignment>/results/", views.results_file, name="results_file"),
]
