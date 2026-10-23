from django.urls import include, path

urlpatterns = [path("", include("spaced_positions.core.urls"))]
