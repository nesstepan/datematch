"""Тесты HTTP-слоя через тестовый клиент Django (БД не нужна — хранилище в памяти).
Запуск:  USE_MEMORY_DB=1 python manage.py test
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from PIL import Image

from core import security, services, store


def png():
    buf = io.BytesIO()
    Image.new("RGB", (800, 900), (120, 80, 200)).save(buf, "PNG")
    return buf.getvalue()


def reg_data(email, name="Тест", gender="female", looking="male", **extra):
    return {"email": email, "password": "secret123", "name": name, "age": "24", "gender": gender,
            "looking_for": looking, "bio": "Привет", "interests": ["Кино", "Музыка"],
            "photo": SimpleUploadedFile("p.png", png(), content_type="image/png"), **extra}


@override_settings(USE_MEMORY_DB=True, ADMIN_EMAILS={"boss@example.com"})
class ApiTests(SimpleTestCase):
    def setUp(self):
        security.ITERATIONS = 1000
        security.login_limiter._hits.clear()
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.c = Client()

    def register(self, client, email, **kw):
        return client.post("/api/auth/register/", reg_data(email, **kw))

    # --- авторизация ---
    def test_register_login_logout(self):
        r = self.register(self.c, "a@example.com")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.c.get("/api/me/").json()["user"]["email"], "a@example.com")
        self.c.post("/api/auth/logout/")
        self.assertEqual(self.c.get("/api/me/").status_code, 401)
        ok = self.c.post("/api/auth/login/", {"email": "a@example.com", "password": "secret123"},
                         content_type="application/json")
        self.assertEqual(ok.status_code, 200)

    def test_register_validation_errors_are_specific(self):
        r = self.c.post("/api/auth/register/", {**reg_data("bad"), "age": "12", "password": "short"})
        body = r.json()["error"]
        self.assertEqual(r.status_code, 422)
        self.assertEqual({"email", "age", "password"}, set(body["fields"]))

    def test_register_requires_real_photo(self):
        data = reg_data("a@example.com")
        data["photo"] = SimpleUploadedFile("x.png", b"not-an-image", content_type="image/png")
        r = self.c.post("/api/auth/register/", data)
        self.assertEqual(r.status_code, 422)
        self.assertIn("photo", r.json()["error"]["fields"])
        data = reg_data("a@example.com"); del data["photo"]
        self.assertIn("photo", self.c.post("/api/auth/register/", data).json()["error"]["fields"])

    def test_duplicate_email(self):
        self.register(self.c, "a@example.com")
        r = self.register(Client(), "A@Example.com")
        self.assertEqual(r.status_code, 409)

    def test_wrong_password_and_rate_limit(self):
        self.register(self.c, "a@example.com")
        for _ in range(5):
            r = Client().post("/api/auth/login/", {"email": "a@example.com", "password": "nope12345"},
                              content_type="application/json")
            self.assertEqual(r.status_code, 401)
        r = Client().post("/api/auth/login/", {"email": "a@example.com", "password": "secret123"},
                          content_type="application/json")
        self.assertEqual(r.status_code, 429)

    def test_password_hash_never_in_responses(self):
        self.register(self.c, "a@example.com")
        self.assertNotIn("password", str(self.c.get("/api/me/").json()))

    def test_protected_endpoints_need_login(self):
        for url in ("/api/me/", "/api/feed/", "/api/matches/", "/photo/x/", "/api/admin/users/"):
            self.assertEqual(Client().get(url).status_code, 401, url)

    def test_csrf_enforced(self):
        strict = Client(enforce_csrf_checks=True)
        r = strict.post("/api/auth/login/", {"email": "a@example.com", "password": "x"}, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    # --- свайпы, матчи, чат ---
    def two_users(self):
        a, b = Client(), Client()
        ua = self.register(a, "a@example.com", name="Аня").json()["user"]
        ub = self.register(b, "b@example.com", name="Борис", gender="male", looking="female").json()["user"]
        return a, b, ua, ub

    def test_full_flow_swipe_match_chat(self):
        a, b, ua, ub = self.two_users()
        feed = a.get("/api/feed/").json()["profiles"]
        self.assertEqual([p["uid"] for p in feed], [ub["uid"]])
        self.assertNotIn("email", feed[0])
        post = lambda cl, uid, like: cl.post("/api/swipes/", {"target_uid": uid, "like": like}, content_type="application/json").json()
        self.assertFalse(post(a, ub["uid"], True)["matched"])
        res = post(b, ua["uid"], True)
        self.assertTrue(res["matched"])
        mid = res["match_id"]
        url = f"/api/matches/{mid}/messages/"
        self.assertEqual(a.post(url, {"text": "Привет"}, content_type="application/json").status_code, 201)
        self.assertEqual(b.get(url).json()["messages"][0]["text"], "Привет")
        self.assertEqual(len(a.get("/api/matches/").json()["matches"]), 1)

    def test_swipe_input_validation(self):
        a, b, ua, ub = self.two_users()
        for body in ({}, {"target_uid": ub["uid"]}, {"target_uid": 5, "like": True}, {"target_uid": ub["uid"], "like": "yes"}):
            self.assertEqual(a.post("/api/swipes/", body, content_type="application/json").status_code, 400)
        self.assertEqual(a.post("/api/swipes/", "{oops", content_type="application/json").status_code, 400)

    def test_outsider_cannot_read_chat(self):
        a, b, ua, ub = self.two_users()
        mid = None
        a.post("/api/swipes/", {"target_uid": ub["uid"], "like": True}, content_type="application/json")
        mid = b.post("/api/swipes/", {"target_uid": ua["uid"], "like": True}, content_type="application/json").json()["match_id"]
        eve = Client(); self.register(eve, "eve@example.com", name="Ева")
        self.assertEqual(eve.get(f"/api/matches/{mid}/messages/").status_code, 404)
        self.assertEqual(eve.delete(f"/api/matches/{mid}/").status_code, 404)

    # --- профиль ---
    def test_profile_update_and_delete(self):
        self.register(self.c, "a@example.com")
        r = self.c.post("/api/me/", {"name": "Новое имя", "age": "30", "gender": "female", "looking_for": "everyone",
                                     "bio": "", "interests": ["Кино"]})
        self.assertEqual(r.json()["user"]["name"], "Новое имя")
        bad = self.c.delete("/api/me/", {"password": "wrong"}, content_type="application/json")
        self.assertEqual(bad.status_code, 403)
        ok = self.c.delete("/api/me/", {"password": "secret123"}, content_type="application/json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.c.get("/api/me/").status_code, 401)

    # --- админка ---
    def test_admin_panel_access_and_actions(self):
        admin, user = Client(), Client()
        self.register(admin, "boss@example.com", name="Босс")
        uid = self.register(user, "u@example.com").json()["user"]["uid"]
        self.assertEqual(user.get("/api/admin/stats/").status_code, 403)
        self.assertEqual(user.get("/panel/").status_code, 403)
        self.assertEqual(admin.get("/panel/").status_code, 200)
        self.assertEqual(admin.post("/api/admin/interests/", {"name": "Настолки"}, content_type="application/json").status_code, 201)
        self.assertEqual(admin.post("/api/admin/interests/", {"name": "настолки"}, content_type="application/json").status_code, 409)
        self.assertEqual(admin.patch(f"/api/admin/users/{uid}/", {"is_active": False}, content_type="application/json").status_code, 200)
        self.assertEqual(user.get("/api/me/").status_code, 403)  # заблокирован
        self.assertEqual(admin.delete(f"/api/admin/users/{uid}/").status_code, 200)
        self.assertEqual(len(admin.get("/api/admin/users/").json()["users"]), 1)

    def test_admin_cannot_delete_self(self):
        admin = Client()
        me = self.register(admin, "boss@example.com").json()["user"]
        self.assertEqual(admin.delete(f"/api/admin/users/{me['uid']}/").status_code, 400)

    # --- страницы и ошибки ---
    def test_pages_and_redirects(self):
        self.assertEqual(self.c.get("/").status_code, 200)
        self.assertEqual(self.c.get("/register/").status_code, 200)
        self.assertEqual(self.c.get("/discover/").status_code, 302)
        self.register(self.c, "a@example.com")
        for url in ("/discover/", "/matches/", "/profile/"):
            self.assertEqual(self.c.get(url).status_code, 200, url)
        self.assertEqual(self.c.get("/login/").status_code, 302)

    def test_404_formats(self):
        self.assertEqual(self.c.get("/api/unknown/").json()["error"]["code"], "404")
        r = self.c.get("/no-such-page/")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Страница не найдена", r.content.decode())

    def test_method_not_allowed(self):
        self.assertEqual(self.c.get("/api/auth/login/").status_code, 405)

    def test_healthz(self):
        self.assertEqual(self.c.get("/healthz").status_code, 200)
