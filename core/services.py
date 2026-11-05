"""Бизнес-логика DateMatch. Не зависит от Django — работает поверх core.store.

Коллекции Firestore (связи — через идентификаторы):
  users            — профиль и учётные данные
  photos           — фото профиля (id = id пользователя)
  interests        — справочник интересов (им управляет админ)
  swipes           — лайки/дизлайки (id = "<from>__<to>")
  matches          — пары (id = отсортированные "<a>__<b>")
  matches/<id>/messages — сообщения чата (текст, фото, GIF, видео, голосовые, подарки)
  matches/<id>/signals  — сигналы звонков WebRTC
  media (+ chunks)      — файлы: видео анкеты и вложения чата
  notifications         — уведомления о лайках, парах, сообщениях, звонках, достижениях
  users/<id>/posts      — посты на странице пользователя
  reports               — жалобы на пользователей (разбирает администратор)
"""
import base64
import random
import time

from . import features, media, security, validators
from .exceptions import ApiError
from .store import get_store

DEFAULT_INTERESTS = [
    "Путешествия", "Кино", "Музыка", "Спорт", "Кофе", "Книги", "Игры", "Кулинария",
    "Фотография", "Программирование", "Йога", "Собаки", "Коты", "Походы", "Искусство",
]
_seeded = False


def _now():
    return time.time()


def reset_cache():
    global _seeded
    _seeded = False


# ---------- интересы ----------
def ensure_seed_interests():
    global _seeded
    if _seeded:
        return
    st = get_store()
    if not st.query("interests", limit=1):
        for name in DEFAULT_INTERESTS:
            st.set("interests", st.new_id(), {"name": name, "created_at": _now()})
    _seeded = True


def list_interests():
    ensure_seed_interests()
    items = get_store().query("interests", order_by="name")
    return [{"id": i["id"], "name": i["name"]} for i in items]


def interest_names():
    return [i["name"] for i in list_interests()]


def add_interest(raw_name):
    try:
        name = validators.clean_interest_name(raw_name)
    except validators._Bad as exc:
        raise ApiError(str(exc), 422, "validation_error", {"name": str(exc)})
    if name.lower() in {n.lower() for n in interest_names()}:
        raise ApiError("Такой интерес уже есть", 409, "duplicate", {"name": "Такой интерес уже есть"})
    st = get_store()
    iid = st.new_id()
    st.set("interests", iid, {"name": name, "created_at": _now()})
    return {"id": iid, "name": name}


def delete_interest(iid):
    st = get_store()
    if not st.get("interests", iid):
        raise ApiError("Интерес не найден", 404, "not_found")
    st.delete("interests", iid)


# ---------- пользователи ----------
def get_user(uid):
    return get_store().get("users", uid) if uid else None


def get_user_by_email(email):
    found = get_store().query("users", [("email", "==", email)], limit=1)
    return found[0] if found else None


def photo_url(u):
    return f"/photo/{u['id']}/?v={int(u.get('photo_updated_at', 0))}"


def public_profile(u):
    return {"uid": u["id"], "name": u["name"], "age": u["age"], "bio": u.get("bio", ""),
            "interests": u.get("interests", []), "photo_url": photo_url(u),
            "video_url": f"/media/{u['video_id']}/" if u.get("video_id") else "",
            "music_title": u.get("music_title", ""), "music_url": u.get("music_url", ""),
            "accent": u.get("accent", ""), "status": u.get("status", ""),
            "goal": u.get("goal", "unsure"), "goal_title": validators.GOAL_TITLES.get(u.get("goal", "unsure"), ""),
            **presence(u), "badges": features.badges(u)}


def private_profile(u):
    return {**public_profile(u), "email": u["email"], "gender": u["gender"],
            "looking_for": u["looking_for"], "is_admin": bool(u.get("is_admin")),
            "hidden": bool(u.get("hidden")), "hide_online": bool(u.get("hide_online")),
            "blocked_count": len(u.get("blocked_uids") or []), "created_at": u.get("created_at")}


