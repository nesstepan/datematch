# DateMatch — сайт знакомств (упрощённый Tinder)

Django 5 + Firebase Firestore. Регистрация с фото, профиль, лента со свайпами, лайк/дизлайк, матчи, чат, админ-панель.

* Быстрый старт и деплой: [docs/05_DEPLOY_AND_DEFENSE.md](docs/05_DEPLOY_AND_DEFENSE.md)
* ТЗ, схема БД, список API: [docs/01_TZ.md](docs/01_TZ.md)
* Новые функции (фильтры, тёмная тема, видео, медиа в чате, уведомления, звонки, подарки, достижения): [docs/06_NEW_FEATURES.md](docs/06_NEW_FEATURES.md)
* Тесты и безопасность: [docs/04_TESTING.md](docs/04_TESTING.md)

* Дизайн-система, шрифты, иконки: [docs/07_DESIGN.md](docs/07_DESIGN.md)
* Полная инструкция по выкладке на хостинг: [docs/08_DEPLOY_FULL.md](docs/08_DEPLOY_FULL.md)

```bash
pip install -r requirements.txt
export DJANGO_DEBUG=1 USE_MEMORY_DB=1 ADMIN_EMAILS=you@example.com
python manage.py runserver
```
