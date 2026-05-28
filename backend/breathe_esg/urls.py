from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.views.static import serve
import os


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("ingestion.urls")),
    path("api/", include("review.urls")),
    path("api/auth/", include("core.auth_urls")),
    # Serve built React static assets (JS, CSS, images) directly
    re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT / "assets"}),
    re_path(r"^favicon\..*$", serve, {"document_root": settings.STATIC_ROOT}),
    # SPA catch-all — serve React index.html for any non-API, non-asset route
    path("", TemplateView.as_view(template_name="index.html")),
    path("<path:path>", TemplateView.as_view(template_name="index.html")),
]