def _save_photo(uid, jpeg_bytes):
    ts = _now()
    get_store().set("photos", uid, {
        "data": base64.b64encode(jpeg_bytes).decode(), "content_type": "image/jpeg", "updated_at": ts})
    return ts


def get_photo(uid):
    doc = get_store().get("photos", uid)
    return (base64.b64decode(doc["data"]), doc["content_type"]) if doc else None


def create_user(cleaned, jpeg_bytes, admin_emails=()):
    if get_user_by_email(cleaned["email"]):
        raise ApiError("Этот email уже зарегистрирован", 409, "duplicate",
                       {"email": "Этот email уже зарегистрирован — попробуйте войти"})
    st = get_store()
    uid = st.new_id()
    ts = _save_photo(uid, jpeg_bytes)
    st.set("users", uid, {
        "email": cleaned["email"], "password_hash": security.hash_password(cleaned["password"]),
        "name": cleaned["name"], "age": cleaned["age"], "gender": cleaned["gender"],
        "looking_for": cleaned["looking_for"], "bio": cleaned["bio"], "interests": cleaned["interests"],
        "goal": cleaned.get("goal", "unsure"), "hide_online": False, "blocked_uids": [], "last_seen": ts,
        "is_admin": cleaned["email"] in admin_emails, "is_active": True,
        "created_at": ts, "photo_updated_at": ts,
    })
    return get_user(uid)


def update_profile(uid, cleaned, jpeg_bytes=None):
    patch = dict(cleaned)
    if jpeg_bytes:
        patch["photo_updated_at"] = _save_photo(uid, jpeg_bytes)
    get_store().update("users", uid, patch)
    return get_user(uid)


def delete_user_cascade(uid):
    st = get_store()
    for s in st.query("swipes", [("from_uid", "==", uid)]) + st.query("swipes", [("to_uid", "==", uid)]):
        st.delete("swipes", s["id"])
    for m in st.query("matches", [("users", "array_contains", uid)]):
        _delete_match(m["id"])
    media.delete_where("owner", uid)
    for p in st.query(f"users/{uid}/posts"):
        st.delete(f"users/{uid}/posts", p["id"])
    for r in st.query("reports", [("target_uid", "==", uid)]) + st.query("reports", [("from_uid", "==", uid)]):
        st.delete("reports", r["id"])
    features.delete_user_notifications(uid)
    st.delete("photos", uid)
    st.delete("users", uid)


def make_admin(uid):
    get_store().update("users", uid, {"is_admin": True})
    return get_user(uid)


def set_user_active(uid, active):
    if not get_user(uid):
        raise ApiError("Пользователь не найден", 404, "not_found")
    get_store().update("users", uid, {"is_active": bool(active)})


def update_settings(uid, body):
    patch = validators.validate_settings(body)
    if patch:
        get_store().update("users", uid, patch)
        features.bump(uid)  # «Полная анкета» может выдаться после смены оформления
    return get_user(uid)


def set_video(uid, raw):
    ctype = media.classify_profile_video(raw)
    user = get_user(uid)
    new_id = media.save(uid, "video", ctype, raw, public=True)
    get_store().update("users", uid, {"video_id": new_id})
    media.delete(user.get("video_id"))
    features.bump(uid)
    return get_user(uid)


def remove_video(uid):
    user = get_user(uid)
    get_store().update("users", uid, {"video_id": ""})
    media.delete(user.get("video_id"))
    return get_user(uid)


def get_media_for(media_id, uid):
    """Файл отдаётся только тем, кому он предназначен: участникам пары или (для видео анкеты) всем вошедшим."""
    meta, data = media.load(media_id)
    if not meta:
        raise ApiError("Файл не найден", 404, "not_found")
    if meta.get("match_id"):
        get_match_for(meta["match_id"], uid)
    elif not meta.get("public") and meta.get("owner") != uid:
        raise ApiError("Файл не найден", 404, "not_found")
    return meta, data


