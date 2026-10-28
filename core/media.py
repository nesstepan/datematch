"""Медиафайлы (видео анкеты, вложения чата): проверка по содержимому и хранение кусками в Firestore.

Документ Firestore ограничен ~1 МиБ, поэтому файл режется на куски по 700 КБ (в base64 ≈ 933 КБ):
  media/<id>                — метаданные (владелец, тип, размер, к какой паре относится)
  media/<id>/chunks/<0000>  — куски данных
Для больших объёмов (много видео) лучше вынести файлы во внешнее хранилище, см. docs/06_NEW_FEATURES.md.
"""
import base64
import io
import threading
import time
from collections import OrderedDict

from .exceptions import ApiError
from .store import get_store

CHUNK = 700_000
MB = 1024 * 1024
LIMITS = {"image": 5 * MB, "gif": 3 * MB, "video": 6 * MB, "voice": 2 * MB}
KIND_RU = {"image": "Фото", "gif": "GIF", "video": "Видео", "voice": "Голосовое"}

_cache = OrderedDict()  # media_id -> bytes (файлы неизменны, поэтому кэш безопасен)
_cache_lock = threading.Lock()
_CACHE_MAX_BYTES = 24 * MB
_cache_size = 0


def _bad(msg, field="file"):
    return ApiError(msg, 422, "validation_error", {field: msg})


def sniff(raw):
    """Определяет тип по первым байтам (расширению и заголовку Content-Type доверять нельзя)."""
    h = raw[:16]
    if h[:3] == b"\xff\xd8\xff":
        return "image", "image/jpeg"
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        return "image", "image/png"
    if h[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image", "image/webp"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "image/gif"
    if raw[4:8] == b"ftyp":
        return "video", ("video/quicktime" if raw[8:12] == b"qt  " else "video/mp4")
    if h[:4] == b"\x1aE\xdf\xa3":
        return "video", "video/webm"
    if h[:4] == b"OggS":
        return "audio", "audio/ogg"
    if h[:3] == b"ID3" or h[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "audio", "audio/mpeg"
    if h[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        return "audio", "audio/wav"
    return None, None


def _fit_image(raw):
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((1280, 1280), Image.LANCZOS)
        for quality in (82, 70, 55):
            out = io.BytesIO()
            img.save(out, "JPEG", quality=quality, optimize=True)
            if out.tell() < 900_000:
                break
        return out.getvalue()
    except Exception:
        raise _bad("Не удалось прочитать картинку")


def _check_gif(raw):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        Image.open(io.BytesIO(raw)).verify()
    except Exception:
        raise _bad("Не удалось прочитать GIF")


def classify_chat(raw, hint=""):
    """-> (kind, content_type, bytes) для вложения чата. kind: image | gif | video | voice."""
    if not raw:
        raise _bad("Файл пустой")
    kind, ctype = sniff(raw)
    if hint == "voice":
        if kind not in ("audio", "video"):
            raise _bad("Не удалось распознать голосовое сообщение")
        ctype = {"video/webm": "audio/webm", "video/mp4": "audio/mp4",
                 "video/quicktime": "audio/mp4"}.get(ctype, ctype)
        kind = "voice"
    elif kind in (None, "audio"):
        raise _bad("Поддерживаются фото (JPG, PNG, WEBP), GIF и видео (MP4, WEBM, MOV)")
    if len(raw) > LIMITS[kind]:
        raise _bad(f"{KIND_RU[kind]} больше {LIMITS[kind] // MB} МБ — выберите файл поменьше")
    if kind == "image":
        raw, ctype = _fit_image(raw), "image/jpeg"
    elif kind == "gif":
        _check_gif(raw)
    return kind, ctype, raw


def classify_profile_video(raw):
    kind, ctype = sniff(raw or b"")
    if kind != "video":
        raise _bad("Нужно видео в формате MP4, WEBM или MOV", "video")
    if len(raw) > LIMITS["video"]:
        raise _bad(f"Видео больше {LIMITS['video'] // MB} МБ — сожмите или обрежьте его", "video")
    return ctype


def save(owner, kind, ctype, raw, match_id="", public=False):
    st = get_store()
    mid = st.new_id()
    for i in range(0, max(len(raw), 1), CHUNK):
        st.set(f"media/{mid}/chunks", f"{i // CHUNK:04d}",
               {"idx": i // CHUNK, "data": base64.b64encode(raw[i:i + CHUNK]).decode()})
    st.set("media", mid, {"owner": owner, "kind": kind, "content_type": ctype, "size": len(raw),
                          "match_id": match_id, "public": bool(public), "created_at": time.time()})
    return mid


def _remember(mid, data):
    global _cache_size
    with _cache_lock:
        if mid in _cache or len(data) > _CACHE_MAX_BYTES:
            return
        _cache[mid] = data
        _cache_size += len(data)
        while _cache_size > _CACHE_MAX_BYTES and _cache:
            _, old = _cache.popitem(last=False)
            _cache_size -= len(old)


def load(mid):
    """-> (meta, bytes) | (None, None)"""
    meta = get_store().get("media", mid)
    if not meta:
        return None, None
    with _cache_lock:
        if mid in _cache:
            _cache.move_to_end(mid)
            return meta, _cache[mid]
    chunks = get_store().query(f"media/{mid}/chunks", order_by="idx")
    data = b"".join(base64.b64decode(c["data"]) for c in chunks)
    _remember(mid, data)
    return meta, data


def delete(mid):
    global _cache_size
    if not mid:
        return
    st = get_store()
    for c in st.query(f"media/{mid}/chunks"):
        st.delete(f"media/{mid}/chunks", c["id"])
    st.delete("media", mid)
    with _cache_lock:
        old = _cache.pop(mid, None)
        if old is not None:
            _cache_size -= len(old)


def delete_where(field, value):
    for m in get_store().query("media", [(field, "==", value)]):
        delete(m["id"])
