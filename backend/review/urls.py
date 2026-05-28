from django.urls import path
from . import views

urlpatterns = [
    path("records/", views.EmissionRecordListView.as_view(), name="records-list"),
    path("records/<int:pk>/", views.EmissionRecordDetailView.as_view(), name="records-detail"),
    path("records/<int:pk>/approve/", views.ApproveView.as_view(), name="records-approve"),
    path("records/<int:pk>/flag/", views.FlagView.as_view(), name="records-flag"),
    path("records/<int:pk>/reject/", views.RejectView.as_view(), name="records-reject"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
]
