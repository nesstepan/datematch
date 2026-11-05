"""Настройки DateMatch.

Django здесь используется как веб-фреймворк (маршруты, шаблоны, сессии, CSRF),
а данные лежат в Firebase Firestore, поэтому классической БД Django нет.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes")


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT"):
        raise ImproperlyConfigured("Задайте переменную окружения DJANGO_SECRET_KEY")
    SECRET_KEY = "dev-only-insecure-key-change-me"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = []
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

# Railway: адрес сайта приходит в переменной RAILWAY_PUBLIC_DOMAIN, а проверку «жив ли сайт» делает
# служебный хост healthcheck.railway.app — его тоже нужно разрешить, иначе проверка не пройдёт.
_railway_host = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if _railway_host:
    ALLOWED_HOSTS += [_railway_host, "healthcheck.railway.app"]
    CSRF_TRUSTED_ORIGINS.append(f"https://{_railway_host}")
# Свой домен: DJANGO_ALLOWED_HOSTS="site.ru,www.site.ru" и DJANGO_CSRF_ORIGINS="https://site.ru,https://www.site.ru"
CSRF_TRUSTED_ORIGINS += [o.strip() for o in os.environ.get("DJANGO_CSRF_ORIGINS", "").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
}]

# Классической БД нет: всё хранится в Firestore (см. core/store.py)
DATABASES = {}

# Сессии в подписанных cookie — таблицы в БД не нужны
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_FAILURE_VIEW = "core.errors.csrf_failure"

SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", False)
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# файлы чата и видео анкеты идут через multipart; сами файлы ограничены в core/media.py
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

LANGUAGE_CODE = "ru"
TIME_ZONE = "UTC"
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Раздавать статику прямо из core/static даже без collectstatic (локальный запуск «из коробки»)
WHITENOISE_USE_FINDERS = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- Firebase ---------------------------------------------------------
# USE_MEMORY_DB=1 — хранить данные в памяти процесса (локальная разработка и тесты)
USE_MEMORY_DB = env_bool("USE_MEMORY_DB", False)
# Звонки (WebRTC) выключены: без TURN-сервера они не соединяют людей из разных сетей. Включить: CALLS_ENABLED=1 + TURN_*
CALLS_ENABLED = env_bool("CALLS_ENABLED", False)
FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
FIREBASE_CREDENTIALS_FILE = os.environ.get("FIREBASE_CREDENTIALS_FILE", "")

# TURN-сервер для звонков между разными сетями (необязательно; без него работает только STUN)
TURN_URLS = [u.strip() for u in os.environ.get("TURN_URLS", "").split(",") if u.strip()]
TURN_USERNAME = os.environ.get("TURN_USERNAME", "")
TURN_CREDENTIAL = os.environ.get("TURN_CREDENTIAL", "")

# Пользователь с таким email при регистрации становится администратором
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