# ---------- лента и свайпы ----------
def _wants(user, other):
    return user["looking_for"] in ("everyone", other["gender"])


def feed(uid, limit=10, filters=None):
    """filters: age_min, age_max, interests (список названий, подходит любой), goals, with_video, with_music."""
    f = filters or {}
    st = get_store()
    me = get_user(uid)
    swiped = {s["to_uid"] for s in st.query("swipes", [("from_uid", "==", uid)])}
    pool = st.query("users", [("is_active", "==", True)], limit=500)
    wanted = {i.lower() for i in f.get("interests", [])}
    goals = set(f.get("goals") or [])
    blocked_me = blocked_ids(me)

    def ok(u):
        if u["id"] == uid or u["id"] in swiped or u.get("hidden") or not (_wants(me, u) and _wants(u, me)):
            return False
        if u["id"] in blocked_me or uid in blocked_ids(u):
            return False
        if goals and u.get("goal", "unsure") not in goals:
            return False
        if u["age"] < f.get("age_min", 18) or u["age"] > f.get("age_max", 99):
            return False
        if wanted and not wanted & {i.lower() for i in u.get("interests", [])}:
            return False
        if f.get("with_video") and not u.get("video_id"):
            return False
        return not (f.get("with_music") and not u.get("music_title"))

    cands = [u for u in pool if ok(u)]
    random.shuffle(cands)
    return [public_profile(u) for u in cands[:limit]]


def swipe(uid, target_uid, like):
    if uid == target_uid:
        raise ApiError("Нельзя оценивать свой профиль", 400, "bad_request")
    target = get_user(target_uid)
    if not target or not target.get("is_active", True):
        raise ApiError("Этот профиль больше недоступен", 404, "not_found")
    if _blocked_either(get_user(uid), target):
        raise ApiError("Этот профиль больше недоступен", 404, "not_found")
    st = get_store()
    prev = st.get("swipes", f"{uid}__{target_uid}")
    first_like = bool(like) and not (prev and prev.get("like"))
    st.set("swipes", f"{uid}__{target_uid}",
           {"from_uid": uid, "to_uid": target_uid, "like": bool(like), "created_at": _now()})
    result = {"matched": False}
    if not like:
        return result
    me = get_user(uid)
    back = st.get("swipes", f"{target_uid}__{uid}")
    if back and back.get("like"):
        mid = "__".join(sorted([uid, target_uid]))
        if not st.get("matches", mid):
            st.set("matches", mid, {"users": [uid, target_uid], "created_at": _now(),
                                    "last_message": "", "last_message_at": 0, "deleted_ids": []})
            features.drop_notification(uid, "like", target_uid)
            features.notify(target_uid, "match", f"Новая пара: {me['name']}!", key=mid, from_uid=uid,
                            from_name=me["name"], from_photo=photo_url(me), match_id=mid)
            features.bump(uid, likes_given=1, matches=1)
            features.bump(target_uid, matches=1)
        result = {"matched": True, "match_id": mid, "profile": public_profile(target)}
    elif first_like:
        features.notify(target_uid, "like", "Кто-то поставил вам лайк", key=uid)
        features.bump(uid, likes_given=1)
        features.bump(target_uid, likes_received=1)
    return result


# ---------- пары и чат ----------
def _delete_match(mid):
    st = get_store()
    for msg in st.query(f"matches/{mid}/messages"):
        st.delete(f"matches/{mid}/messages", msg["id"])
    features.clear_signals(mid)
    media.delete_where("match_id", mid)
    st.delete("matches", mid)


def get_match_for(mid, uid):
    m = get_store().get("matches", mid)
    if not m or uid not in m["users"]:
        raise ApiError("Пара не найдена — возможно, её уже удалили", 404, "not_found")
    return m


