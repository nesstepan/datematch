"""Тесты ответов на сообщения (без Django).  Запуск:  python -m unittest core.tests.test_replies -v"""
import unittest

from core import services, store
from core.exceptions import ApiError
from core.tests.test_social import SocialBase

PNG = None


class TestReplies(SocialBase):
    def setUp(self):
        super().setUp()
        self.mid = self.pair()

    def poll(self, uid):
        return services.chat_poll(self.mid, uid, None)["messages"]

    def test_reply_to_text(self):
        first = services.send_message(self.mid, self.a["id"], "Пойдём гулять?")
        r = services.send_message(self.mid, self.b["id"], "Да, давай!", reply_to=first["id"])
        self.assertEqual(r["reply_to"], {"id": first["id"], "mine": False, "type": "text", "text": "Пойдём гулять?"})
        mine_view = [m for m in self.poll(self.a["id"]) if m["id"] == r["id"]][0]
        self.assertFalse(mine_view["mine"])
        self.assertTrue(mine_view["reply_to"]["mine"])                      # для Ани цитата — её собственное сообщение
        self.assertIsNone([m for m in self.poll(self.a["id"]) if m["id"] == first["id"]][0]["reply_to"])

    def test_reply_to_own_message_and_chain(self):
        m1 = services.send_message(self.mid, self.a["id"], "один")
        m2 = services.send_message(self.mid, self.a["id"], "два", reply_to=m1["id"])
        m3 = services.send_message(self.mid, self.b["id"], "три", reply_to=m2["id"])
        self.assertEqual(m3["reply_to"]["text"], "два")                    # цитата без вложенных цитат
        self.assertTrue(m2["reply_to"]["mine"])

    def test_previews_for_media_and_gifts(self):
        gift = services.send_gift(self.mid, self.a["id"], "rose")
        r = services.send_message(self.mid, self.b["id"], "Спасибо!", reply_to=gift["id"])
        self.assertTrue(r["reply_to"]["text"].startswith("Подарок"))
        long = services.send_message(self.mid, self.a["id"], "я" * 900)
        r2 = services.send_message(self.mid, self.b["id"], "ого", reply_to=long["id"])
        self.assertEqual(len(r2["reply_to"]["text"]), 140)                  # длинные цитаты обрезаются

    def test_reply_with_gift_and_media(self):
        m = services.send_message(self.mid, self.a["id"], "привет")
        g = services.send_gift(self.mid, self.b["id"], "rose", reply_to=m["id"])
        self.assertEqual(g["reply_to"]["id"], m["id"])
        from core.tests.test_features import MP4
        v = services.send_media(self.mid, self.b["id"], MP4, reply_to=m["id"])
        self.assertEqual(v["reply_to"]["text"], "привет")

    def test_invalid_replies_rejected(self):
        for bad in ("nope", "x" * 80, 123):
            with self.assertRaises(ApiError) as ctx:
                services.send_message(self.mid, self.a["id"], "текст", reply_to=bad)
            self.assertEqual(ctx.exception.status, 422)
        self.assertEqual(len(self.poll(self.a["id"])), 0)                   # ничего не сохранилось

    def test_cannot_reply_to_deleted_and_other_matches(self):
        m = services.send_message(self.mid, self.a["id"], "секрет")
        services.delete_message(self.mid, self.a["id"], m["id"])
        with self.assertRaises(ApiError):
            services.send_message(self.mid, self.b["id"], "ответ", reply_to=m["id"])
        # сообщение из чужого чата найти нельзя: у Анны есть вторая пара — с Виктором
        other_mid = self.pair(self.a, self.c)
        foreign = services.send_message(other_mid, self.a["id"], "в другом чате")
        with self.assertRaises(ApiError):
            services.send_message(self.mid, self.a["id"], "подмена", reply_to=foreign["id"])

    def test_quote_text_hidden_after_original_deleted(self):
        m = services.send_message(self.mid, self.a["id"], "я передумаю")
        services.send_message(self.mid, self.b["id"], "хорошо", reply_to=m["id"])
        services.delete_message(self.mid, self.a["id"], m["id"])
        reply = [x for x in self.poll(self.b["id"]) if x["text"] == "хорошо"][0]
        self.assertEqual(reply["reply_to"]["text"], "")
        self.assertTrue(reply["reply_to"]["deleted"])

    def test_deleted_reply_has_no_quote(self):
        m = services.send_message(self.mid, self.a["id"], "один")
        r = services.send_message(self.mid, self.b["id"], "два", reply_to=m["id"])
        services.delete_message(self.mid, self.b["id"], r["id"])
        got = [x for x in self.poll(self.a["id"]) if x["id"] == r["id"]][0]
        self.assertIsNone(got["reply_to"])


if __name__ == "__main__":
    unittest.main()
