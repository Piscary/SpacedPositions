from django.urls import path

from . import collect, commands, edit, importer, views  # noqa: F401 (commands and edit register the server commands)

app_name = "library"

urlpatterns = [
    path("lib/results/", views.results, name="results"),
    path("lib/complete/", views.complete, name="complete"),
    path("lib/facets/", views.facets, name="facets"),
    path("lib/cards/", views.cards, name="cards"),
    path("lib/subject/", views.subject, name="subject"),
    path("lib/fens/", views.fens, name="fens"),
    path("lib/export/", views.export, name="export"),
    path("lib/collect/save/", collect.save, name="collect_save"),
    path("lib/collect/many/", collect.save_many, name="collect_many"),
    path("lib/sources/new/", collect.new_source, name="new_source"),
    path("lib/presets/", collect.save_preset, name="presets"),
    path("lib/import/scan/", importer.scan_view, name="import_scan"),
    path("lib/import/run/", importer.run_view, name="import_run"),
    path("lib/import/upload/", importer.upload_view, name="import_upload"),
    path("lib/import/job/<str:job_id>/", importer.job_view, name="import_job"),
]
