from django.urls import path
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
import json


@ensure_csrf_cookie
def get_csrf(request):
    return JsonResponse({"detail": "CSRF cookie set"})


@require_http_methods(["POST"])
def login_view(request):
    data = json.loads(request.body)
    user = authenticate(request, username=data.get("username"), password=data.get("password"))
    if user:
        login(request, user)
        return JsonResponse({
            "id": user.id,
            "username": user.username,
            "is_staff": user.is_staff,
        })
    return JsonResponse({"detail": "Invalid credentials"}, status=400)


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return JsonResponse({"detail": "Logged out"})


def me_view(request):
    if request.user.is_authenticated:
        return JsonResponse({
            "id": request.user.id,
            "username": request.user.username,
            "is_staff": request.user.is_staff,
        })
    return JsonResponse({"detail": "Not authenticated"}, status=401)


urlpatterns = [
    path("csrf/", get_csrf),
    path("login/", login_view),
    path("logout/", logout_view),
    path("me/", me_view),
]