def list_matches(uid):
    items = []
    for m in get_store().query("matches", [("users", "array_contains", uid)]):
        other_id = next(x for x in m["users"] if x != uid)
        other = get_user(other_id)
        if not other:
            continue
        items.append({"id": m["id"], "other": public_profile(other),
                      "last_message": m.get("last_message", ""),
                      "sort": m.get("last_message_at") or m["created_at"]})
    items.sort(key=lambda x: x["sort"], reverse=True)
    return items


def other_in_match(match, uid):
    return get_user(next(x for x in match["users"] if x != uid))


def unmatch(mid, uid):
    get_match_for(mid, uid)
    _delete_match(mid)


def _message_view(m, uid):
    gift = features.GIFTS.get(m.get("gift", ""))
    deleted = bool(m.get("deleted"))
    return {"id": m["id"], "mine": m["sender"] == uid, "type": "text" if deleted else m.get("type", "text"),
            "text": "" if deleted else m.get("text", ""), "deleted": deleted,
            "media_url": f"/media/{m['media_id']}/" if m.get("media_id") and not deleted else "",
            "duration": m.get("duration", 0),
            "gift": {"id": m["gift"], "icon": gift[0], "title": gift[1]} if gift and not deleted else None,
            "created_at": m["created_at"]}


def list_messages(mid, uid, since=None, with_deleted=False, match=None):
    """Сообщения пары. С with_deleted=True вернёт ещё и id удалённых (берутся из документа пары — одно чтение)."""
    match = match or get_match_for(mid, uid)
    st = get_store()
    path = f"matches/{mid}/messages"
    if since is None:
        msgs = list(reversed(st.query(path, order_by="created_at", descending=True, limit=100)))
    else:
        msgs = st.query(path, [("created_at", ">", since)], order_by="created_at", limit=200)
    views = [_message_view(m, uid) for m in msgs]
    return (views, match.get("deleted_ids", [])) if with_deleted else views


PREVIEW = {"image": "Фото", "gif": "GIF", "video": "Видео", "voice": "Голосовое сообщение"}


def _store_message(mid, uid, doc, preview, counters):
    """Общая часть: запись сообщения, обновление пары, уведомление собеседнику, счётчики достижений."""
    match = get_match_for(mid, uid)
    st = get_store()
    ts = _now()
    msg_id = st.new_id()
    st.set(f"matches/{mid}/messages", msg_id, {"sender": uid, "created_at": ts, **doc})
    st.update("matches", mid, {"last_message": preview[:80], "last_message_at": ts, "last_sender": uid,
                               f"typing_{uid}": 0})
    other_id = next(x for x in match["users"] if x != uid)
    me = get_user(uid)
    features.notify(other_id, "message", f"{me['name']}: {preview[:80]}", key=msg_id, from_uid=uid,
                    from_name=me["name"], from_photo=photo_url(me), match_id=mid)
    features.bump(uid, messages_sent=1, **counters)
    if "gifts_sent" in counters:
        features.bump(other_id, gifts_received=1)
    return _message_view({"id": msg_id, "sender": uid, "created_at": ts, **doc}, uid)


def send_message(mid, uid, raw_text):
    try:
        text = validators.clean_message(raw_text)
    except validators._Bad as exc:
        raise ApiError(str(exc), 422, "validation_error", {"text": str(exc)})
    return _store_message(mid, uid, {"type": "text", "text": text}, text, {})


def send_gift(mid, uid, gift_id):
    gift = features.GIFTS.get(gift_id)
    if not gift:
        raise ApiError("Такого подарка нет", 422, "validation_error", {"gift": "Выберите подарок из списка"})
    return _store_message(mid, uid, {"type": "gift", "gift": gift_id, "text": ""},
                          f"{gift[0]} Подарок: {gift[1]}", {"gifts_sent": 1})


