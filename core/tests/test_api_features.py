"""HTTP-тесты новых функций (нужен Django): USE_MEMORY_DB=1 python manage.py test"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from PIL import Image

from core import security, services, store

MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00" + bytes(range(256)) * 4
JSON = "application/json"


def png():
    buf = io.BytesIO()
    Image.new("RGB", (800, 900), (120, 80, 200)).save(buf, "PNG")
    return buf.getvalue()


def reg(email, name, gender, looking):
    return {"email": email, "password": "secret123", "name": name, "age": "24", "gender": gender,
            "looking_for": looking, "bio": "Привет", "interests": ["Кино"],
            "photo": SimpleUploadedFile("p.png", png(), content_type="image/png")}


@override_settings(USE_MEMORY_DB=True)
class FeatureApiTests(SimpleTestCase):
    def setUp(self):
        security.ITERATIONS = 1000
        security.login_limiter._hits.clear()
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.a, self.b = Client(), Client()
        self.ua = self.a.post("/api/auth/register/", reg("a@example.com", "Аня", "female", "male")).json()["user"]
        self.ub = self.b.post("/api/auth/register/", reg("b@example.com", "Борис", "male", "female")).json()["user"]

    def pair(self):
        self.a.post("/api/swipes/", {"target_uid": self.ub["uid"], "like": True}, content_type=JSON)
        r = self.b.post("/api/swipes/", {"target_uid": self.ua["uid"], "like": True}, content_type=JSON).json()
        return r["match_id"]

    def test_feed_filters_and_hidden(self):
        self.assertEqual(len(self.a.get("/api/feed/?age_min=20&age_max=30").json()["profiles"]), 1)
        self.assertEqual(self.a.get("/api/feed/?age_min=30").json()["profiles"], [])
        self.assertEqual(self.a.get("/api/feed/?with_video=1").json()["profiles"], [])
        self.assertEqual(self.a.get("/api/feed/?age_min=50&age_max=20").status_code, 422)
        self.assertEqual(self.a.get("/api/feed/?age_min=abc").status_code, 400)
        r = self.b.post("/api/me/settings/", {"hidden": True}, content_type=JSON)
        self.assertTrue(r.json()["user"]["hidden"])
        self.assertEqual(self.a.get("/api/feed/").json()["profiles"], [])

    def test_settings_validation(self):
        r = self.a.post("/api/me/settings/", {"accent": "red", "music_url": "ftp://x"}, content_type=JSON)
        self.assertEqual(r.status_code, 422)
        self.assertEqual({"accent", "music_url"}, set(r.json()["error"]["fields"]))
        ok = self.a.post("/api/me/settings/", {"accent": "#aabbcc", "status": "Привет", "music_title": "Трек"}, content_type=JSON)
        self.assertEqual(ok.json()["user"]["accent"], "#aabbcc")

    def test_profile_video_upload_and_streaming_range(self):
        up = self.a.post("/api/me/video/", {"video": SimpleUploadedFile("v.mp4", MP4, content_type="video/mp4")})
        self.assertEqual(up.status_code, 201)
        url = up.json()["user"]["video_url"]
        full = self.b.get(url)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full["Content-Type"], "video/mp4")
        self.assertEqual(full["Accept-Ranges"], "bytes")
        part = self.b.get(url, HTTP_RANGE="bytes=0-9")
        self.assertEqual(part.status_code, 206)
        self.assertEqual(len(part.content), 10)
        self.assertEqual(part["Content-Range"], f"bytes 0-9/{len(MP4)}")
        self.assertEqual(self.b.get(url, HTTP_RANGE="bytes=99999-").status_code, 416)
        self.assertEqual(self.a.delete("/api/me/video/").json()["user"]["video_url"], "")
        self.assertEqual(self.b.get(url).status_code, 404)

    def test_video_upload_rejects_garbage(self):
        r = self.a.post("/api/me/video/", {"video": SimpleUploadedFile("v.mp4", b"not a video", content_type="video/mp4")})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.a.post("/api/me/video/", {}).status_code, 422)

    def test_media_requires_login(self):
        self.a.post("/api/me/video/", {"video": SimpleUploadedFile("v.mp4", MP4, content_type="video/mp4")})
        url = self.a.get("/api/me/").json()["user"]["video_url"]
        self.assertEqual(Client().get(url).status_code, 401)

    def test_chat_attachments_gift_delete(self):
        mid = self.pair()
        base = f"/api/matches/{mid}/messages/"
        up = self.a.post(base, {"file": SimpleUploadedFile("x.png", png(), content_type="image/png"), "text": "вот"})
        self.assertEqual(up.status_code, 201)
        msg = up.json()["message"]
        self.assertEqual(msg["type"], "image")
        self.assertEqual(self.b.get(msg["media_url"]).status_code, 200)
        voice = self.a.post(base, {"file": SimpleUploadedFile("v.webm", b"\x1aE\xdf\xa3" + b"\x00" * 50), "kind": "voice", "duration": "5"})
        self.assertEqual(voice.json()["message"]["type"], "voice")
        bad = self.a.post(base, {"file": SimpleUploadedFile("x.exe", b"MZ\x90\x00")})
        self.assertEqual(bad.status_code, 422)
        gift = self.a.post(base, {"gift": "rose"}, content_type=JSON)
        self.assertEqual(gift.json()["message"]["gift"]["icon"], "g-rose")
        self.assertEqual(self.a.post(base, {"gift": "zzz"}, content_type=JSON).status_code, 422)
        # чужой не может удалить, свой — может, собеседник видит «удалено»
        self.assertEqual(self.b.delete(f"{base}{msg['id']}/").status_code, 403)
        self.assertEqual(self.a.delete(f"{base}{msg['id']}/").status_code, 200)
        data = self.b.get(base).json()
        self.assertIn(msg["id"], data["deleted"])
        self.assertTrue(next(m for m in data["messages"] if m["id"] == msg["id"])["deleted"])
        self.assertEqual(self.b.get(msg["media_url"]).status_code, 404)

    def test_notifications_api(self):
        self.a.post("/api/swipes/", {"target_uid": self.ub["uid"], "like": True}, content_type=JSON)
        data = self.b.get("/api/notifications/").json()
        self.assertEqual(data["unread"], 1)
        n = data["notifications"][0]
        self.assertEqual(n["type"], "like")
        self.assertEqual(self.b.post("/api/notifications/read/", {}, content_type=JSON).status_code, 400)
        self.assertEqual(self.b.post("/api/notifications/read/", {"ids": [n["id"]]}, content_type=JSON).status_code, 200)
        self.assertEqual(self.b.get("/api/notifications/").json()["unread"], 0)
        self.assertEqual(Client().get("/api/notifications/").status_code, 401)

    def test_signals_api(self):
        mid = self.pair()
        url = f"/api/matches/{mid}/signals/"
        self.assertEqual(self.a.post(url, {"kind": "offer", "payload": {"video": True}}, content_type=JSON).status_code, 201)
        got = self.b.get(url + "?since=0").json()["signals"]
        self.assertEqual([s["kind"] for s in got], ["offer"])
        self.assertEqual(self.a.post(url, {"kind": "bad"}, content_type=JSON).status_code, 400)
        self.assertEqual(Client().get(url).status_code, 401)

    @override_settings(TURN_URLS=["turn:turn.example.com:3478"], TURN_USERNAME="u", TURN_CREDENTIAL="p")
    def test_ice_servers(self):
        servers = self.a.get("/api/ice/").json()["iceServers"]
        self.assertEqual(servers[-1]["username"], "u")
        self.assertEqual(Client().get("/api/ice/").status_code, 401)

    def test_catalogs_and_pages(self):
        self.assertEqual(len(self.a.get("/api/gifts/").json()["gifts"]), 8)
        ach = self.a.get("/api/achievements/").json()["achievements"]
        self.assertTrue(all(not a["earned"] for a in ach))
        for url in ("/discover/", "/profile/", "/matches/"):
            self.assertEqual(self.a.get(url).status_code, 200, url)
        mid = self.pair()
        self.assertEqual(self.a.get(f"/chat/{mid}/").status_code, 200)
