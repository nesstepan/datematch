"""Исключения приложения. Не зависят от Django, чтобы сервисы можно было тестировать отдельно."""


class ApiError(Exception):
    """Ожидаемая ошибка: превращается в JSON-ответ с понятным текстом для пользователя."""

    def __init__(self, message, status=400, code="bad_request", fields=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.fields = fields or {}


class StoreError(Exception):
    """База данных недоступна или вернула ошибку."""