def send_media(mid, uid, raw, hint="", duration=0, caption=""):
    get_match_for(mid, uid)  # не принимаем файлы для чужих пар
    kind, ctype, data = media.classify_chat(raw, hint)
    try:
        caption = validators.clean_message(caption) if (caption or "").strip() else ""
    except validators._Bad as exc:
        raise ApiError(str(exc), 422, "validation_error", {"text": str(exc)})
    media_id = media.save(uid, kind, ctype, data, match_id=mid)
    counters = {"voice_sent": 1} if kind == "voice" else {"media_sent": 1}
    doc = {"type": kind, "text": caption, "media_id": media_id,
           "duration": validators.clean_duration(duration) if kind == "voice" else 0}
    return _store_message(mid, uid, doc, caption or PREVIEW[kind], counters)


def delete_message(mid, uid, msg_id):
    """Удалять можно только своё. Файл стирается, у собеседника сообщение превращается в «удалено»."""
    match = get_match_for(mid, uid)
    st = get_store()
    path = f"matches/{mid}/messages"
    msg = st.get(path, msg_id)
    if not msg:
        raise ApiError("Сообщение не найдено", 404, "not_found")
    if msg["sender"] != uid:
        raise ApiError("Можно удалять только свои сообщения", 403, "forbidden")
    if msg.get("deleted"):
        return
    media.delete(msg.get("media_id"))
    st.update(path, msg_id, {"deleted": True, "text": "", "media_id": "", "gift": "", "type": "text"})
    other_id = next(x for x in match["users"] if x != uid)
    features.drop_notification(other_id, "message", msg_id)
    patch = {"deleted_ids": (match.get("deleted_ids", []) + [msg_id])[-100:]}
    if match.get("last_message_at") == msg["created_at"]:
        patch["last_message"] = "Сообщение удалено"
    st.update("matches", mid, patch)


# ---------- звонки ----------
def post_call_signal(mid, uid, kind, payload):
    match = get_match_for(mid, uid)
    other = other_in_match(match, uid)
    if not other:
        raise ApiError("Собеседник больше недоступен", 404, "not_found")
    me = get_user(uid)
    features.post_signal(mid, uid, other["id"], kind, payload)
    if kind == "offer":
        video = isinstance(payload, dict) and bool(payload.get("video"))
        features.notify(other["id"], "call", f"{me['name']} звонит вам" + (" (видео)" if video else ""),
                        key=mid, from_uid=uid, from_name=me["name"], from_photo=photo_url(me), match_id=mid,
                        data={"video": video})
    elif kind in ("hangup", "decline"):
        features.drop_notification(other["id"], "call", mid)
        features.drop_notification(uid, "call", mid)
    elif kind == "answer":
        features.drop_notification(uid, "call", mid)
        features.bump(uid, calls=1)
        features.bump(other["id"], calls=1)


def get_call_signals(mid, uid, since):
    get_match_for(mid, uid)
    return features.get_signals(mid, uid, since)


# ---------- присутствие («в сети») ----------
ONLINE_WINDOW = 120  # секунд: столько после последнего запроса человек считается «в сети»


def presence(u, now=None):
    """{'online': bool, 'last_seen': ts|None}. Если человек скрыл статус, о нём ничего не известно."""
    if u.get("hide_online"):
        return {"online": False, "last_seen": None}
    ts = u.get("last_seen") or 0
    return {"online": bool(ts) and (now or _now()) - ts < ONLINE_WINDOW, "last_seen": ts or None}


def touch(uid, user=None):
    """Обновляет «был в сети» не чаще раза в минуту, чтобы не тратить записи Firestore."""
    u = user or get_user(uid)
    if u and _now() - (u.get("last_seen") or 0) > 60:
        get_store().update("users", uid, {"last_seen": _now()})


# ---------- чёрный список ----------
MAX_BLOCKED = 200


def blocked_ids(u):
    return set(u.get("blocked_uids") or [])


