"""Тесты новых возможностей без Django: чёрный список, лайки, поиск, посты, жалобы, статусы сообщений.
Запуск:  python -m unittest core.tests.test_social -v
"""
import unittest

from core import features, services, store, validators
from core.exceptions import ApiError
from core.tests.test_services import ServiceTestCase, form, make_jpeg


class SocialBase(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.register(email="a@example.com", name="Анна", gender="female", looking_for="male")
        self.b = self.register(email="b@example.com", name="Борис", gender="male", looking_for="female", interests=["Кино"])
        self.c = self.register(email="c@example.com", name="Виктор", gender="male", looking_for="female", interests=["Музыка"])

    def like(self, x, y, like=True):
        return services.swipe(x["id"], y["id"], like)

    def pair(self, x=None, y=None):
        x, y = x or self.a, y or self.b
        self.like(x, y)
        return self.like(y, x)["match_id"]


class TestGoalAndPresence(SocialBase):
    def test_goal_validation_and_default(self):
        self.assertEqual(validators.validate_profile(form(), ["Кино"])["goal"], "unsure")
        self.assertEqual(validators.validate_profile(form(goal="friends"), ["Кино"])["goal"], "friends")
        with self.assertRaises(ApiError) as ctx:
            validators.validate_profile(form(goal="hack"), ["Кино"])
        self.assertIn("goal", ctx.exception.fields)

    def test_goal_in_profile_and_feed_filter(self):
        cleaned = validators.validate_registration(form(email="d@example.com", name="Дима", gender="male",
                                                       looking_for="female", goal="friends"), services.interest_names())
        d = services.create_user(cleaned, self.photo)
        self.assertEqual(services.public_profile(d)["goal_title"], "Дружба")
        got = [p["uid"] for p in services.feed(self.a["id"], 10, {"goals": ["friends"]})]
        self.assertEqual(got, [d["id"]])

    def test_presence_online_and_hidden(self):
        self.assertTrue(services.public_profile(services.get_user(self.b["id"]))["online"])  # только что зарегистрирован
        store.get_store().update("users", self.b["id"], {"last_seen": 1.0})
        pub = services.public_profile(services.get_user(self.b["id"]))
        self.assertFalse(pub["online"])
        self.assertEqual(pub["last_seen"], 1.0)
        services.update_settings(self.b["id"], {"hide_online": True})
        pub = services.public_profile(services.get_user(self.b["id"]))
        self.assertEqual((pub["online"], pub["last_seen"]), (False, None))

    def test_touch_is_throttled(self):
        store.get_store().update("users", self.a["id"], {"last_seen": 1.0})
        services.touch(self.a["id"])
        first = services.get_user(self.a["id"])["last_seen"]
        self.assertGreater(first, 1.0)
        services.touch(self.a["id"])
        self.assertEqual(services.get_user(self.a["id"])["last_seen"], first)


class TestBlocks(SocialBase):
    def test_block_removes_match_and_hides_both_ways(self):
        mid = self.pair()
        services.send_message(mid, self.a["id"], "hi")
        services.block_user(self.a["id"], self.b["id"])
        self.assertEqual(services.list_matches(self.a["id"]), [])
        self.assertIsNone(store.get_store().get("matches", mid))
        self.assertEqual(store.get_store().query(f"matches/{mid}/messages"), [])
        # ни у кого из двоих другой не появляется в ленте и поиске
        self.assertNotIn(self.b["id"], [p["uid"] for p in services.feed(self.a["id"], 10)])
        self.assertEqual(services.search_users(self.a["id"], "Борис"), [])
        self.assertEqual(services.search_users(self.b["id"], "Анна"), [])
        with self.assertRaises(ApiError):
            services.swipe(self.b["id"], self.a["id"], True)
        with self.assertRaises(ApiError):
            services.profile_view(self.b["id"], self.a["id"])

    def test_list_unblock_and_limits(self):
        services.block_user(self.a["id"], self.b["id"])
        services.block_user(self.a["id"], self.b["id"])  # повтор не дублирует
        self.assertEqual([x["uid"] for x in services.list_blocked(self.a["id"])], [self.b["id"]])
        services.unblock_user(self.a["id"], self.b["id"])
        self.assertEqual(services.list_blocked(self.a["id"]), [])
        self.assertIn(self.b["id"], [p["uid"] for p in services.feed(self.a["id"], 10)])
        with self.assertRaises(ApiError):
            services.block_user(self.a["id"], self.a["id"])
        with self.assertRaises(ApiError):
            services.block_user(self.a["id"], "nope")


class TestLikesInbox(SocialBase):
    def test_incoming_likes_until_answered(self):
        self.like(self.b, self.a)
        self.like(self.c, self.a)
        self.assertEqual({p["uid"] for p in services.list_likes(self.a["id"])}, {self.b["id"], self.c["id"]})
        self.like(self.a, self.b, False)
        self.assertEqual([p["uid"] for p in services.list_likes(self.a["id"])], [self.c["id"]])
        self.assertTrue(self.like(self.a, self.c)["matched"])
        self.assertEqual(services.list_likes(self.a["id"]), [])

    def test_dislikes_and_blocked_not_listed(self):
        self.like(self.b, self.a, False)
        self.like(self.c, self.a)
        services.block_user(self.a["id"], self.c["id"])
        self.assertEqual(services.list_likes(self.a["id"]), [])


class TestSearch(SocialBase):
    def test_by_name_interest_age_goal(self):
        self.assertEqual([p["name"] for p in services.search_users(self.a["id"], "бор")], ["Борис"])
        self.assertEqual([p["name"] for p in services.search_users(self.a["id"], "музык")], ["Виктор"])
        self.assertEqual(len(services.search_users(self.a["id"], "")), 2)
        self.assertEqual(services.search_users(self.a["id"], "", age_min=40), [])
        self.assertEqual(services.search_users(self.a["id"], "", goal="friends"), [])

    def test_hidden_self_and_blocked_are_excluded(self):
        services.update_settings(self.b["id"], {"hidden": True})
        names = [p["name"] for p in services.search_users(self.a["id"], "")]
        self.assertEqual(names, ["Виктор"])
        self.assertNotIn("Анна", [p["name"] for p in services.search_users(self.a["id"], "")])


class TestPosts(SocialBase):
    def test_create_list_delete(self):
        p1 = services.create_post(self.a["id"], "  Привет, мир  ")
        self.assertEqual(p1["text"], "Привет, мир")
        p2 = services.create_post(self.a["id"], "С фото", make_jpeg(fmt="JPEG"))
        self.assertTrue(p2["image_url"].startswith("/media/"))
        self.assertEqual([p["id"] for p in services.list_posts(self.a["id"])], [p2["id"], p1["id"]])
        services.delete_post(self.a["id"], p2["id"])
        self.assertEqual(len(services.list_posts(self.a["id"])), 1)
        self.assertEqual(store.get_store().query("media", [("owner", "==", self.a["id"]), ("kind", "==", "post")]), [])

    def test_validation_and_ownership(self):
        for text in ("", "   ", "x" * 1001):
            with self.assertRaises(ApiError) as ctx:
                services.create_post(self.a["id"], text)
            self.assertEqual(ctx.exception.status, 422)
        with self.assertRaises(ApiError):
            services.create_post(self.a["id"], "текст", b"not an image")
        post = services.create_post(self.a["id"], "мой")
        with self.assertRaises(ApiError) as ctx:
            services.delete_post(self.b["id"], post["id"])  # у Бориса такого поста нет
        self.assertEqual(ctx.exception.status, 404)

    def test_post_limit(self):
        for i in range(services.MAX_POSTS):
            services.create_post(self.a["id"], f"п{i}")
        with self.assertRaises(ApiError):
            services.create_post(self.a["id"], "лишний")

    def test_posts_removed_with_user(self):
        services.create_post(self.a["id"], "x", make_jpeg(fmt="JPEG"))
        services.delete_user_cascade(self.a["id"])
        self.assertEqual(store.get_store().query(f"users/{self.a['id']}/posts"), [])
        self.assertEqual(store.get_store().query("media"), [])


class TestMatchesPosts(SocialBase):
    def test_only_pairs_and_self(self):
        services.create_post(self.a["id"], "пост Анны")
        services.create_post(self.b["id"], "пост Бориса")
        services.create_post(self.c["id"], "пост Виктора")
        self.pair()  # пара Анна-Борис
        got = services.matches_posts(self.a["id"])
        self.assertEqual({p["text"] for p in got}, {"пост Анны", "пост Бориса"})
        self.assertNotIn("пост Виктора", {p["text"] for p in got})
        self.assertEqual({p["author"]["name"]: p["author"]["mine"] for p in got}, {"Анна": True, "Борис": False})

    def test_sorted_newest_first_and_limits(self):
        self.pair()
        for i in range(8):
            services.create_post(self.b["id"], f"п{i}")
        got = services.matches_posts(self.a["id"], limit=4, per_user=3)
        self.assertEqual(len(got), 3)  # не больше per_user от одного автора
        self.assertEqual([p["text"] for p in got], ["п7", "п6", "п5"])

    def test_unmatch_and_block_hide_posts(self):
        services.create_post(self.b["id"], "секрет")
        mid = self.pair()
        self.assertEqual(len(services.matches_posts(self.a["id"])), 1)
        services.unmatch(mid, self.a["id"])
        self.assertEqual(services.matches_posts(self.a["id"]), [])

    def test_empty_without_pairs(self):
        self.assertEqual(services.matches_posts(self.a["id"]), [])


class TestProfileView(SocialBase):
    def test_relation_flags(self):
        v = services.profile_view(self.a["id"], self.b["id"])
        self.assertEqual(v["relation"], {"me": False, "matched": False, "match_id": None,
                                         "i_liked": False, "i_passed": False, "liked_me": False})
        self.like(self.b, self.a)
        self.assertTrue(services.profile_view(self.a["id"], self.b["id"])["relation"]["liked_me"])
        mid = self.like(self.a, self.b)["match_id"]
        rel = services.profile_view(self.a["id"], self.b["id"])["relation"]
        self.assertEqual((rel["matched"], rel["match_id"], rel["i_liked"]), (True, mid, True))
        self.assertTrue(services.profile_view(self.a["id"], self.a["id"])["relation"]["me"])

    def test_hidden_profile_visible_only_to_pairs_and_admin(self):
        services.update_settings(self.b["id"], {"hidden": True})
        with self.assertRaises(ApiError) as ctx:
            services.profile_view(self.a["id"], self.b["id"])
        self.assertEqual(ctx.exception.status, 404)
        self.pair()
        self.assertEqual(services.profile_view(self.a["id"], self.b["id"])["profile"]["name"], "Борис")

    def test_no_private_data_exposed(self):
        v = services.profile_view(self.a["id"], self.b["id"])
        self.assertNotIn("email", str(v))
        self.assertNotIn("password", str(v))

    def test_inactive_user_not_found(self):
        services.set_user_active(self.b["id"], False)
        with self.assertRaises(ApiError):
            services.profile_view(self.a["id"], self.b["id"])


class TestReports(SocialBase):
    def test_create_list_resolve(self):
        services.create_report(self.a["id"], self.b["id"], "spam", "реклама", "profile")
        services.create_report(self.a["id"], self.b["id"], "abuse", "", "chat")  # повторная жалоба заменяет прежнюю
        items = services.list_reports()
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["reason"], items[0]["from_name"], items[0]["target"]["name"]), ("abuse", "Анна", "Борис"))
        self.assertEqual(services.stats()["reports_open"], 1)
        services.resolve_report(items[0]["id"], "block")
        self.assertFalse(services.get_user(self.b["id"])["is_active"])
        self.assertEqual(services.list_reports(), [])
        self.assertEqual(services.stats()["reports_open"], 0)

    def test_dismiss_and_errors(self):
        services.create_report(self.a["id"], self.c["id"], "other", "", "profile")
        rid = services.list_reports()[0]["id"]
        services.resolve_report(rid, "dismiss")
        self.assertTrue(services.get_user(self.c["id"])["is_active"])
        with self.assertRaises(ApiError):
            services.resolve_report(rid, "explode")
        with self.assertRaises(ApiError):
            services.resolve_report("nope", "dismiss")
        with self.assertRaises(ApiError):
            services.create_report(self.a["id"], self.a["id"], "spam", "", "profile")

    def test_report_with_block_and_admin_protected(self):
        mid = self.pair()
        services.create_report(self.a["id"], self.b["id"], "spam", "", "chat", also_block=True)
        self.assertIsNone(store.get_store().get("matches", mid))
        admin = services.create_user(validators.validate_registration(form(email="boss@example.com"), services.interest_names()),
                                     self.photo, {"boss@example.com"})
        services.create_report(self.a["id"], admin["id"], "spam", "", "profile")
        with self.assertRaises(ApiError) as ctx:
            services.resolve_report(services.list_reports()[0]["id"], "block")
        self.assertEqual(ctx.exception.status, 403)

    def test_validation(self):
        self.assertEqual(validators.validate_report({"reason": "spam", "details": " a  b ", "context": "chat"}),
                         ("spam", "a b", "chat"))
        self.assertEqual(validators.validate_report({"reason": "spam", "context": "x"})[2], "profile")
        for body in ({}, {"reason": "nope"}, {"reason": "spam", "details": "x" * 501}):
            with self.assertRaises(ApiError) as ctx:
                validators.validate_report(body)
            self.assertEqual(ctx.exception.status, 422)

    def test_reports_removed_with_user(self):
        services.create_report(self.a["id"], self.b["id"], "spam", "", "profile")
        services.delete_user_cascade(self.b["id"])
        self.assertEqual(store.get_store().query("reports"), [])


