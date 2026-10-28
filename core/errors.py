from django.http import JsonResponse
from django.shortcuts import render


def _respond(request, status, title, text):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": {"code": str(status), "message": text, "fields": {}}}, status=status)
    return render(request, "error.html", {"status": status, "title": title, "text": text}, status=status)


def bad_request(request, exception=None):
    return _respond(request, 400, "Некорректный запрос", "Сервер не понял запрос. Вернитесь назад и попробуйте снова.")


def forbidden(request, exception=None):
    return _respond(request, 403, "Нет доступа", "У вас нет прав открывать эту страницу.")


def not_found(request, exception=None):
    return _respond(request, 404, "Страница не найдена", "Такой страницы нет. Возможно, ссылка устарела.")


def server_error(request):
    return _respond(request, 500, "Что-то сломалось на сервере", "Мы уже видим ошибку в логах. Попробуйте обновить страницу через минуту.")


def csrf_failure(request, reason=""):
    return _respond(request, 403, "Сессия устарела", "Обновите страницу и повторите действие — защитный токен истёк.")
