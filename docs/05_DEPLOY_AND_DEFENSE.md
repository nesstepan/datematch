# Этап 5. Деплой и защита

## 1. Firebase (один раз)
1. https://console.firebase.google.com → **Add project** (Analytics не нужен).
2. **Build → Firestore Database → Create database** → режим **Production** → регион ближе к вам (например, `eur3`).
3. Вкладка **Rules** → вставьте содержимое `firestore.rules` → **Publish**.
4. **Project settings (шестерёнка) → Service accounts → Generate new private key** → скачается JSON. Это секрет: не коммитить, не слать в чаты.

## 2. Локальный запуск
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DJANGO_DEBUG=1 ADMIN_EMAILS=you@example.com
export USE_MEMORY_DB=1                                   # без Firebase; для настоящей БД вместо этого:
# export FIREBASE_CREDENTIALS_FILE=/путь/serviceAccountKey.json
python manage.py runserver
```
Откройте http://127.0.0.1:8000, зарегистрируйтесь с email из `ADMIN_EMAILS` — получите доступ к `/panel/`.
Windows PowerShell: `$env:DJANGO_DEBUG="1"; $env:USE_MEMORY_DB="1"; $env:ADMIN_EMAILS="you@example.com"` вместо `export`; cmd: `set DJANGO_DEBUG=1` и т.д. Переменные задаются в том же окне, где запускается `runserver`.

## 3. Деплой на Render
1. Залейте проект на GitHub (убедитесь, что JSON-ключа в репозитории нет).
2. https://render.com → **New → Blueprint** (подхватит `render.yaml`) или **New → Web Service**:
   * Build: `pip install -r requirements.txt && python manage.py collectstatic --no-input`
   * Start: `gunicorn config.wsgi:application --workers 2 --bind 0.0.0.0:$PORT`
   * Plan: Free
3. **Environment** → переменные:
   | Ключ | Значение |
   |---|---|
   | `DJANGO_SECRET_KEY` | длинная случайная строка (Blueprint создаст сам) |
   | `DJANGO_SSL_REDIRECT` | `1` |
   | `ADMIN_EMAILS` | ваш email |
   | `FIREBASE_CREDENTIALS_JSON` | **всё содержимое** скачанного JSON-файла |
   | `PYTHON_VERSION` | `3.12.3` |
   | `TURN_URLS`, `TURN_USERNAME`, `TURN_CREDENTIAL` | необязательно: TURN-сервер для звонков между разными сетями (см. `06_NEW_FEATURES.md`) |
4. Deploy. Ссылка вида `https://datematch-xxxx.onrender.com` — это «работающий проект в интернете».
5. Проверка в продакшене: регистрация → фото грузится → второй аккаунт в другом браузере → взаимный лайк → чат → админка.

Важно: бесплатный сервис Render «засыпает» после ~15 минут простоя, первый запрос после этого идёт 30–60 секунд. Откройте сайт за минуту до защиты.
Про «Vercel/Netlify для фронтенда»: здесь фронтенд отдаёт сам Django, поэтому отдельный хостинг не нужен — одна ссылка, нет проблем с CORS и куками.
Если преподаватель требует именно раздельный деплой — скажите ему об этом сразу и объясните выбор.

Новые функции (медиа в чате, видео, звонки, уведомления) не требуют ничего, кроме HTTPS, который Render выдаёт сам. Подробности и ограничения: [06_NEW_FEATURES.md](06_NEW_FEATURES.md).

## 4. Демо на 5–7 минут
| Время | Что показать |
|---|---|
| 0:00–0:45 | Идея и стек (один слайд): Django + Firestore + сессии, 6 коллекций |
| 0:45–1:30 | Схема БД и как связаны коллекции (ER из `01_TZ.md`) |
| 1:30–2:30 | Регистрация: показать валидацию (пустая форма, плохое фото), потом создать аккаунт |
| 2:30–4:30 | Два окна (обычное + инкогнито): свайп → взаимный лайк → «Это пара!» → чат в реальном времени |
| 4:30–5:30 | Админка: добавить интерес, заблокировать пользователя; личный кабинет |
| 5:30–6:30 | Телефонный вид в DevTools; безопасность одним слайдом (хеши, CSRF, XSS, права); тесты |
| 6:30–7:00 | Ограничения и что улучшили бы (WebSocket, Firebase Storage, транзакции) |

Подготовьте до защиты два аккаунта-примера (с нормальными фото) и сохранённый сценарий, чтобы не вводить данные на глазах у комиссии.

## 5. Вероятные вопросы
* **Почему Firestore, а не SQL?** Данные естественно ложатся в документы, бесплатный тариф, не надо поднимать сервер БД.
* **Как найти взаимный лайк?** Документ свайпа имеет id `"от__кому"`; при лайке читаем документ `"кому__от"` — одно чтение.
* **Как избежали двух пар при одновременных лайках?** Id пары — отсортированные uid, запись идемпотентна.
* **Где хранятся фото?** В Firestore как сжатый base64-JPEG; Firebase Storage требует платный план. Масштабировать — вынести в Storage/S3.
* **Почему не WebSocket?** Опрос раз в 3 сек надёжен на бесплатном хостинге; для продакшена — Channels или Firestore realtime.
* **Как защищены пароли?** PBKDF2-SHA256, 600 000 итераций, соль; в БД хеш, не пароль.
* **Что если Firebase недоступен?** Пользователь видит сообщение 503, сервер не падает, ошибка пишется в лог.