def _blocked_either(a, b):
    """Заблокировал ли кто-то из двоих другого (a, b — документы пользователей)."""
    return b["id"] in blocked_ids(a) or a["id"] in blocked_ids(b)


def block_user(uid, target_uid):
    if uid == target_uid:
        raise ApiError("Нельзя заблокировать самого себя", 400, "bad_request")
    if not get_user(target_uid):
        raise ApiError("Пользователь не найден", 404, "not_found")
    me = get_user(uid)
    lst = list(me.get("blocked_uids") or [])
    if target_uid not in lst:
        if len(lst) >= MAX_BLOCKED:
            raise ApiError("Чёрный список переполнен (максимум 200)", 422, "validation_error")
        lst.append(target_uid)
        get_store().update("users", uid, {"blocked_uids": lst})
    mid = "__".join(sorted([uid, target_uid]))
    if get_store().get("matches", mid):
        _delete_match(mid)  # переписка и пара исчезают у обоих


def unblock_user(uid, target_uid):
    me = get_user(uid)
    lst = [x for x in (me.get("blocked_uids") or []) if x != target_uid]
    get_store().update("users", uid, {"blocked_uids": lst})


def list_blocked(uid):
    out = []
    for tid in get_user(uid).get("blocked_uids") or []:
        u = get_user(tid)
        if u:
            out.append({"uid": tid, "name": u["name"], "photo_url": photo_url(u)})
    return out


# ---------- «кто меня лайкнул» и поиск ----------
def list_likes(uid, limit=50):
    """Люди, которые лайкнули вас, а вы им ещё не ответили."""
    st = get_store()
    me = get_user(uid)
    answered = {s["to_uid"] for s in st.query("swipes", [("from_uid", "==", uid)])}
    likes = st.query("swipes", [("to_uid", "==", uid), ("like", "==", True)])
    likes.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    out = []
    for s in likes:
        if s["from_uid"] in answered:
            continue
        u = get_user(s["from_uid"])
        if not u or not u.get("is_active", True) or _blocked_either(me, u):
            continue
        out.append({**public_profile(u), "liked_at": s.get("created_at")})
        if len(out) >= limit:
            break
    return out


def search_users(uid, q="", age_min=18, age_max=99, goal="", limit=30):
    """Поиск по имени и интересам. Скрытые анкеты и заблокированные не показываются."""
    me = get_user(uid)
    qn = validators.clean_search_query(q).casefold()
    found = []
    for u in get_store().query("users", [("is_active", "==", True)], limit=500):
        if u["id"] == uid or u.get("hidden") or _blocked_either(me, u):
            continue
        if not age_min <= u["age"] <= age_max or (goal and u.get("goal", "unsure") != goal):
            continue
        if qn and qn not in u["name"].casefold() and not any(qn in i.casefold() for i in u.get("interests", [])):
            continue
        found.append(u)
    found.sort(key=lambda u: (not presence(u)["online"], u["name"].casefold()))
    return [public_profile(u) for u in found[:limit]]


# ---------- страница пользователя и посты ----------
MAX_POSTS = 50


def _post_view(p):
    return {"id": p["id"], "text": p.get("text", ""), "created_at": p["created_at"],
            "image_url": f"/media/{p['media_id']}/" if p.get("media_id") else ""}


def list_posts(uid, limit=20):
    return [_post_view(p) for p in
            get_store().query(f"users/{uid}/posts", order_by="created_at", descending=True, limit=limit)]


