"""Тесты новых функций (без Django): фильтры, скрытие, видео, медиа в чате, подарки, удаление, уведомления,
достижения, сигналы звонков.  Запуск:  python -m unittest core.tests.test_features -v"""
import io
import unittest

from PIL import Image

from core import features, media, security, services, store, validators
from core.exceptions import ApiError

security.ITERATIONS = 1000

MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00" + b"\x00" * 200
WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 200


def img(fmt="PNG", size=(900, 700)):
    buf = io.BytesIO()
    Image.new("RGB", size, (10, 200, 90)).save(buf, fmt)
    return buf.getvalue()


def gif():
    buf = io.BytesIO()
    frames = [Image.new("P", (40, 40), i) for i in (0, 1)]
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    return buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.photo = validators.process_photo(img())
        self.a = self.user("a@example.com", "Аня", "female", "male", age="25")
        self.b = self.user("b@example.com", "Борис", "male", "female", age="30", interests=["Кофе"])

    def user(self, email, name, gender, looking, age="25", interests=("Кино",)):
        form = {"email": email, "password": "secret123", "name": name, "age": age, "gender": gender,
                "looking_for": looking, "bio": "Привет", "interests": list(interests)}
        return services.create_user(validators.validate_registration(form, services.interest_names()), self.photo)

    def pair(self):
        services.swipe(self.a["id"], self.b["id"], True)
        res = services.swipe(self.b["id"], self.a["id"], True)
        self.assertTrue(res["matched"])
        return res["match_id"]


class TestFeedFilters(Base):
    def uids(self, **f):
        return [p["uid"] for p in services.feed(self.a["id"], 20, f)]

    def test_age_range(self):
        self.assertEqual(self.uids(age_min=28, age_max=35), [self.b["id"]])
        self.assertEqual(self.uids(age_min=40), [])
        self.assertEqual(self.uids(age_max=29), [])

    def test_interests_any_match(self):
        self.assertEqual(self.uids(interests=["кофе", "Йога"]), [self.b["id"]])
        self.assertEqual(self.uids(interests=["Йога"]), [])

    def test_with_video_and_music(self):
        self.assertEqual(self.uids(with_video=True), [])
        services.set_video(self.b["id"], MP4)
        self.assertEqual(self.uids(with_video=True), [self.b["id"]])
        self.assertEqual(self.uids(with_music=True), [])
        services.update_settings(self.b["id"], {"music_title": "Кино — Группа крови"})
        self.assertEqual(self.uids(with_music=True), [self.b["id"]])


class TestHidden(Base):
    def test_hidden_user_not_in_feed_but_can_browse(self):
        services.update_settings(self.b["id"], {"hidden": True})
        self.assertEqual(services.feed(self.a["id"], 10), [])
        self.assertEqual(len(services.feed(self.b["id"], 10)), 1)  # сам скрытый всё ещё листает ленту
        services.update_settings(self.b["id"], {"hidden": False})
        self.assertEqual(len(services.feed(self.a["id"], 10)), 1)

    def test_settings_validation(self):
        for bad in ({"hidden": "yes"}, {"accent": "red"}, {"music_url": "javascript:alert(1)"},
                    {"status": "x" * 61}, {"music_title": "x" * 81}):
            with self.assertRaises(ApiError) as ctx:
                services.update_settings(self.a["id"], bad)
            self.assertEqual(ctx.exception.status, 422)
        u = services.update_settings(self.a["id"], {"accent": "#FF5C8A", "music_url": "https://music.example/x"})
        self.assertEqual(u["accent"], "#ff5c8a")


