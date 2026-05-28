from django.urls import path
from . import views

urlpatterns = [
    path("ingest/", views.IngestUploadView.as_view(), name="ingest-upload"),
    path("batches/", views.BatchListView.as_view(), name="batch-list"),
    path("batches/<int:pk>/", views.BatchDetailView.as_view(), name="batch-detail"),
    path("batches/<int:pk>/lock/", views.BatchLockView.as_view(), name="batch-lock"),
]
