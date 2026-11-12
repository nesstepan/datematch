"""Тесты реакций на сообщения (без Django).  Запуск:  python -m unittest core.tests.test_reactions -v"""
import unittest

from core import services
from core.exceptions import ApiError
from core.tests.test_social import SocialBase


class TestReactions(SocialBase):
    def setUp(self):
        super().setUp()
        self.mid = self.pair()
        self.m = services.send_message(self.mid, self.a["id"], "Привет!")

    def poll(self, uid):
        return services.chat_poll(self.mid, uid, None)

    def view(self, uid):
        return [x for x in self.poll(uid)["messages"] if x["id"] == self.m["id"]][0]["reactions"]

    def test_set_replace_and_remove(self):
        r = services.react_message(self.mid, self.b["id"], self.m["id"], "fire")
        self.assertEqual(r["reactions"], [{"kind": "fire", "count": 1, "mine": True}])
        self.assertEqual(self.view(self.a["id"]), [{"kind": "fire", "count": 1, "mine": False}])   # автор видит, что реакция не его
        services.react_message(self.mid, self.b["id"], self.m["id"], "like")                       # одна реакция от человека: заменяется
        self.assertEqual([x["kind"] for x in self.view(self.b["id"])], ["like"])
        services.react_message(self.mid, self.b["id"], self.m["id"], None)
        self.assertEqual(self.view(self.b["id"]), [])
        services.react_message(self.mid, self.b["id"], self.m["id"], "")                           # повторное снятие безопасно
        self.assertEqual(self.poll(self.b["id"])["reactions"], {})

    def test_both_participants_and_counts(self):
        services.react_message(self.mid, self.a["id"], self.m["id"], "heart")
        services.react_message(self.mid, self.b["id"], self.m["id"], "heart")
        self.assertEqual(self.view(self.a["id"]), [{"kind": "heart", "count": 2, "mine": True}])
        services.react_message(self.mid, self.b["id"], self.m["id"], "sad")
        self.assertEqual([(x["kind"], x["count"], x["mine"]) for x in self.view(self.b["id"])], [("heart", 1, False), ("sad", 1, True)])

    def test_poll_returns_reactions_for_old_messages(self):
        services.react_message(self.mid, self.b["id"], self.m["id"], "laugh")
        later = services.send_message(self.mid, self.b["id"], "новое")
        p = services.chat_poll(self.mid, self.a["id"], since=later["created_at"] - 0.0001)
        self.assertEqual([x["id"] for x in p["messages"]], [later["id"]])                            # старого сообщения в ответе нет
        self.assertEqual(p["reactions"][self.m["id"]], [{"kind": "laugh", "count": 1, "mine": False}])  # но реакция на него есть

    def test_validation(self):
        for bad in ("poop", 5, "FIRE"):
            with self.assertRaises(ApiError) as ctx:
                services.react_message(self.mid, self.b["id"], self.m["id"], bad)
            self.assertEqual(ctx.exception.status, 422)
        with self.assertRaises(ApiError) as ctx:
            services.react_message(self.mid, self.b["id"], "nope", "fire")
        self.assertEqual(ctx.exception.status, 404)

    def test_outsider_cannot_react(self):
        with self.assertRaises(ApiError) as ctx:
            services.react_message(self.mid, self.c["id"], self.m["id"], "fire")
        self.assertEqual(ctx.exception.status, 404)

    def test_deleted_message_loses_reactions_and_blocks_new_ones(self):
        services.react_message(self.mid, self.b["id"], self.m["id"], "fire")
        services.delete_message(self.mid, self.a["id"], self.m["id"])
        self.assertEqual(self.poll(self.b["id"])["reactions"], {})
        with self.assertRaises(ApiError):
            services.react_message(self.mid, self.b["id"], self.m["id"], "like")

    def test_old_reactions_are_pruned(self):
        services.MAX_REACTED, old = 3, services.MAX_REACTED
        try:
            ids = [services.send_message(self.mid, self.a["id"], f"м{i}")["id"] for i in range(6)]
            for i in ids:
                services.react_message(self.mid, self.b["id"], i, "like")
            self.assertLessEqual(len(self.poll(self.b["id"])["reactions"]), 3)
            self.assertIn(ids[-1], self.poll(self.b["id"])["reactions"])                              # свежая реакция не теряется
        finally:
            services.MAX_REACTED = old


if __name__ == "__main__":
    unittest.main()