def create_post(uid, raw_text, raw_photo=None):
    try:
        text = validators.clean_post_text(raw_text)
    except validators._Bad as exc:
        raise ApiError(str(exc), 422, "validation_error", {"text": str(exc)})
    if not text and not raw_photo:
        raise ApiError("Напишите что-нибудь или прикрепите фото", 422, "validation_error",
                       {"text": "Напишите что-нибудь или прикрепите фото"})
    st, path = get_store(), f"users/{uid}/posts"
    if len(st.query(path, limit=MAX_POSTS + 1)) >= MAX_POSTS:
        raise ApiError("Слишком много постов — удалите старые (максимум 50)", 422, "validation_error")
    media_id = ""
    if raw_photo:
        kind, ctype, data = media.classify_chat(raw_photo, "")
        if kind not in ("image", "gif"):
            raise ApiError("К посту можно прикрепить только фото или GIF", 422, "validation_error",
                           {"photo": "К посту можно прикрепить только фото или GIF"})
        media_id = media.save(uid, "post", ctype, data, public=True)
    pid = st.new_id()
    doc = {"text": text, "media_id": media_id, "created_at": _now()}
    st.set(path, pid, doc)
    return _post_view({"id": pid, **doc})


def delete_post(uid, post_id):
    st, path = get_store(), f"users/{uid}/posts"
    post = st.get(path, post_id)
    if not post:
        raise ApiError("Пост не найден", 404, "not_found")
    media.delete(post.get("media_id"))
    st.delete(path, post_id)


def matches_posts(uid, limit=30, per_user=5):
    """Лента постов: свежие посты людей, с которыми у вас есть пара, и ваши собственные."""
    me = get_user(uid)
    authors = [{"uid": uid, "name": me["name"], "photo_url": photo_url(me), "mine": True}]
    for m in list_matches(uid):
        o = m["other"]
        authors.append({"uid": o["uid"], "name": o["name"], "photo_url": o["photo_url"], "mine": False})
    items = []
    for a in authors:
        for p in list_posts(a["uid"], per_user):
            items.append({**p, "author": a})
    items.sort(key=lambda p: p["created_at"], reverse=True)
    return items[:limit]


def profile_view(viewer_uid, target_uid):
    """Страница пользователя: анкета, посты и отношения между вами (пара, лайки)."""
    viewer, target = get_user(viewer_uid), get_user(target_uid)
    if not target or not target.get("is_active", True):
        raise ApiError("Анкета не найдена", 404, "not_found")
    rel = {"me": viewer_uid == target_uid, "matched": False, "match_id": None,
           "i_liked": False, "i_passed": False, "liked_me": False}
    if not rel["me"]:
        if _blocked_either(viewer, target):
            raise ApiError("Анкета не найдена", 404, "not_found")
        st = get_store()
        mine = st.get("swipes", f"{viewer_uid}__{target_uid}")
        theirs = st.get("swipes", f"{target_uid}__{viewer_uid}")
        mid = "__".join(sorted([viewer_uid, target_uid]))
        matched = bool(st.get("matches", mid))
        rel.update(matched=matched, match_id=mid if matched else None, i_liked=bool(mine and mine.get("like")),
                   i_passed=bool(mine and not mine.get("like")), liked_me=bool(theirs and theirs.get("like")))
        if target.get("hidden") and not (matched or rel["liked_me"] or viewer.get("is_admin")):
            raise ApiError("Анкета не найдена", 404, "not_found")  # скрытая анкета видна только парам и тем, кого лайкнули вы
    return {"profile": public_profile(target), "relation": rel, "posts": list_posts(target_uid)}


# ---------- жалобы ----------
def create_report(uid, target_uid, reason, details, context, also_block=False):
    if uid == target_uid:
        raise ApiError("Нельзя пожаловаться на самого себя", 400, "bad_request")
    if not get_user(target_uid):
        raise ApiError("Пользователь не найден", 404, "not_found")
    get_store().set("reports", f"{uid}__{target_uid}", {
        "from_uid": uid, "target_uid": target_uid, "reason": reason, "details": details,
        "context": context, "status": "open", "created_at": _now()})
    if also_block:
        block_user(uid, target_uid)