class TestVideo(Base):
    def test_set_replace_remove(self):
        services.set_video(self.a["id"], MP4)
        first = services.get_user(self.a["id"])["video_id"]
        self.assertTrue(services.public_profile(services.get_user(self.a["id"]))["video_url"].startswith("/media/"))
        services.set_video(self.a["id"], WEBM)
        self.assertNotEqual(first, services.get_user(self.a["id"])["video_id"])
        self.assertIsNone(store.get_store().get("media", first))  # старое видео стёрто
        services.remove_video(self.a["id"])
        self.assertEqual(services.public_profile(services.get_user(self.a["id"]))["video_url"], "")

    def test_rejects_non_video_and_big(self):
        for raw in (img(), b"hello", b""):
            with self.assertRaises(ApiError):
                services.set_video(self.a["id"], raw)
        with self.assertRaises(ApiError):
            services.set_video(self.a["id"], MP4 + b"\x00" * (6 * 1024 * 1024))

    def test_video_visible_to_any_user_but_not_private_media(self):
        services.set_video(self.a["id"], MP4)
        vid = services.get_user(self.a["id"])["video_id"]
        meta, data = services.get_media_for(vid, self.b["id"])
        self.assertEqual(meta["content_type"], "video/mp4")
        self.assertEqual(data, MP4)

    def test_large_file_is_chunked_and_restored(self):
        raw = MP4 + bytes(range(256)) * 9000  # ~2,3 МБ - несколько кусков
        services.set_video(self.a["id"], raw)
        vid = services.get_user(self.a["id"])["video_id"]
        self.assertGreater(len(store.get_store().query(f"media/{vid}/chunks")), 2)
        media._cache.clear(); media._cache_size = 0
        self.assertEqual(services.get_media_for(vid, self.b["id"])[1], raw)


class TestChatMedia(Base):
    def test_sniff(self):
        self.assertEqual(media.sniff(img("PNG"))[0], "image")
        self.assertEqual(media.sniff(gif())[0], "gif")
        self.assertEqual(media.sniff(MP4), ("video", "video/mp4"))
        self.assertEqual(media.sniff(b"<script>alert(1)</script>"), (None, None))

    def test_send_image_gif_video_voice(self):
        mid = self.pair()
        m1 = services.send_media(mid, self.a["id"], img("WEBP"))
        m2 = services.send_media(mid, self.a["id"], gif())
        m3 = services.send_media(mid, self.a["id"], MP4, caption="смотри")
        m4 = services.send_media(mid, self.a["id"], WEBM, hint="voice", duration="12")
        self.assertEqual([m["type"] for m in (m1, m2, m3, m4)], ["image", "gif", "video", "voice"])
        self.assertEqual(m3["text"], "смотри")
        self.assertEqual(m4["duration"], 12)
        meta, data = services.get_media_for(m1["media_url"].split("/")[2], self.b["id"])  # собеседник видит
        self.assertEqual(meta["content_type"], "image/jpeg")  # фото пережато в JPEG
        self.assertEqual(services.get_media_for(m4["media_url"].split("/")[2], self.a["id"])[0]["content_type"], "audio/webm")
        listed = services.list_messages(mid, self.b["id"])
        self.assertEqual([m["type"] for m in listed], ["image", "gif", "video", "voice"])
        self.assertFalse(listed[0]["mine"])

    def test_rejects_bad_files(self):
        mid = self.pair()
        for raw, hint in ((b"MZ\x90\x00 exe", ""), (b"", ""), (b"text", "voice"), (img(), "voice")):
            with self.assertRaises(ApiError):
                services.send_media(mid, self.a["id"], raw, hint)
        with self.assertRaises(ApiError):  # GIF больше 3 МБ
            services.send_media(mid, self.a["id"], gif() + b"\x00" * (3 * 1024 * 1024))

    def test_outsider_cannot_read_or_send(self):
        mid = self.pair()
        c = self.user("c@example.com", "Вера", "female", "male")
        m = services.send_media(mid, self.a["id"], img())
        with self.assertRaises(ApiError) as ctx:
            services.get_media_for(m["media_url"].split("/")[2], c["id"])
        self.assertEqual(ctx.exception.status, 404)
        with self.assertRaises(ApiError):
            services.send_media(mid, c["id"], img())

    def test_unmatch_and_account_delete_remove_files(self):
        mid = self.pair()
        services.send_media(mid, self.a["id"], img())
        services.set_video(self.a["id"], MP4)
        self.assertEqual(len(store.get_store().query("media")), 2)
        services.unmatch(mid, self.b["id"])
        self.assertEqual(len(store.get_store().query("media")), 1)
        services.delete_user_cascade(self.a["id"])
        self.assertEqual(store.get_store().query("media"), [])
        self.assertEqual(store.get_store().query("media/x/chunks"), [])


