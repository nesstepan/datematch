"""Тесты лайков и комментариев к постам (без Django).  Запуск:  python -m unittest core.tests.test_post_social -v"""
import unittest

from core import features, services, store
from core.exceptions import ApiError
from core.tests.test_social import SocialBase


class PostSocialBase(SocialBase):
    def setUp(self):
        super().setUp()
        self.post = services.create_post(self.a["id"], "Мой первый пост")  # автор: Анна
        self.mid = self.pair()                                               # Анна и Борис — пара

    def notes(self, uid, kind):
        return [n for n in features.list_notifications(uid) if n["type"] == kind]


class TestPostLikes(PostSocialBase):
    def test_like_unlike_and_counts(self):
        r = services.like_post(self.b["id"], self.a["id"], self.post["id"])
        self.assertEqual(r, {"liked": True, "likes": 1})
        services.like_post(self.b["id"], self.a["id"], self.post["id"])  # повторный лайк не удваивает
        self.assertEqual(services.like_post(self.a["id"], self.a["id"], self.post["id"])["likes"], 2)  # свой пост тоже можно
        got = services.list_posts(self.a["id"], viewer_uid=self.b["id"])[0]
        self.assertEqual((got["likes"], got["liked"]), (2, True))
        self.assertFalse(services.list_posts(self.a["id"], viewer_uid=self.c["id"])[0]["liked"])
        r = services.like_post(self.b["id"], self.a["id"], self.post["id"], like=False)
        self.assertEqual(r, {"liked": False, "likes": 1})
        services.like_post(self.b["id"], self.a["id"], self.post["id"], like=False)  # повторный дизлайк безопасен

    def test_like_notifies_author_once_and_unlike_removes_it(self):
        services.like_post(self.b["id"], self.a["id"], self.post["id"])
        services.like_post(self.b["id"], self.a["id"], self.post["id"])
        notes = self.notes(self.a["id"], "post_like")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["data"]["author_uid"], self.a["id"])
        services.like_post(self.b["id"], self.a["id"], self.post["id"], like=False)
        self.assertEqual(self.notes(self.a["id"], "post_like"), [])
        services.like_post(self.a["id"], self.a["id"], self.post["id"])  # лайк своего поста уведомлений не шлёт
        self.assertEqual(self.notes(self.a["id"], "post_like"), [])

    def test_unknown_post_and_hidden_author(self):
        with self.assertRaises(ApiError) as ctx:
            services.like_post(self.b["id"], self.a["id"], "nope")
        self.assertEqual(ctx.exception.status, 404)
        services.block_user(self.a["id"], self.c["id"])  # автор заблокировал Виктора
        with self.assertRaises(ApiError) as ctx:
            services.like_post(self.c["id"], self.a["id"], self.post["id"])
        self.assertEqual(ctx.exception.status, 404)

    def test_feed_and_profile_carry_counters(self):
        services.like_post(self.b["id"], self.a["id"], self.post["id"])
        feed = services.matches_posts(self.b["id"])
        self.assertEqual((feed[0]["likes"], feed[0]["liked"], feed[0]["uid"]), (1, True, self.a["id"]))
        page = services.profile_view(self.b["id"], self.a["id"])["posts"][0]
        self.assertEqual((page["likes"], page["liked"], page["comments"]), (1, True, 0))


