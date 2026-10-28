"""Хеширование паролей и ограничение числа попыток входа (только стандартная библиотека)."""
import base64
import hashlib
import hmac
import os
import threading
import time

ITERATIONS = 600_000  # рекомендация OWASP для PBKDF2-SHA256
_DUMMY = None


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored) -> bool:
    """Если пользователя нет (stored=None), всё равно считаем хеш — чтобы время ответа не выдавало,
    существует ли такой email."""
    global _DUMMY
    if not stored:
        if _DUMMY is None:
            _DUMMY = hash_password("dummy-password")
        stored, valid_user = _DUMMY, False
    else:
        valid_user = True
    try:
        _, iterations, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(calc, base64.b64decode(digest)) and valid_user
    except (ValueError, TypeError):
        return False


class RateLimiter:
    """Не более `limit` неудачных попыток за `window` секунд на ключ (email + IP).
    Хранится в памяти процесса — для учебного проекта достаточно."""

    def __init__(self, limit=5, window=600):
        self.limit, self.window = limit, window
        self._hits = {}
        self._lock = threading.Lock()

    def _fresh(self, key):
        cutoff = time.time() - self.window
        hits = [t for t in self._hits.get(key, []) if t > cutoff]
        self._hits[key] = hits
        return hits

    def blocked(self, key) -> bool:
        with self._lock:
            return len(self._fresh(key)) >= self.limit

    def hit(self, key):
        with self._lock:
            self._fresh(key).append(time.time())

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)


login_limiter = RateLimiter()
