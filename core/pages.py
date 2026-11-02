"""HTML-страницы. Данные на них подгружаются через JSON API (static/js)."""
from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from . import services
from .exceptions import StoreError


def _me(request):
    uid = request.session.get("uid")
    if not uid:
        return None
    try:
        user = services.get_user(uid)
    except StoreError:
        return None
    if not user or not user.get("is_active", True):
        request.session.flush()
        return None
    return user


def _page(template, auth=True, admin=False):
    def decorator(fn):
        def view(request, *args, **kwargs):
            user = _me(request)
            if auth and not user:
                return redirect("/login/")
            if not auth and user:
                return redirect("/discover/")
            if admin and not user.get("is_admin"):
                return render(request, "error.html", {"status": 403, "title": "Нет доступа",
                              "text": "Админ-панель доступна только администраторам."}, status=403)
            ctx = {"me": user, "my_photo": services.photo_url(user) if user else "",
                   "calls_enabled": settings.CALLS_ENABLED,
                   **(fn(request, user, *args, **kwargs) or {})}
            return render(request, template, ctx)
        return view
    return decorator


@_page("landing.html", auth=False)
def landing(request, user):
    return {}


@_page("register.html", auth=False)
def register_page(request, user):
    return {}


@_page("login.html", auth=False)
def login_page(request, user):
    return {}


@_page("discover.html")
def discover_page(request, user):
    return {}


@_page("matches.html")
def matches_page(request, user):
    return {}


@_page("profile.html")
def profile_page(request, user):
    return {}


@_page("likes.html")
def likes_page(request, user):
    return {}


@_page("search.html")
def search_page(request, user):
    return {}


@_page("user.html")
def user_page(request, user, uid):
    return {"target_uid": uid, "is_me": uid == user["id"]}


@_page("panel.html", admin=True)
def panel_page(request, user):
    return {}


@_page("chat.html")
def chat_page(request, user, match_id):
    try:
        match = services.get_match_for(match_id, user["id"])
    except Exception:
        return {"missing": True}
    return {"match_id": match_id, "other": services.public_profile(services.other_in_match(match, user["id"]))}