class TestPostComments(PostSocialBase):
    def test_add_list_count(self):
        r = services.add_comment(self.b["id"], self.a["id"], self.post["id"], "  Классный   пост!  ")
        self.assertEqual(r["comments"], 1)
        self.assertEqual(r["comment"]["text"], "Классный пост!")
        self.assertTrue(r["comment"]["mine"])
        services.add_comment(self.a["id"], self.a["id"], self.post["id"], "Спасибо")
        listed = services.list_comments(self.a["id"], self.a["id"], self.post["id"])
        self.assertEqual([c["text"] for c in listed], ["Классный пост!", "Спасибо"])
        self.assertEqual([c["mine"] for c in listed], [False, True])      # глазами автора поста
        self.assertTrue(all(c["can_delete"] for c in listed))             # хозяин поста удаляет любые
        seen_by_b = services.list_comments(self.b["id"], self.a["id"], self.post["id"])
        self.assertEqual([c["can_delete"] for c in seen_by_b], [True, False])
        self.assertEqual(services.list_posts(self.a["id"])[0]["comments"], 2)

    def test_validation(self):
        for bad in ("", "   ", "x" * 501):
            with self.assertRaises(ApiError) as ctx:
                services.add_comment(self.b["id"], self.a["id"], self.post["id"], bad)
            self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(services.list_posts(self.a["id"])[0]["comments"], 0)

    def test_notification_goes_to_author_only(self):
        services.add_comment(self.b["id"], self.a["id"], self.post["id"], "Привет!")
        notes = self.notes(self.a["id"], "comment")
        self.assertEqual(len(notes), 1)
        self.assertIn("Борис", notes[0]["text"])
        self.assertEqual(notes[0]["data"]["post_id"], self.post["id"])
        services.add_comment(self.a["id"], self.a["id"], self.post["id"], "Ответ себе")
        self.assertEqual(len(self.notes(self.a["id"], "comment")), 1)
        self.assertEqual(self.notes(self.b["id"], "comment"), [])

    def test_delete_rules(self):
        cb = services.add_comment(self.b["id"], self.a["id"], self.post["id"], "от Бориса")["comment"]["id"]
        with self.assertRaises(ApiError) as ctx:  # посторонний удалить не может
            services.delete_comment(self.c["id"], self.a["id"], self.post["id"], cb)
        self.assertIn(ctx.exception.status, (403, 404))
        r = services.delete_comment(self.b["id"], self.a["id"], self.post["id"], cb)  # автор комментария
        self.assertEqual(r["comments"], 0)
        self.assertEqual(self.notes(self.a["id"], "comment"), [])
        cb2 = services.add_comment(self.b["id"], self.a["id"], self.post["id"], "ещё")["comment"]["id"]
        services.delete_comment(self.a["id"], self.a["id"], self.post["id"], cb2)       # хозяин поста
        with self.assertRaises(ApiError) as ctx:
            services.delete_comment(self.a["id"], self.a["id"], self.post["id"], cb2)
        self.assertEqual(ctx.exception.status, 404)

    def test_blocked_user_cannot_comment_or_read(self):
        services.block_user(self.b["id"], self.c["id"])
        with self.assertRaises(ApiError):
            services.add_comment(self.c["id"], self.b["id"], services.create_post(self.b["id"], "пост Бориса")["id"], "привет")

    def test_comment_limit(self):
        services.MAX_COMMENTS, old = 2, services.MAX_COMMENTS
        try:
            services.add_comment(self.b["id"], self.a["id"], self.post["id"], "1")
            services.add_comment(self.b["id"], self.a["id"], self.post["id"], "2")
            with self.assertRaises(ApiError):
                services.add_comment(self.b["id"], self.a["id"], self.post["id"], "3")
        finally:
            services.MAX_COMMENTS = old

    def test_deleted_author_shown_neutrally(self):
        services.add_comment(self.b["id"], self.a["id"], self.post["id"], "я скоро уйду")
        services.delete_user_cascade(self.b["id"])
        c = services.list_comments(self.a["id"], self.a["id"], self.post["id"])[0]
        self.assertEqual(c["author"]["name"], "Удалённый пользователь")

    def test_removing_post_or_account_removes_comments(self):
        services.add_comment(self.b["id"], self.a["id"], self.post["id"], "x")
        path = f"users/{self.a['id']}/posts/{self.post['id']}/comments"
        self.assertEqual(len(store.get_store().query(path)), 1)
        services.delete_post(self.a["id"], self.post["id"])
        self.assertEqual(store.get_store().query(path), [])
        p2 = services.create_post(self.a["id"], "второй")
        services.add_comment(self.b["id"], self.a["id"], p2["id"], "y")
        services.delete_user_cascade(self.a["id"])
        self.assertEqual(store.get_store().query(f"users/{self.a['id']}/posts/{p2['id']}/comments"), [])


class TestAchievementText(PostSocialBase):
    def test_notification_has_no_internal_icon_name(self):
        for n in self.notes(self.a["id"], "achievement"):
            self.assertNotIn("heart ", n["text"]); self.assertNotIn("hearts ", n["text"])
            self.assertRegex(n["text"], r"^Достижение: [А-Яа-я ]+")


if __name__ == "__main__":
    unittest.main()
