"""JSON API. Все ошибки возвращаются в одном формате:
{"error": {"code": "...", "message": "понятный текст", "fields": {"поле": "что не так"}}}
"""
import functools
import json
import logging

from django.conf import settings
from django.http import HttpResponse, JsonResponse

from . import features, security, services, validators
from .exceptions import ApiError, StoreError

log = logging.getLogger(__name__)


def error_response(exc: ApiError):
    return JsonResponse({"error": {"code": exc.code, "message": exc.message, "fields": exc.fields}},
                        status=exc.status)


def current_user(request):
    uid = request.session.get("uid")
    user = services.get_user(uid) if uid else None
    if not user:
        request.session.flush()
        raise ApiError("Войдите в аккаунт, чтобы продолжить", 401, "unauthorized")
    if not user.get("is_active", True):
        request.session.flush()
        raise ApiError("Ваш аккаунт заблокирован администратором", 403, "blocked")
    services.touch(uid, user)  # «был в сети» (не чаще раза в минуту)
    return user


def calls_required():
    if not settings.CALLS_ENABLED:
        raise ApiError("Звонки сейчас отключены", 404, "not_found")


def api_view(methods, login=True, admin=False):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(request, *args, **kwargs):
            try:
                if request.method not in methods:
                    raise ApiError("Метод не поддерживается", 405, "method_not_allowed")
                if login:
                    request.me = current_user(request)
                    if admin and not request.me.get("is_admin"):
                        raise ApiError("Недостаточно прав", 403, "forbidden")
                result = fn(request, *args, **kwargs)
                if isinstance(result, HttpResponse):
                    return result
                if isinstance(result, tuple):
                    return JsonResponse(result[0], status=result[1])
                return JsonResponse(result if result is not None else {"ok": True})
            except ApiError as exc:
                return error_response(exc)
            except StoreError:
                log.exception("Firestore error")
                return error_response(ApiError(
                    "База данных временно недоступна. Попробуйте через минуту.", 503, "db_unavailable"))
            except Exception:
                log.exception("Unhandled error in %s", fn.__name__)
                return error_response(ApiError(
                    "Внутренняя ошибка сервера. Мы уже в логах — попробуйте ещё раз.", 500, "server_error"))
        return wrapper
    return decorator


def read_json(request):
    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError
        return data
    except ValueError:
        raise ApiError("Некорректный JSON в запросе", 400, "bad_json")


def profile_form(request):
    form = {k: request.POST.get(k, "") for k in
            ("email", "password", "name", "age", "gender", "looking_for", "bio", "goal")}
    form["interests"] = request.POST.getlist("interests")
    return form


def read_photo(request, required):
    f = request.FILES.get("photo")
    if f is None:
        if required:
            raise ApiError("Загрузите фото", 422, "validation_error", {"photo": "Загрузите фото профиля"})
        return None
    if f.size > validators.MAX_PHOTO_BYTES:
        raise ApiError("Фото слишком большое", 422, "validation_error",
                       {"photo": "Файл больше 5 МБ — выберите фото поменьше"})
    return validators.process_photo(f.read())


