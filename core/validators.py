"""Серверная валидация. Правила продублированы на фронте (static/js), но доверять мы можем только этому файлу."""
import io
import re
from urllib.parse import urlparse

from .exceptions import ApiError

GENDERS = ("male", "female", "other")
LOOKING_FOR = ("male", "female", "everyone")
GOALS = (("relationship", "Серьёзные отношения"), ("dating", "Свидания"), ("friends", "Дружба"),
         ("chat", "Общение"), ("unsure", "Пока не знаю"))
GOAL_IDS = tuple(g[0] for g in GOALS)
GOAL_TITLES = dict(GOALS)
REPORT_REASONS = {"spam": "Спам или реклама", "fake": "Фейковая анкета", "abuse": "Оскорбления или угрозы",
                  "inappropriate": "Неприемлемый контент", "underage": "Похоже, нет 18 лет", "other": "Другое"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
NAME_RE = re.compile(r"^[\w\s'.\-]+$", re.UNICODE)
INTEREST_RE = re.compile(r"^[\w\s'.\-+#]+$", re.UNICODE)

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_INTERESTS = 8


class _Bad(Exception):
    pass


def clean_email(v):
    v = (v or "").strip().lower()
    if not v:
        raise _Bad("Укажите email")
    if len(v) > 254 or not EMAIL_RE.match(v):
        raise _Bad("Некорректный email, пример: name@example.com")
    return v


def clean_password(v):
    v = v or ""
    if not v:
        raise _Bad("Введите пароль")
    if len(v) < 8:
        raise _Bad("Пароль должен быть не короче 8 символов")
    if len(v) > 128:
        raise _Bad("Пароль слишком длинный (максимум 128 символов)")
    if not (re.search(r"[^\W\d_]", v) and re.search(r"\d", v)):
        raise _Bad("Пароль должен содержать и буквы, и цифры")
    return v


def clean_name(v):
    v = " ".join((v or "").split())
    if len(v) < 2 or len(v) > 50:
        raise _Bad("Имя — от 2 до 50 символов")
    if not NAME_RE.match(v):
        raise _Bad("В имени допустимы только буквы, пробелы, дефис и точка")
    return v


def clean_age(v):
    try:
        age = int(str(v).strip())
    except (TypeError, ValueError):
        raise _Bad("Укажите возраст числом")
    if age < 18 or age > 99:
        raise _Bad("Сервис только для совершеннолетних: возраст от 18 до 99")
    return age


def _choice(v, allowed, message):
    v = (v or "").strip()
    if v not in allowed:
        raise _Bad(message)
    return v


def clean_bio(v):
    v = (v or "").strip()
    if len(v) > 500:
        raise _Bad("О себе — не больше 500 символов")
    return v


def clean_interests(values, allowed_names):
    canon = {n.lower(): n for n in allowed_names}
    result = []
    for raw in values or []:
        name = canon.get((raw or "").strip().lower())
        if name is None:
            raise _Bad(f"Неизвестный интерес: {str(raw)[:30]}")
        if name not in result:
            result.append(name)
    if len(result) > MAX_INTERESTS:
        raise _Bad(f"Выберите не больше {MAX_INTERESTS} интересов")
    return result


def clean_message(v):
    v = (v or "").strip()
    if not v:
        raise _Bad("Сообщение пустое")
    if len(v) > 1000:
        raise _Bad("Сообщение длиннее 1000 символов")
    return v


def clean_interest_name(v):
    v = " ".join((v or "").split())
    if len(v) < 2 or len(v) > 30:
        raise _Bad("Название интереса — от 2 до 30 символов")
    if not INTEREST_RE.match(v):
        raise _Bad("В названии допустимы буквы, цифры, пробел, дефис, +, #")
    return v


def _run(errors, field, fn, *args):
    try:
        return fn(*args)
    except _Bad as exc:
        errors[field] = str(exc)
        return None


def _finish(errors):
    if errors:
        raise ApiError("Проверьте заполнение полей", 422, "validation_error", errors)


def validate_profile(form, allowed_interests):
    errors = {}
    data = {
        "name": _run(errors, "name", clean_name, form.get("name")),
        "age": _run(errors, "age", clean_age, form.get("age")),
        "gender": _run(errors, "gender", _choice, form.get("gender"), GENDERS, "Выберите пол"),
        "looking_for": _run(errors, "looking_for", _choice, form.get("looking_for"), LOOKING_FOR,
                            "Укажите, кого вы ищете"),
        "bio": _run(errors, "bio", clean_bio, form.get("bio")),
        "goal": _run(errors, "goal", clean_goal, form.get("goal")),
        "interests": _run(errors, "interests", clean_interests, form.get("interests"), allowed_interests),
    }
    _finish(errors)
    return data


def validate_registration(form, allowed_interests):
    errors = {}
    try:
        data = validate_profile(form, allowed_interests)
    except ApiError as exc:
        errors.update(exc.fields)
        data = {}
    data["email"] = _run(errors, "email", clean_email, form.get("email"))
    data["password"] = _run(errors, "password", clean_password, form.get("password"))
    _finish(errors)
    return data


def process_photo(raw: bytes) -> bytes:
    """Проверяет, что это настоящее изображение, обрезает до 4:5, уменьшает и пережимает в JPEG.
    Заодно это убирает EXIF (геолокацию) и любые «встроенные» данные."""
    from PIL import Image, ImageOps

    if not raw:
        raise ApiError("Загрузите фото", 422, "validation_error", {"photo": "Загрузите фото"})
    if len(raw) > MAX_PHOTO_BYTES:
        raise ApiError("Фото слишком большое", 422, "validation_error",
                       {"photo": "Файл больше 5 МБ — выберите фото поменьше"})
    Image.MAX_IMAGE_PIXELS = 40_000_000
    try:
        img = Image.open(io.BytesIO(raw))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("format")
        img.load()
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.fit(img, (600, 750), method=Image.LANCZOS)
        for quality in (82, 70, 55):
            out = io.BytesIO()
            img.save(out, "JPEG", quality=quality, optimize=True)
            if out.tell() < 450_000:
                break
        return out.getvalue()
    except Exception:
        raise ApiError("Не удалось прочитать фото", 422, "validation_error",
                       {"photo": "Нужен файл JPG, PNG или WEBP — этот не открывается как картинка"})


# ---------- оформление, музыка, приватность ----------
def clean_status(v):
    v = " ".join((v or "").split())
    if len(v) > 60:
        raise _Bad("Статус — не больше 60 символов")
    return v


def clean_music_title(v):
    v = " ".join((v or "").split())
    if len(v) > 80:
        raise _Bad("Название трека — не больше 80 символов")
    return v


def clean_music_url(v):
    v = (v or "").strip()
    if not v:
        return ""
    if len(v) > 300 or re.search(r"\s", v):
        raise _Bad("Ссылка слишком длинная или содержит пробелы")
    p = urlparse(v)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise _Bad("Ссылка должна начинаться с http:// или https://")
    return v


def clean_accent(v):
    v = (v or "").strip().lower()
    if v and not re.fullmatch(r"#[0-9a-f]{6}", v):
        raise _Bad("Цвет нужен в формате #rrggbb")
    return v


def validate_settings(body):
    """Частичное обновление: проверяются только присланные поля."""
    errors, data = {}, {}
    if "hidden" in body:
        if isinstance(body["hidden"], bool):
            data["hidden"] = body["hidden"]
        else:
            errors["hidden"] = "Нужно значение true или false"
    if "hide_online" in body:
        if isinstance(body["hide_online"], bool):
            data["hide_online"] = body["hide_online"]
        else:
            errors["hide_online"] = "Нужно значение true или false"
    for key, fn in (("status", clean_status), ("music_title", clean_music_title),
                    ("music_url", clean_music_url), ("accent", clean_accent)):
        if key in body:
            data[key] = _run(errors, key, fn, body.get(key))
    _finish(errors)
    return data


def clean_duration(v):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return 0
    return max(0, min(n, 180))


def clean_goal(v):
    v = (v or "unsure").strip() or "unsure"
    if v not in GOAL_IDS:
        raise _Bad("Выберите, что вы ищете")
    return v


def clean_post_text(v):
    v = (v or "").strip()
    if len(v) > 1000:
        raise _Bad("Пост длиннее 1000 символов")
    return v


def clean_comment(v):
    v = " ".join((v or "").split())
    if not v:
        raise _Bad("Напишите комментарий")
    if len(v) > 500:
        raise _Bad("Комментарий длиннее 500 символов")
    return v


def clean_search_query(v):
    v = " ".join((v or "").split())
    return v[:50]


def validate_report(body):
    """-> (reason, details, context). Ошибки — в том же формате, что и у остальных форм."""
    errors = {}
    reason = body.get("reason")
    if reason not in REPORT_REASONS:
        errors["reason"] = "Выберите причину жалобы"
    details = " ".join(str(body.get("details") or "").split())
    if len(details) > 500:
        errors["details"] = "Пояснение — не больше 500 символов"
    context = body.get("context") if body.get("context") in ("profile", "chat", "post") else "profile"
    _finish(errors)
    return reason, details, context
