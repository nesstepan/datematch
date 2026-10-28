"""Тесты логики без Django и без Firebase (хранилище в памяти).
Запуск:  python -m unittest core.tests.test_services core.tests.test_validators -v
"""
import io
import unittest

from PIL import Image

from core import security, services, store, validators
from core.exceptions import ApiError

security.ITERATIONS = 1000  # в тестах хеш считаем быстро


def make_jpeg(size=(900, 700), color=(200, 50, 80), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def form(**over):
    base = {"email": "a@example.com", "password": "secret123", "name": "Аня", "age": "25",
            "gender": "female", "looking_for": "male", "bio": "Привет", "interests": ["Кино"]}
    base.update(over)
    return base


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.photo = validators.process_photo(make_jpeg())

    def register(self, **over):
        cleaned = validators.validate_registration(form(**over), services.interest_names())
        return services.create_user(cleaned, self.photo)


class TestUsers(ServiceTestCase):
    def test_register_and_duplicate_email(self):
        u = self.register()
        self.assertEqual(u["email"], "a@example.com")
        self.assertNotIn("secret123", str(u))
        with self.assertRaises(ApiError) as ctx:
            self.register()
        self.assertEqual(ctx.exception.status, 409)

    def test_password_check(self):
        u = self.register()
        self.assertTrue(security.verify_password("secret123", u["password_hash"]))
        self.assertFalse(security.verify_password("wrong-pass1", u["password_hash"]))
        self.assertFalse(security.verify_password("anything1", None))

    def test_admin_email(self):
        cleaned = validators.validate_registration(form(email="boss@example.com"), services.interest_names())
        self.assertTrue(services.create_user(cleaned, self.photo, {"boss@example.com"})["is_admin"])

    def test_private_profile_has_email_public_does_not(self):
        u = self.register()
        self.assertIn("email", services.private_profile(u))
        self.assertNotIn("email", services.public_profile(u))
        self.assertNotIn("password_hash", services.private_profile(u))

    def test_delete_cascade(self):
        a, b = self.register(), self.register(email="b@example.com", gender="male", looking_for="female")
        services.swipe(a["id"], b["id"], True)
        services.swipe(b["id"], a["id"], True)
        mid = services.list_matches(a["id"])[0]["id"]
        services.send_message(mid, a["id"], "hi")
        services.delete_user_cascade(a["id"])
        st = store.get_store()
        self.assertIsNone(st.get("users", a["id"]))
        self.assertIsNone(st.get("photos", a["id"]))
        self.assertEqual(st.query("matches"), [])
        self.assertEqual(st.query("swipes"), [])
        self.assertEqual(st.query(f"matches/{mid}/messages"), [])


class TestSwipesAndMatches(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.register(email="a@example.com", gender="female", looking_for="male")
        self.b = self.register(email="b@example.com", name="Борис", gender="male", looking_for="female")

    def test_one_sided_like_is_not_match(self):
        self.assertFalse(services.swipe(self.a["id"], self.b["id"], True)["matched"])
        self.assertEqual(services.list_matches(self.a["id"]), [])

    def test_mutual_like_makes_match_for_both(self):
        services.swipe(self.a["id"], self.b["id"], True)
        res = services.swipe(self.b["id"], self.a["id"], True)
        self.assertTrue(res["matched"])
        self.assertEqual(len(services.list_matches(self.a["id"])), 1)
        self.assertEqual(services.list_matches(self.b["id"])[0]["other"]["uid"], self.a["id"])

    def test_dislike_blocks_match(self):
        services.swipe(self.a["id"], self.b["id"], False)
        self.assertFalse(services.swipe(self.b["id"], self.a["id"], True)["matched"])

    def test_repeat_swipe_does_not_duplicate_match(self):
        services.swipe(self.a["id"], self.b["id"], True)
        services.swipe(self.b["id"], self.a["id"], True)
        services.swipe(self.b["id"], self.a["id"], True)
        self.assertEqual(len(store.get_store().query("matches")), 1)

    def test_cannot_swipe_self_or_missing(self):
        with self.assertRaises(ApiError):
            services.swipe(self.a["id"], self.a["id"], True)
        with self.assertRaises(ApiError) as ctx:
            services.swipe(self.a["id"], "nope", True)
        self.assertEqual(ctx.exception.status, 404)

    def test_feed_excludes_self_swiped_and_mismatched_preferences(self):
        c = self.register(email="c@example.com", gender="female", looking_for="female")
        self.assertEqual([p["uid"] for p in services.feed(self.a["id"])], [self.b["id"]])  # c не ищет женщин... и a ищет мужчин
        services.swipe(self.a["id"], self.b["id"], False)
        self.assertEqual(services.feed(self.a["id"]), [])
        self.assertNotIn(self.a["id"], [p["uid"] for p in services.feed(c["id"])])

    def test_blocked_user_not_in_feed(self):
        services.set_user_active(self.b["id"], False)
        self.assertEqual(services.feed(self.a["id"]), [])


class TestChat(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.register(email="a@example.com", gender="female", looking_for="male")
        self.b = self.register(email="b@example.com", gender="male", looking_for="female")
        self.c = self.register(email="c@example.com", gender="male", looking_for="female")
        services.swipe(self.a["id"], self.b["id"], True)
        self.mid = services.swipe(self.b["id"], self.a["id"], True)["match_id"]

    def test_send_and_read(self):
        services.send_message(self.mid, self.a["id"], "  Привет!  ")
        msgs = services.list_messages(self.mid, self.b["id"])
        self.assertEqual([m["text"] for m in msgs], ["Привет!"])
        self.assertFalse(msgs[0]["mine"])
        self.assertEqual(services.list_matches(self.b["id"])[0]["last_message"], "Привет!")

    def test_since_returns_only_new(self):
        first = services.send_message(self.mid, self.a["id"], "1")
        services.send_message(self.mid, self.b["id"], "2")
        new = services.list_messages(self.mid, self.a["id"], since=first["created_at"])
        self.assertEqual([m["text"] for m in new], ["2"])

    def test_outsider_cannot_read_or_write(self):
        with self.assertRaises(ApiError) as ctx:
            services.list_messages(self.mid, self.c["id"])
        self.assertEqual(ctx.exception.status, 404)
        with self.assertRaises(ApiError):
            services.send_message(self.mid, self.c["id"], "hack")

    def test_message_validation(self):
        for bad in ("", "   ", "x" * 1001):
            with self.assertRaises(ApiError) as ctx:
                services.send_message(self.mid, self.a["id"], bad)
            self.assertEqual(ctx.exception.status, 422)

    def test_unmatch_removes_chat(self):
        services.send_message(self.mid, self.a["id"], "hi")
        services.unmatch(self.mid, self.a["id"])
        self.assertEqual(services.list_matches(self.b["id"]), [])
        with self.assertRaises(ApiError):
            services.list_messages(self.mid, self.b["id"])


class TestInterestsAdmin(ServiceTestCase):
    def test_seed_add_delete(self):
        self.assertIn("Кино", services.interest_names())
        item = services.add_interest("Настолки")
        self.assertIn("Настолки", services.interest_names())
        with self.assertRaises(ApiError) as ctx:
            services.add_interest("настолки")
        self.assertEqual(ctx.exception.status, 409)
        services.delete_interest(item["id"])
        self.assertNotIn("Настолки", services.interest_names())

    def test_stats(self):
        self.register()
        s = services.stats()
        self.assertEqual((s["users"], s["matches"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
