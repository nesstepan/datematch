"""HTTP-тесты ответов, реакций и видео в чате (нужен Django): USE_MEMORY_DB=1 python manage.py test"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings

from core import security, services, store
from core.tests.test_api import reg_data

JSON = "application/json"
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00"


@override_settings(USE_MEMORY_DB=True, ADMIN_EMAILS={"boss@example.com"})
class ChatExtrasApiTests(SimpleTestCase):
    def setUp(self):
        security.ITERATIONS = 1000
        security.login_limiter._hits.clear()
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.a, self.b = Client(), Client()
        ua = self.a.post("/api/auth/register/", reg_data("a@example.com", name="Аня")).json()["user"]
        ub = self.b.post("/api/auth/register/", reg_data("b@example.com", name="Борис", gender="male", looking="female")).json()["user"]
        self.a.post("/api/swipes/", {"target_uid": ub["uid"], "like": True}, content_type=JSON)
        self.mid = self.b.post("/api/swipes/", {"target_uid": ua["uid"], "like": True}, content_type=JSON).json()["match_id"]
        self.base = f"/api/matches/{self.mid}/messages/"

    def test_reply_json_multipart_and_gift(self):
        first = self.a.post(self.base, {"text": "Привет"}, content_type=JSON).json()["message"]
        r = self.b.post(self.base, {"text": "Ответ", "reply_to": first["id"]}, content_type=JSON)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["message"]["reply_to"], {"id": first["id"], "mine": False, "type": "text", "text": "Привет"})
        g = self.b.post(self.base, {"gift": "rose", "reply_to": first["id"]}, content_type=JSON).json()["message"]
        self.assertEqual(g["reply_to"]["id"], first["id"])
        v = self.b.post(self.base, {"file": SimpleUploadedFile("v.mp4", MP4 + b"\0" * 300, content_type="video/mp4"), "reply_to": first["id"]})
        self.assertEqual(v.status_code, 201)
        self.assertEqual(v.json()["message"]["reply_to"]["text"], "Привет")
        listed = self.a.get(self.base).json()["messages"]
        self.assertTrue(listed[1]["reply_to"]["mine"])  # для Ани цитата — её собственное сообщение

    def test_bad_reply_target(self):
        r = self.b.post(self.base, {"text": "x", "reply_to": "nope"}, content_type=JSON)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.a.get(self.base).json()["messages"], [])

    def test_reactions_flow(self):
        m = self.a.post(self.base, {"text": "Привет"}, content_type=JSON).json()["message"]
        url = f"{self.base}{m['id']}/reaction/"
        r = self.b.post(url, {"kind": "fire"}, content_type=JSON)
        self.assertEqual(r.json()["reactions"], [{"kind": "fire", "count": 1, "mine": True}])
        poll = self.a.get(self.base).json()
        self.assertEqual(poll["messages"][0]["reactions"][0]["kind"], "fire")
        self.assertEqual(self.b.post(url, {"kind": "poop"}, content_type=JSON).status_code, 422)
        self.assertEqual(self.b.delete(url).json()["reactions"], [])
        self.assertEqual(Client().post(url, {"kind": "like"}, content_type=JSON).status_code, 401)
        stranger = Client()
        stranger.post("/api/auth/register/", reg_data("c@example.com", name="Вера"))
        self.assertEqual(stranger.post(url, {"kind": "like"}, content_type=JSON).status_code, 404)

    def test_video_limit_is_15_mb(self):
        ok = self.a.post(self.base, {"file": SimpleUploadedFile("v.mp4", MP4 + b"\0" * (9 * 1024 * 1024), content_type="video/mp4")})
        self.assertEqual(ok.status_code, 201)                           # раньше такое видео отклонялось (лимит был 6 МБ)
        big = self.a.post(self.base, {"file": SimpleUploadedFile("v.mp4", MP4 + b"\0" * (16 * 1024 * 1024), content_type="video/mp4")})
        self.assertEqual(big.status_code, 422)
        # видео в анкете осталось с прежним лимитом
        prof = self.a.post("/api/me/video/", {"video": SimpleUploadedFile("v.mp4", MP4 + b"\0" * (6 * 1024 * 1024), content_type="video/mp4")})
        self.assertEqual(prof.status_code, 422)
