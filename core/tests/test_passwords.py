"""Тесты смены пароля (без Django).  Запуск:  python -m unittest core.tests.test_passwords -v"""
import unittest

from core import security, services
from core.exceptions import ApiError
from core.tests.test_social import SocialBase


class TestChangeOwnPassword(SocialBase):
    def ok(self, uid, password):
        return security.verify_password(password, services.get_user(uid)["password_hash"])

    def test_success_changes_hash_and_version(self):
        v = services.change_password(self.a["id"], "secret123", "newpass456")
        self.assertEqual(v, 1)
        self.assertTrue(self.ok(self.a["id"], "newpass456"))
        self.assertFalse(self.ok(self.a["id"], "secret123"))
        self.assertEqual(services.change_password(self.a["id"], "newpass456", "another789"), 2)  # версия растёт

    def test_wrong_current_password(self):
        with self.assertRaises(ApiError) as ctx:
            services.change_password(self.a["id"], "wrong-pass1", "newpass456")
        self.assertEqual((ctx.exception.status, ctx.exception.code), (422, "wrong_current_password"))
        self.assertIn("current_password", ctx.exception.fields)
        self.assertTrue(self.ok(self.a["id"], "secret123"))  # пароль не изменился

    def test_weak_and_same_new_password(self):
        for bad in ("", "short1", "onlyletters", "12345678", "x" * 129):
            with self.assertRaises(ApiError) as ctx:
                services.change_password(self.a["id"], "secret123", bad)
            self.assertIn("new_password", ctx.exception.fields, bad)
        with self.assertRaises(ApiError) as ctx:
            services.change_password(self.a["id"], "secret123", "secret123")
        self.assertIn("new_password", ctx.exception.fields)
        self.assertTrue(self.ok(self.a["id"], "secret123"))

    def test_missing_current_password(self):
        with self.assertRaises(ApiError):
            services.change_password(self.a["id"], None, "newpass456")

    def test_other_users_untouched(self):
        services.change_password(self.a["id"], "secret123", "newpass456")
        self.assertTrue(self.ok(self.b["id"], "secret123"))
        self.assertEqual(services.get_user(self.b["id"]).get("pwv", 0), 0)


class TestAdminSetPassword(SocialBase):
    def test_admin_sets_any_users_password(self):
        services.admin_set_password(self.b["id"], "reset12345")
        u = services.get_user(self.b["id"])
        self.assertTrue(security.verify_password("reset12345", u["password_hash"]))
        self.assertEqual(u["pwv"], 1)
        self.assertFalse(security.verify_password("secret123", u["password_hash"]))

    def test_validation_and_unknown_user(self):
        with self.assertRaises(ApiError) as ctx:
            services.admin_set_password(self.b["id"], "short")
        self.assertIn("password", ctx.exception.fields)
        with self.assertRaises(ApiError) as ctx:
            services.admin_set_password("nope", "reset12345")
        self.assertEqual(ctx.exception.status, 404)
        self.assertTrue(security.verify_password("secret123", services.get_user(self.b["id"])["password_hash"]))


class TestFastSending(SocialBase):
    def test_side_effects_run_in_background_when_enabled(self):
        import threading, time
        from core import features
        mid = self.pair()
        services.ASYNC_SIDE_EFFECTS = True
        try:
            before = threading.active_count()
            msg = services.send_message(mid, self.a["id"], "Привет!")
            self.assertEqual(msg["text"], "Привет!")  # сообщение уже сохранено и возвращено
            for _ in range(50):  # уведомление появится следом (в фоне)
                if [n for n in features.list_notifications(self.b["id"]) if n["type"] == "message"]:
                    break
                time.sleep(0.05)
            notes = [n for n in features.list_notifications(self.b["id"]) if n["type"] == "message"]
            self.assertEqual(len(notes), 1)
        finally:
            services.ASYNC_SIDE_EFFECTS = False

    def test_background_error_does_not_break_sending(self):
        mid = self.pair()
        services.ASYNC_SIDE_EFFECTS = True
        orig = services._message_side_effects
        services._message_side_effects = lambda *a, **k: 1 / 0
        try:
            self.assertEqual(services.send_message(mid, self.a["id"], "ок")["text"], "ок")
        finally:
            services._message_side_effects = orig
            services.ASYNC_SIDE_EFFECTS = False


if __name__ == "__main__":
    unittest.main()