class TestMessageStatuses(SocialBase):
    def setUp(self):
        super().setUp()
        self.mid = self.pair()

    def test_sent_delivered_read(self):
        msg = services.send_message(self.mid, self.a["id"], "привет")
        r = services.chat_poll(self.mid, self.a["id"])["receipts"]
        self.assertLess(r["delivered_at"], msg["created_at"])  # отправлено, но не доставлено
        services.list_notifications(self.b["id"])  # у Бориса открыт сайт и пришло уведомление
        r = services.chat_poll(self.mid, self.a["id"])["receipts"]
        self.assertGreaterEqual(r["delivered_at"], msg["created_at"])
        self.assertLess(r["read_at"], msg["created_at"])  # ещё не прочитано
        services.chat_poll(self.mid, self.b["id"])  # Борис открыл чат
        r = services.chat_poll(self.mid, self.a["id"])["receipts"]
        self.assertGreaterEqual(r["read_at"], msg["created_at"])

    def test_delivery_flag_is_written_once(self):
        services.send_message(self.mid, self.a["id"], "раз")
        first = services.list_notifications(self.b["id"])
        self.assertFalse(first[0]["delivered"])
        self.assertTrue(services.list_notifications(self.b["id"])[0]["delivered"])

    def test_own_messages_do_not_mark_read(self):
        services.send_message(self.mid, self.a["id"], "я пишу")
        services.chat_poll(self.mid, self.a["id"])
        self.assertEqual(store.get_store().get("matches", self.mid).get(f"read_at_{self.a['id']}", 0), 0)

    def test_typing_indicator(self):
        self.assertFalse(services.chat_poll(self.mid, self.b["id"])["typing"])
        services.set_typing(self.mid, self.a["id"])
        self.assertTrue(services.chat_poll(self.mid, self.b["id"])["typing"])
        self.assertFalse(services.chat_poll(self.mid, self.a["id"])["typing"])  # свой набор себе не показывается
        services.send_message(self.mid, self.a["id"], "готово")
        self.assertFalse(services.chat_poll(self.mid, self.b["id"])["typing"])

    def test_poll_returns_other_presence_and_requires_membership(self):
        out = services.chat_poll(self.mid, self.a["id"])
        self.assertIn("online", out["other"])
        with self.assertRaises(ApiError):
            services.chat_poll(self.mid, self.c["id"])
        with self.assertRaises(ApiError):
            services.set_typing(self.mid, self.c["id"])


if __name__ == "__main__":
    unittest.main()
