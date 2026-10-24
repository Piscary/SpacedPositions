from django.urls import include, path

urlpatterns = [
    path("", include("spaced_positions.training.urls")),
    path("", include("spaced_positions.analysis.urls")),
    path("", include("spaced_positions.library.urls")),
    path("", include("spaced_positions.core.urls")),
]
