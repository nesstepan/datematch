"""Подарки, достижения, уведомления и сигналы звонков. Работает поверх core.store."""
import json
import threading
import time

from .exceptions import ApiError
from .store import get_store

# ---------- виртуальные подарки (бесплатные, оплаты нет) ----------
GIFTS = {
    "rose": ("g-rose", "Роза"), "teddy": ("g-teddy", "Мишка"), "choco": ("g-choco", "Шоколадка"), "coffee": ("g-coffee", "Кофе"),
    "cake": ("g-cake", "Торт"), "diamond": ("g-diamond", "Бриллиант"), "clover": ("g-clover", "Клевер на удачу"),
    "surprise": ("g-surprise", "Сюрприз"),
}


def gift_catalog():
    return [{"id": k, "icon": v[0], "title": v[1]} for k, v in GIFTS.items()]


# ---------- достижения ----------
def _s(u, key):
    return (u.get("stats") or {}).get(key, 0)


ACHIEVEMENTS = [  # id, имя иконки из спрайта, название, как получить, условие
    ("first_like", "heart", "Первый лайк", "Поставьте первый лайк", lambda u: _s(u, "likes_given") >= 1),
    ("first_match", "hearts", "Первая пара", "Получите первую взаимную симпатию", lambda u: _s(u, "matches") >= 1),
    ("matches_5", "flame", "Душа компании", "Наберите 5 пар", lambda u: _s(u, "matches") >= 5),
    ("popular", "star", "Популярный", "Получите 10 лайков", lambda u: _s(u, "likes_received") >= 10),
    ("icebreaker", "snowflake", "Ледокол", "Отправьте первое сообщение", lambda u: _s(u, "messages_sent") >= 1),
    ("chatterbox", "chat", "Болтун", "Отправьте 50 сообщений", lambda u: _s(u, "messages_sent") >= 50),
    ("voice", "mic", "Голос сердца", "Отправьте голосовое сообщение", lambda u: _s(u, "voice_sent") >= 1),
    ("paparazzi", "camera", "Фотограф", "Отправьте 5 фото, видео или GIF", lambda u: _s(u, "media_sent") >= 5),
    ("gift_giver", "gift", "Щедрая душа", "Подарите виртуальный подарок", lambda u: _s(u, "gifts_sent") >= 1),
    ("gift_fav", "g-teddy", "Любимчик", "Получите 3 подарка", lambda u: _s(u, "gifts_received") >= 3),
    ("on_camera", "film", "В кадре", "Добавьте видео в анкету", lambda u: bool(u.get("video_id"))),
    ("caller", "phone", "На связи", "Поговорите по звонку", lambda u: _s(u, "calls") >= 1),
    ("full_profile", "trophy", "Полная анкета", "О себе, видео, музыка и свой цвет оформления",
     lambda u: bool(u.get("bio") and u.get("video_id") and u.get("music_title") and u.get("accent"))),
]
_BY_ID = {a[0]: a for a in ACHIEVEMENTS}


def badges(user):
    return [{"id": i, "icon": _BY_ID[i][1], "title": _BY_ID[i][2]}
            for i in user.get("achievements", []) if i in _BY_ID]


def achievement_list(user):
    got = set(user.get("achievements", []))
    return [{"id": a[0], "icon": a[1], "title": a[2], "desc": a[3], "earned": a[0] in got} for a in ACHIEVEMENTS]


def bump(uid, **inc):
    """Увеличивает счётчики пользователя и выдаёт новые достижения. Вызывать без аргументов, чтобы только перепроверить."""
    st = get_store()
    u = st.get("users", uid)
    if not u:
        return []
    stats = dict(u.get("stats") or {})
    for k, v in inc.items():
        stats[k] = stats.get(k, 0) + v
    u["stats"] = stats
    earned = list(u.get("achievements", []))
    new = [a for a in ACHIEVEMENTS if a[0] not in earned and a[4](u)]
    patch = {"stats": stats}
    if new:
        patch["achievements"] = earned + [a[0] for a in new]
    st.update("users", uid, patch)
    for a in new:
        notify(uid, "achievement", f"Достижение: {a[1]} {a[2]}", key=a[0])
    return [a[0] for a in new]


# ---------- уведомления ----------
def notify(to_uid, ntype, text, key, from_uid="", from_name="", from_photo="", match_id="", data=None):
    get_store().set("notifications", f"{ntype}__{to_uid}__{key}", {
        "to_uid": to_uid, "type": ntype, "text": text, "from_uid": from_uid, "from_name": from_name,
        "from_photo": from_photo, "match_id": match_id, "data": data or {}, "created_at": time.time()})


def list_notifications(uid):
    items = get_store().query("notifications", [("to_uid", "==", uid)])
    items.sort(key=lambda n: n["created_at"], reverse=True)
    return [{"id": n["id"], "type": n["type"], "text": n["text"], "from_name": n.get("from_name", ""),
             "photo_url": n.get("from_photo", ""), "match_id": n.get("match_id", ""),
             "data": n.get("data", {}), "created_at": n["created_at"],
             "delivered": bool(n.get("delivered"))} for n in items[:50]]


def mark_read(uid, ids=None, match_id=None, types=None):
    """Прочитанное уведомление просто удаляется — коллекция остаётся маленькой."""
    st = get_store()
    for n in st.query("notifications", [("to_uid", "==", uid)]):
        if ids is not None and n["id"] not in ids:
            continue
        if match_id is not None and n.get("match_id") != match_id:
            continue
        if types is not None and n["type"] not in types:
            continue
        st.delete("notifications", n["id"])


def drop_notification(to_uid, ntype, key):
    get_store().delete("notifications", f"{ntype}__{to_uid}__{key}")


def delete_user_notifications(uid):
    st = get_store()
    for n in st.query("notifications", [("to_uid", "==", uid)]) + st.query("notifications", [("from_uid", "==", uid)]):
        st.delete("notifications", n["id"])


# ---------- сигналы звонков (WebRTC) ----------
SIGNAL_KINDS = ("offer", "answer", "candidate", "hangup", "decline")
_ts_lock = threading.Lock()
_last_ts = 0.0


def _unique_ts():
    global _last_ts
    with _ts_lock:
        _last_ts = max(time.time(), _last_ts + 1e-6)
        return _last_ts


def post_signal(mid, from_uid, to_uid, kind, payload):
    if kind not in SIGNAL_KINDS:
        raise ApiError("Неизвестный тип сигнала", 400, "bad_request")
    payload = payload if isinstance(payload, str) else json.dumps(payload)
    if len(payload) > 20000:
        raise ApiError("Слишком большой сигнал", 400, "bad_request")
    st, path = get_store(), f"matches/{mid}/signals"
    if kind == "offer":  # новый звонок — старые сигналы больше не нужны
        for s in st.query(path):
            st.delete(path, s["id"])
    sid = st.new_id()
    st.set(path, sid, {"from_uid": from_uid, "to_uid": to_uid, "kind": kind, "payload": payload,
                       "created_at": _unique_ts()})
    return sid


def get_signals(mid, uid, since=0.0):
    docs = get_store().query(f"matches/{mid}/signals", [("created_at", ">", since)], order_by="created_at")
    return [{"id": s["id"], "kind": s["kind"], "payload": s["payload"], "created_at": s["created_at"]}
            for s in docs if s["to_uid"] == uid]


def clear_signals(mid):
    st, path = get_store(), f"matches/{mid}/signals"
    for s in st.query(path):
        st.delete(path, s["id"])
