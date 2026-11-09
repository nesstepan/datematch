"""HTTP-тесты смены пароля (нужен Django): USE_MEMORY_DB=1 python manage.py test"""
from django.test import Client, SimpleTestCase, override_settings

from core import security, services, store
from core.tests.test_api import reg_data

JSON = "application/json"


@override_settings(USE_MEMORY_DB=True, ADMIN_EMAILS={"boss@example.com"})
class PasswordApiTests(SimpleTestCase):
    def setUp(self):
        security.ITERATIONS = 1000
        security.login_limiter._hits.clear()
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.user, self.admin = Client(), Client()
        self.uu = self.user.post("/api/auth/register/", reg_data("user@example.com", name="Аня")).json()["user"]
        self.admin.post("/api/auth/register/", reg_data("boss@example.com", name="Шеф"))

    def login(self, email, password):
        return Client().post("/api/auth/login/", {"email": email, "password": password}, content_type=JSON)

    def test_change_own_password(self):
        second_device = Client()
        self.assertEqual(self.login("user@example.com", "secret123").status_code, 200)
        second_device.post("/api/auth/login/", {"email": "user@example.com", "password": "secret123"}, content_type=JSON)
        r = self.user.post("/api/me/password/", {"current_password": "secret123", "new_password": "newpass456"}, content_type=JSON)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.user.get("/api/me/").status_code, 200)         # этот вход остаётся действительным
        self.assertEqual(second_device.get("/api/me/").status_code, 401)     # остальные закрыты
        self.assertEqual(self.login("user@example.com", "secret123").status_code, 401)
        self.assertEqual(self.login("user@example.com", "newpass456").status_code, 200)

    def test_wrong_weak_and_same_password(self):
        post = lambda cur, new: self.user.post("/api/me/password/", {"current_password": cur, "new_password": new}, content_type=JSON)
        r = post("wrong-pass1", "newpass456")
        self.assertEqual(r.status_code, 422); self.assertIn("current_password", r.json()["error"]["fields"])
        self.assertIn("new_password", post("secret123", "short1").json()["error"]["fields"])
        self.assertIn("new_password", post("secret123", "secret123").json()["error"]["fields"])
        self.assertEqual(self.login("user@example.com", "secret123").status_code, 200)

    def test_requires_login_and_limits_attempts(self):
        self.assertEqual(Client().post("/api/me/password/", {}, content_type=JSON).status_code, 401)
        codes = [self.user.post("/api/me/password/", {"current_password": "bad-pass-%d" % i, "new_password": "newpass456"},
                                content_type=JSON).status_code for i in range(12)]
        self.assertIn(429, codes)                                            # перебор текущего пароля блокируется

    def test_admin_sets_password(self):
        url = f"/api/admin/users/{self.uu['uid']}/password/"
        self.assertEqual(self.user.post(url, {"password": "hacked12345"}, content_type=JSON).status_code, 403)  # не админ
        self.assertEqual(self.admin.post(url, {"password": "short"}, content_type=JSON).status_code, 422)
        self.assertEqual(self.admin.post(url, {"password": "reset12345"}, content_type=JSON).status_code, 200)
        self.assertEqual(self.user.get("/api/me/").status_code, 401)         # старый вход пользователя закрыт
        self.assertEqual(self.login("user@example.com", "secret123").status_code, 401)
        self.assertEqual(self.login("user@example.com", "reset12345").status_code, 200)
        self.assertEqual(self.admin.post("/api/admin/users/nope/password/", {"password": "reset12345"}, content_type=JSON).status_code, 404)
        me = self.admin.get("/api/me/").json()["user"]["uid"]
        self.assertEqual(self.admin.post(f"/api/admin/users/{me}/password/", {"password": "reset12345"}, content_type=JSON).status_code, 400)
