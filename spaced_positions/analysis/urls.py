from django.urls import path

from . import views

app_name = "analysis"

urlpatterns = [
    path("analysis/new/", views.create, name="create"),
    path("analysis/<str:pid>/", views.load, name="load"),
    path("analysis/<str:pid>/play/", views.play, name="play"),
    path("analysis/<str:pid>/line/", views.line, name="line"),
    path("analysis/<str:pid>/edit/", views.edit, name="edit"),
    path("analysis/<str:pid>/delete/", views.delete, name="delete"),
    path("analysis/<str:pid>/promote/", views.promote, name="promote"),
    path("analysis/<str:pid>/reorder/", views.reorder, name="reorder"),
    path("analysis/<str:pid>/position/", views.set_position, name="position"),
    path("analysis/<str:pid>/replace/", views.replace, name="replace"),
    path("analysis/<str:pid>/puzzle/", views.puzzle, name="puzzle"),
    path("analysis/<str:pid>/inspector/", views.inspector, name="inspector"),
    path("positions/search/", views.search, name="search"),
    path("journal/", views.journal, name="journal"),
    path("journal/<int:eid>/undo/", views.undo, name="undo"),
    path("journal/<int:eid>/redo/", views.redo, name="redo"),
]