def client_ip(request):
    return (request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", ""))


# ---------- служебное ----------
def health(request):
    return HttpResponse("ok")


# ---------- авторизация ----------
@api_view(["POST"], login=False)
def register(request):
    cleaned = validators.validate_registration(profile_form(request), services.interest_names())
    photo = read_photo(request, required=True)
    user = services.create_user(cleaned, photo, settings.ADMIN_EMAILS)
    request.session.flush()
    request.session["uid"] = user["id"]
    return {"user": services.private_profile(user)}, 201


@api_view(["POST"], login=False)
def login(request):
    body = read_json(request)
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or not password:
        raise ApiError("Введите email и пароль", 422, "validation_error",
                       {k: "Обязательное поле" for k, v in (("email", email), ("password", password)) if not v})
    key = f"{email}|{client_ip(request)}"
    if security.login_limiter.blocked(key):
        raise ApiError("Слишком много неудачных попыток. Подождите 10 минут.", 429, "too_many_attempts")
    user = services.get_user_by_email(email)
    if not security.verify_password(password, user["password_hash"] if user else None):
        security.login_limiter.hit(key)
        raise ApiError("Неверный email или пароль", 401, "invalid_credentials")
    if not user.get("is_active", True):
        raise ApiError("Ваш аккаунт заблокирован администратором", 403, "blocked")
    security.login_limiter.reset(key)
    if email in settings.ADMIN_EMAILS and not user.get("is_admin"):
        user = services.make_admin(user["id"])
    request.session.flush()
    request.session["uid"] = user["id"]
    return {"user": services.private_profile(user)}


@api_view(["POST"], login=False)
def logout(request):
    request.session.flush()
    return {"ok": True}


# ---------- профиль ----------
@api_view(["GET"], login=False)
def interests(request):
    return {"interests": services.list_interests()}


@api_view(["GET", "POST", "DELETE"])
def me(request):
    user = request.me
    if request.method == "GET":
        return {"user": services.private_profile(user)}
    if request.method == "POST":
        cleaned = validators.validate_profile(profile_form(request), services.interest_names())
        photo = read_photo(request, required=False)
        return {"user": services.private_profile(services.update_profile(user["id"], cleaned, photo))}
    body = read_json(request)
    if not security.verify_password(body.get("password") or "", user["password_hash"]):
        raise ApiError("Пароль не подошёл — аккаунт не удалён", 403, "invalid_credentials",
                       {"password": "Неверный пароль"})
    services.delete_user_cascade(user["id"])
    request.session.flush()
    return {"ok": True}


@api_view(["GET"])
def photo(request, uid):
    found = services.get_photo(uid)
    if not found:
        raise ApiError("Фото не найдено", 404, "not_found")
    resp = HttpResponse(found[0], content_type=found[1])
    resp["Cache-Control"] = "private, max-age=86400"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


# ---------- лента, свайпы, пары ----------
def _int_param(request, name, default, lo, hi):
    raw = request.GET.get(name)
    if raw in (None, ""):
        return default
    try:
        return max(lo, min(hi, int(raw)))
    except ValueError:
        raise ApiError(f"{name} должен быть числом", 400, "bad_request")


@api_view(["GET"])
def feed(request):
    limit = _int_param(request, "limit", 10, 1, 20)
    age_min, age_max = _int_param(request, "age_min", 18, 18, 99), _int_param(request, "age_max", 99, 18, 99)
    if age_min > age_max:
        raise ApiError("Минимальный возраст больше максимального", 422, "validation_error",
                       {"age_min": "Минимум не может быть больше максимума"})
    filters = {"age_min": age_min, "age_max": age_max,
               "interests": [i.strip() for i in request.GET.get("interests", "").split(",") if i.strip()][:8],
               "goals": [g for g in request.GET.get("goals", "").split(",") if g in validators.GOAL_IDS],
               "with_video": request.GET.get("with_video") == "1", "with_music": request.GET.get("with_music") == "1"}
    return {"profiles": services.feed(request.me["id"], limit, filters)}


@api_view(["POST"])
def swipes(request):
    body = read_json(request)
    target, like = body.get("target_uid"), body.get("like")
    if not isinstance(target, str) or not isinstance(like, bool):
        raise ApiError("Нужны target_uid (строка) и like (true/false)", 400, "bad_request")
    return services.swipe(request.me["id"], target, like)


@api_view(["GET"])
def matches(request):
    return {"matches": services.list_matches(request.me["id"])}


@api_view(["DELETE"])
def match_detail(request, match_id):
    services.unmatch(match_id, request.me["id"])
    return {"ok": True}


@api_view(["GET", "POST"])
def messages(request, match_id):
    uid = request.me["id"]
    if request.method == "GET":
        since = request.GET.get("since")
        try:
            since = float(since) if since not in (None, "") else None
        except ValueError:
            raise ApiError("since должен быть числом", 400, "bad_request")
        return services.chat_poll(match_id, uid, since)
    upload = request.FILES.get("file")
    if upload is not None:  # фото / GIF / видео / голосовое
        if upload.size > 7 * 1024 * 1024:
            raise ApiError("Файл слишком большой", 422, "validation_error", {"file": "Файл слишком большой"})
        msg = services.send_media(match_id, uid, upload.read(), request.POST.get("kind", ""),
                                  request.POST.get("duration", 0), request.POST.get("text", ""))
        return {"message": msg}, 201
    body = read_json(request)
    if body.get("gift"):
        return {"message": services.send_gift(match_id, uid, body["gift"])}, 201
    return {"message": services.send_message(match_id, uid, body.get("text"))}, 201


@api_view(["DELETE"])
def message_detail(request, match_id, message_id):
    services.delete_message(match_id, request.me["id"], message_id)
    return {"ok": True}


@api_view(["GET", "POST"])
def signals(request, match_id):
    calls_required()
    uid = request.me["id"]
    if request.method == "GET":
        try:
            since = float(request.GET.get("since") or 0)
        except ValueError:
            raise ApiError("since должен быть числом", 400, "bad_request")
        return {"signals": services.get_call_signals(match_id, uid, since)}
    body = read_json(request)
    services.post_call_signal(match_id, uid, body.get("kind"), body.get("payload", {}))
    return {"ok": True}, 201


# ---------- медиа, оформление, видео анкеты ----------
@api_view(["GET"])
def media_file(request, media_id):
    meta, data = services.get_media_for(media_id, request.me["id"])
    total, start, end, status = len(data), 0, len(data) - 1, 200
    rng = request.headers.get("Range", "")
    if rng.startswith("bytes=") and total:
        try:
            a, b = rng[6:].split(",")[0].split("-")
            if a == "":
                start = max(0, total - int(b))
            else:
                start, end = int(a), (int(b) if b else total - 1)
            end = min(end, total - 1)
            if start > end:
                raise ValueError
            status = 206
        except ValueError:
            resp = HttpResponse(status=416)
            resp["Content-Range"] = f"bytes */{total}"
            return resp
    resp = HttpResponse(data[start:end + 1], status=status, content_type=meta["content_type"])
    resp["Accept-Ranges"] = "bytes"
    if status == 206:
        resp["Content-Range"] = f"bytes {start}-{end}/{total}"
    resp["Cache-Control"] = "private, max-age=86400"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


@api_view(["POST"])
def me_settings(request):
    return {"user": services.private_profile(services.update_settings(request.me["id"], read_json(request)))}


@api_view(["POST", "DELETE"])
def me_video(request):
    uid = request.me["id"]
    if request.method == "DELETE":
        return {"user": services.private_profile(services.remove_video(uid))}
    f = request.FILES.get("video")
    if f is None:
        raise ApiError("Выберите видео", 422, "validation_error", {"video": "Выберите видеофайл"})
    if f.size > 7 * 1024 * 1024:
        raise ApiError("Видео слишком большое", 422, "validation_error", {"video": "Видео больше 6 МБ"})
    return {"user": services.private_profile(services.set_video(uid, f.read()))}, 201


# ---------- уведомления, подарки, достижения ----------
@api_view(["GET"])
def notifications(request):
    items = services.list_notifications(request.me["id"])
    return {"notifications": items, "unread": len(items)}


@api_view(["POST"])
def notifications_read(request):
    body = read_json(request)
    ids = body.get("ids")
    types = body.get("types")
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
        raise ApiError("ids должен быть списком строк", 400, "bad_request")
    if types is not None and not (isinstance(types, list) and all(isinstance(i, str) for i in types)):
        raise ApiError("types должен быть списком строк", 400, "bad_request")
    match_id = body.get("match_id")
    if ids is None and match_id is None and types is None and body.get("all") is not True:
        raise ApiError("Укажите ids, match_id, types или all", 400, "bad_request")
    features.mark_read(request.me["id"], ids, match_id if isinstance(match_id, str) else None, types)
    return {"ok": True}


@api_view(["GET"])
def ice_servers(request):
    calls_required()
    servers = [{"urls": ["stun:stun.l.google.com:19302", "stun:stun1.l.google.com:19302"]}]
    if settings.TURN_URLS:
        servers.append({"urls": settings.TURN_URLS, "username": settings.TURN_USERNAME,
                        "credential": settings.TURN_CREDENTIAL})
    return {"iceServers": servers}


@api_view(["GET"])
def gifts(request):
    return {"gifts": features.gift_catalog()}


@api_view(["GET"])
def achievements(request):
    items = features.achievement_list(request.me)
    return {"achievements": items if settings.CALLS_ENABLED else [a for a in items if a["id"] != "caller"]}


# ---------- админ-панель ----------
@api_view(["GET"], admin=True)
def admin_stats(request):
    return services.stats()


@api_view(["GET"], admin=True)
def admin_users(request):
    return {"users": services.admin_users()}


@api_view(["PATCH", "DELETE"], admin=True)
def admin_user(request, uid):
    if uid == request.me["id"]:
        raise ApiError("Нельзя изменить или удалить самого себя", 400, "bad_request")
    target = services.get_user(uid)
    if not target:
        raise ApiError("Пользователь не найден", 404, "not_found")
    if target.get("is_admin"):
        raise ApiError("Администратора нельзя заблокировать или удалить из панели", 403, "forbidden")
    if request.method == "DELETE":
        services.delete_user_cascade(uid)
        return {"ok": True}
    body = read_json(request)
    if not isinstance(body.get("is_active"), bool):
        raise ApiError("Нужно поле is_active (true/false)", 400, "bad_request")
    services.set_user_active(uid, body["is_active"])
    return {"ok": True}


@api_view(["POST"], admin=True)
def admin_interests(request):
    return {"interest": services.add_interest(read_json(request).get("name"))}, 201


@api_view(["DELETE"], admin=True)
def admin_interest(request, iid):
    services.delete_interest(iid)
    return {"ok": True}


@api_view(["GET"], admin=True)
def admin_reports(request):
    return {"reports": services.list_reports()}


@api_view(["PATCH"], admin=True)
def admin_report(request, rid):
    services.resolve_report(rid, read_json(request).get("action"))
    return {"ok": True}


# ---------- «кто меня лайкнул», поиск, страница пользователя, посты ----------
@api_view(["GET"])
def likes(request):
    return {"profiles": services.list_likes(request.me["id"])}


@api_view(["GET"])
def search(request):
    age_min, age_max = _int_param(request, "age_min", 18, 18, 99), _int_param(request, "age_max", 99, 18, 99)
    if age_min > age_max:
        raise ApiError("Минимальный возраст больше максимального", 422, "validation_error",
                       {"age_min": "Минимум не может быть больше максимума"})
    goal = request.GET.get("goal", "")
    if goal and goal not in validators.GOAL_IDS:
        raise ApiError("Неизвестная цель знакомства", 422, "validation_error", {"goal": "Выберите из списка"})
    return {"profiles": services.search_users(request.me["id"], request.GET.get("q", ""), age_min, age_max, goal)}


@api_view(["GET"])
def user_view(request, uid):
    return services.profile_view(request.me["id"], uid)


@api_view(["POST"])
def my_posts(request):
    photo = request.FILES.get("photo")
    if photo is not None and photo.size > 7 * 1024 * 1024:
        raise ApiError("Файл слишком большой", 422, "validation_error", {"photo": "Файл больше 7 МБ"})
    post = services.create_post(request.me["id"], request.POST.get("text", ""), photo.read() if photo else None)
    return {"post": post}, 201


@api_view(["DELETE"])
def my_post(request, post_id):
    services.delete_post(request.me["id"], post_id)
    return {"ok": True}


# ---------- чёрный список, жалобы, «печатает» ----------
@api_view(["GET", "POST"])
def blocks(request):
    uid = request.me["id"]
    if request.method == "POST":
        target = read_json(request).get("uid")
        if not isinstance(target, str):
            raise ApiError("Нужно поле uid", 400, "bad_request")
        services.block_user(uid, target)
    return {"blocked": services.list_blocked(uid)}


@api_view(["DELETE"])
def block_detail(request, uid):
    services.unblock_user(request.me["id"], uid)
    return {"blocked": services.list_blocked(request.me["id"])}


@api_view(["POST"])
def reports(request):
    body = read_json(request)
    target = body.get("uid")
    if not isinstance(target, str):
        raise ApiError("Нужно поле uid", 400, "bad_request")
    reason, details, context = validators.validate_report(body)
    services.create_report(request.me["id"], target, reason, details, context, also_block=body.get("block") is True)
    return {"ok": True}, 201


@api_view(["POST"])
def typing(request, match_id):
    services.set_typing(match_id, request.me["id"])
    return {"ok": True}