def list_reports(status="open"):
    st = get_store()
    items = st.query("reports", [("status", "==", status)])
    items.sort(key=lambda r: r["created_at"], reverse=True)
    out = []
    for r in items[:100]:
        target, sender = get_user(r["target_uid"]), get_user(r["from_uid"])
        if not target:
            st.delete("reports", r["id"])
            continue
        out.append({"id": r["id"], "reason": r["reason"], "reason_title": validators.REPORT_REASONS.get(r["reason"], ""),
                    "details": r.get("details", ""), "context": r.get("context", "profile"),
                    "created_at": r["created_at"], "from_name": sender["name"] if sender else "(удалён)",
                    "target": {"uid": target["id"], "name": target["name"], "email": target["email"],
                               "is_active": target.get("is_active", True), "is_admin": bool(target.get("is_admin"))}})
    return out


def resolve_report(rid, action):
    st = get_store()
    report = st.get("reports", rid)
    if not report:
        raise ApiError("Жалоба не найдена", 404, "not_found")
    if action == "block":
        target = get_user(report["target_uid"])
        if target and target.get("is_admin"):
            raise ApiError("Администратора нельзя заблокировать из жалобы", 403, "forbidden")
        if target:
            set_user_active(report["target_uid"], False)
    elif action != "dismiss":
        raise ApiError("Действие: block или dismiss", 400, "bad_request")
    st.update("reports", rid, {"status": "closed", "resolution": action})


# ---------- статусы сообщений, «печатает», уведомления ----------
def chat_poll(mid, uid, since=None):
    """Всё, что нужно открытому чату за один запрос: новые сообщения, удалённые, статусы, «печатает», «в сети»."""
    match = get_match_for(mid, uid)
    views, deleted = list_messages(mid, uid, since, with_deleted=True, match=match)
    other_id = next(x for x in match["users"] if x != uid)
    other = get_user(other_id)
    st, now = get_store(), _now()
    if match.get("last_sender") not in (None, uid) and match.get(f"read_at_{uid}", 0) < match.get("last_message_at", 0):
        st.update("matches", mid, {f"read_at_{uid}": now, f"delivered_at_{uid}": now})  # собеседнику: «прочитано»
    read_at = match.get(f"read_at_{other_id}", 0)
    return {"messages": views, "deleted": deleted,
            "receipts": {"read_at": read_at, "delivered_at": max(match.get(f"delivered_at_{other_id}", 0), read_at)},
            "typing": now - match.get(f"typing_{other_id}", 0) < 6,
            "other": presence(other) if other else {"online": False, "last_seen": None}}


def set_typing(mid, uid):
    match = get_match_for(mid, uid)
    if _now() - match.get(f"typing_{uid}", 0) >= 2:
        get_store().update("matches", mid, {f"typing_{uid}": _now()})


def list_notifications(uid):
    """Уведомления + отметка «доставлено»: когда клиент получил уведомление о сообщении, отправителю ставится вторая галочка."""
    items = features.list_notifications(uid)
    st, now, seen = get_store(), _now(), set()
    for n in items:
        if n["type"] == "message" and n.get("match_id") and not n.get("delivered"):
            st.update("notifications", n["id"], {"delivered": True})
            if n["match_id"] not in seen:
                seen.add(n["match_id"])
                m = st.get("matches", n["match_id"])
                if m and uid in m["users"]:
                    st.update("matches", n["match_id"], {f"delivered_at_{uid}": now})
    return items


# ---------- админка ----------
def stats():
    st = get_store()
    users = st.query("users")
    return {"users": len(users), "active_users": sum(1 for u in users if u.get("is_active", True)),
            "matches": len(st.query("matches")), "swipes": len(st.query("swipes")),
            "interests": len(list_interests()), "reports_open": len(st.query("reports", [("status", "==", "open")]))}


def admin_users():
    users = get_store().query("users", order_by="created_at", descending=True, limit=500)
    return [{"uid": u["id"], "email": u["email"], "name": u["name"], "age": u["age"],
             "is_active": u.get("is_active", True), "is_admin": bool(u.get("is_admin")),
             "created_at": u.get("created_at")} for u in users]