class TestGiftsAndDelete(Base):
    def test_gift(self):
        mid = self.pair()
        m = services.send_gift(mid, self.a["id"], "rose")
        self.assertEqual(m["type"], "gift"); self.assertEqual(m["gift"]["icon"], "g-rose")
        with self.assertRaises(ApiError):
            services.send_gift(mid, self.a["id"], "nope")
        self.assertEqual(services.get_user(self.b["id"])["stats"]["gifts_received"], 1)

    def test_delete_own_message_only(self):
        mid = self.pair()
        m = services.send_message(mid, self.a["id"], "секрет")
        with self.assertRaises(ApiError) as ctx:
            services.delete_message(mid, self.b["id"], m["id"])
        self.assertEqual(ctx.exception.status, 403)
        services.delete_message(mid, self.a["id"], m["id"])
        msgs, deleted = services.list_messages(mid, self.b["id"], with_deleted=True)
        self.assertEqual(deleted, [m["id"]])
        self.assertTrue(msgs[0]["deleted"]); self.assertEqual(msgs[0]["text"], "")
        self.assertEqual(services.list_matches(self.b["id"])[0]["last_message"], "Сообщение удалено")
        services.delete_message(mid, self.a["id"], m["id"])  # повторное удаление безопасно

    def test_delete_media_message_removes_file(self):
        mid = self.pair()
        m = services.send_media(mid, self.a["id"], img())
        self.assertEqual(len(store.get_store().query("media")), 1)
        services.delete_message(mid, self.a["id"], m["id"])
        self.assertEqual(store.get_store().query("media"), [])

    def test_delete_unknown_and_foreign_match(self):
        mid = self.pair()
        with self.assertRaises(ApiError):
            services.delete_message(mid, self.a["id"], "nope")
        c = self.user("c@example.com", "Вера", "female", "male")
        with self.assertRaises(ApiError):
            services.delete_message(mid, c["id"], "x")


class TestNotifications(Base):
    def types(self, uid):
        return sorted(n["type"] for n in features.list_notifications(uid))

    def test_like_is_anonymous_and_not_duplicated(self):
        services.swipe(self.a["id"], self.b["id"], True)
        services.swipe(self.a["id"], self.b["id"], True)
        notes = features.list_notifications(self.b["id"])
        likes = [n for n in notes if n["type"] == "like"]
        self.assertEqual(len(likes), 1)
        self.assertEqual(likes[0]["from_name"], "")
        self.assertNotIn(self.a["id"], str(likes[0]["text"]))

    def test_dislike_does_not_notify(self):
        services.swipe(self.a["id"], self.b["id"], False)
        self.assertEqual(self.types(self.b["id"]), [])

    def test_match_notifies_first_liker(self):
        services.swipe(self.a["id"], self.b["id"], True)
        services.swipe(self.b["id"], self.a["id"], True)
        self.assertIn("match", self.types(self.a["id"]))
        self.assertNotIn("like", self.types(self.b["id"]))  # у второго симпатия уже взаимная
        self.assertNotIn("like", self.types(self.a["id"]))

    def test_message_notification_and_read(self):
        mid = self.pair()
        services.send_message(mid, self.a["id"], "привет")
        notes = [n for n in features.list_notifications(self.b["id"]) if n["type"] == "message"]
        self.assertEqual(len(notes), 1); self.assertEqual(notes[0]["match_id"], mid)
        self.assertTrue(notes[0]["text"].startswith("Аня:"))
        features.mark_read(self.b["id"], match_id=mid, types=["message"])
        self.assertEqual([n for n in features.list_notifications(self.b["id"]) if n["type"] == "message"], [])
        self.assertEqual([n for n in features.list_notifications(self.a["id"]) if n["type"] == "message"], [])

    def test_mark_read_is_scoped_to_user(self):
        services.swipe(self.a["id"], self.b["id"], True)
        features.mark_read(self.a["id"])  # чужие уведомления не трогаем
        self.assertEqual(self.types(self.b["id"]), ["like"])

    def test_deleted_message_drops_notification(self):
        mid = self.pair()
        m = services.send_message(mid, self.a["id"], "oops")
        services.delete_message(mid, self.a["id"], m["id"])
        self.assertEqual([n for n in features.list_notifications(self.b["id"]) if n["type"] == "message"], [])


class TestAchievements(Base):
    def earned(self, uid):
        return set(services.get_user(uid).get("achievements", []))

    def test_progression(self):
        mid = self.pair()
        self.assertTrue({"first_like", "first_match"} <= self.earned(self.a["id"]))
        services.send_message(mid, self.a["id"], "hi")
        services.send_gift(mid, self.a["id"], "rose")
        services.send_media(mid, self.a["id"], WEBM, hint="voice", duration=3)
        services.set_video(self.a["id"], MP4)
        got = self.earned(self.a["id"])
        self.assertTrue({"icebreaker", "gift_giver", "voice", "on_camera"} <= got)
        self.assertNotIn("chatterbox", got)
        notes = [n["text"] for n in features.list_notifications(self.a["id"]) if n["type"] == "achievement"]
        self.assertTrue(any("Первая пара" in t for t in notes))

    def test_no_duplicates_and_full_profile(self):
        services.set_video(self.a["id"], MP4)
        services.update_settings(self.a["id"], {"music_title": "Трек", "accent": "#112233"})
        services.update_settings(self.a["id"], {"status": "ещё раз"})
        got = services.get_user(self.a["id"])["achievements"]
        self.assertEqual(len(got), len(set(got)))
        self.assertIn("full_profile", got)
        self.assertEqual(sum(1 for n in features.list_notifications(self.a["id"]) if n["id"].endswith("full_profile")), 1)

    def test_badges_in_public_profile(self):
        self.pair()
        badges = services.public_profile(services.get_user(self.a["id"]))["badges"]
        self.assertIn("first_match", [b["id"] for b in badges])
        self.assertTrue(all(b["icon"] and b["title"] for b in badges))


class TestCallSignals(Base):
    def test_offer_answer_flow(self):
        mid = self.pair()
        services.post_call_signal(mid, self.a["id"], "offer", {"sdp": {"type": "offer", "sdp": "x"}, "video": True})
        call = [n for n in features.list_notifications(self.b["id"]) if n["type"] == "call"]
        self.assertEqual(len(call), 1); self.assertTrue(call[0]["data"]["video"])
        services.post_call_signal(mid, self.a["id"], "candidate", {"candidate": "c1"})
        sig = services.get_call_signals(mid, self.b["id"], 0)
        self.assertEqual([s["kind"] for s in sig], ["offer", "candidate"])
        self.assertEqual(services.get_call_signals(mid, self.a["id"], 0), [])  # свои сигналы не возвращаются
        services.post_call_signal(mid, self.b["id"], "answer", {"sdp": {"type": "answer", "sdp": "y"}})
        self.assertEqual([s["kind"] for s in services.get_call_signals(mid, self.a["id"], 0)], ["answer"])
        self.assertEqual([n for n in features.list_notifications(self.b["id"]) if n["type"] == "call"], [])
        self.assertIn("caller", set(services.get_user(self.a["id"]).get("achievements", [])))

    def test_hangup_removes_ring_and_new_offer_clears_old(self):
        mid = self.pair()
        services.post_call_signal(mid, self.a["id"], "offer", {"video": False})
        services.post_call_signal(mid, self.a["id"], "hangup", {})
        self.assertEqual([n for n in features.list_notifications(self.b["id"]) if n["type"] == "call"], [])
        services.post_call_signal(mid, self.a["id"], "offer", {"video": False})
        self.assertEqual([s["kind"] for s in services.get_call_signals(mid, self.b["id"], 0)], ["offer"])

    def test_since_and_validation_and_access(self):
        mid = self.pair()
        services.post_call_signal(mid, self.a["id"], "offer", {})
        first = services.get_call_signals(mid, self.b["id"], 0)[0]["created_at"]
        services.post_call_signal(mid, self.a["id"], "candidate", {"candidate": "c"})
        self.assertEqual([s["kind"] for s in services.get_call_signals(mid, self.b["id"], first)], ["candidate"])
        with self.assertRaises(ApiError):
            services.post_call_signal(mid, self.a["id"], "evil", {})
        with self.assertRaises(ApiError):
            services.post_call_signal(mid, self.a["id"], "candidate", {"x": "y" * 30000})
        c = self.user("c@example.com", "Вера", "female", "male")
        with self.assertRaises(ApiError):
            services.get_call_signals(mid, c["id"], 0)

    def test_signals_cleaned_on_unmatch(self):
        mid = self.pair()
        services.post_call_signal(mid, self.a["id"], "offer", {})
        services.unmatch(mid, self.a["id"])
        self.assertEqual(store.get_store().query(f"matches/{mid}/signals"), [])


class TestCascade(Base):
    def test_notifications_removed_with_account(self):
        mid = self.pair()
        services.send_message(mid, self.a["id"], "hi")
        services.delete_user_cascade(self.a["id"])
        self.assertEqual([n for n in features.list_notifications(self.b["id"]) if n["type"] == "message"], [])


if __name__ == "__main__":
    unittest.main()
