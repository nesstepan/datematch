"""HTTP-тесты новых страниц и функций (нужен Django): USE_MEMORY_DB=1 python manage.py test"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings

from core import security, services, store
from core.tests.test_api_features import JSON, png, reg


@override_settings(USE_MEMORY_DB=True, ADMIN_EMAILS={"boss@example.com"})
class SocialApiTests(SimpleTestCase):
    def setUp(self):
        security.ITERATIONS = 1000
        security.login_limiter._hits.clear()
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.a, self.b, self.boss = Client(), Client(), Client()
        self.ua = self.a.post("/api/auth/register/", reg("a@example.com", "Аня", "female", "male")).json()["user"]
        self.ub = self.b.post("/api/auth/register/", reg("b@example.com", "Борис", "male", "female")).json()["user"]
        self.boss.post("/api/auth/register/", reg("boss@example.com", "Босс", "male", "female"))

    def swipe(self, client, target, like=True):
        return client.post("/api/swipes/", {"target_uid": target["uid"], "like": like}, content_type=JSON).json()

    def pair(self):
        self.swipe(self.a, self.ub)
        return self.swipe(self.b, self.ua)["match_id"]

    # --- страницы ---
    def test_landing_is_open_to_everyone(self):
        self.assertEqual(Client().get("/").status_code, 200)  # гость
        page = self.a.get("/")  # вошедший пользователь тоже видит главную, без перенаправления
        self.assertEqual(page.status_code, 200)
        self.assertIn("Открыть ленту", page.content.decode())
        self.assertEqual(self.a.get("/login/").status_code, 302)  # а вход и регистрация ему не нужны

    def test_posts_feed_of_pairs(self):
        self.b.post("/api/me/posts/", {"text": "пост Бориса"})
        self.assertEqual([p["text"] for p in self.a.get("/api/posts/").json()["posts"]], [])
        self.pair()
        got = self.a.get("/api/posts/").json()["posts"]
        self.assertEqual([(p["text"], p["author"]["name"]) for p in got], [("пост Бориса", "Борис")])
        self.assertEqual(Client().get("/api/posts/").status_code, 401)

    def test_new_pages_need_login_and_render(self):
        for url in ("/likes/", "/search/", "/posts/", "/settings/", f"/u/{self.ub['uid']}/"):
            self.assertEqual(Client().get(url).status_code, 302, url)
            self.assertEqual(self.a.get(url).status_code, 200, url)

    # --- лайки и поиск ---
    def test_likes_page_api(self):
        self.swipe(self.b, self.ua)
        got = self.a.get("/api/likes/").json()["profiles"]
        self.assertEqual([p["uid"] for p in got], [self.ub["uid"]])
        self.assertNotIn("email", got[0])
        self.swipe(self.a, self.ub, False)
        self.assertEqual(self.a.get("/api/likes/").json()["profiles"], [])
        self.assertEqual(Client().get("/api/likes/").status_code, 401)

    def test_search_api(self):
        self.assertEqual([p["name"] for p in self.a.get("/api/search/?q=бор").json()["profiles"]], ["Борис"])
        self.assertEqual(self.a.get("/api/search/?age_min=50&age_max=20").status_code, 422)
        self.assertEqual(self.a.get("/api/search/?goal=hack").status_code, 422)
        self.assertEqual(self.a.get("/api/search/?age_min=abc").status_code, 400)
        self.assertEqual(Client().get("/api/search/").status_code, 401)

    # --- страница пользователя и посты ---
    def test_user_page_and_posts(self):
        r = self.a.get(f"/api/users/{self.ub['uid']}/").json()
        self.assertEqual(r["profile"]["name"], "Борис")
        self.assertFalse(r["relation"]["matched"])
        self.assertNotIn("password", str(r))
        up = self.a.post("/api/me/posts/", {"text": "Мой первый пост",
                                            "photo": SimpleUploadedFile("p.png", png(), content_type="image/png")})
        self.assertEqual(up.status_code, 201)
        pid = up.json()["post"]["id"]
        posts = self.b.get(f"/api/users/{self.ua['uid']}/").json()["posts"]
        self.assertEqual([p["text"] for p in posts], ["Мой первый пост"])
        self.assertEqual(self.b.delete(f"/api/me/posts/{pid}/").status_code, 404)  # чужой пост не удалить
        self.assertEqual(self.a.delete(f"/api/me/posts/{pid}/").status_code, 200)
        self.assertEqual(self.a.post("/api/me/posts/", {"text": ""}).status_code, 422)
        self.assertEqual(self.a.get("/api/users/nope/").status_code, 404)

    # --- чёрный список и жалобы ---
    def test_blocklist_api(self):
        mid = self.pair()
        r = self.a.post("/api/blocks/", {"uid": self.ub["uid"]}, content_type=JSON).json()
        self.assertEqual([x["uid"] for x in r["blocked"]], [self.ub["uid"]])
        self.assertEqual(self.a.get(f"/api/matches/{mid}/messages/").status_code, 404)  # пара исчезла
        self.assertEqual(self.b.get(f"/api/users/{self.ua['uid']}/").status_code, 404)
        self.assertEqual(self.a.get("/api/feed/").json()["profiles"], [])
        self.assertEqual(self.a.post("/api/blocks/", {"uid": self.ua["uid"]}, content_type=JSON).status_code, 400)
        self.assertEqual(self.a.post("/api/blocks/", {}, content_type=JSON).status_code, 400)
        self.assertEqual(self.a.delete(f"/api/blocks/{self.ub['uid']}/").json()["blocked"], [])

    def test_report_flow_and_admin(self):
        bad = self.a.post("/api/reports/", {"uid": self.ub["uid"], "reason": "???"}, content_type=JSON)
        self.assertEqual(bad.status_code, 422)
        ok = self.a.post("/api/reports/", {"uid": self.ub["uid"], "reason": "spam", "details": "реклама", "block": True},
                         content_type=JSON)
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(len(self.a.get("/api/blocks/").json()["blocked"]), 1)
        self.assertEqual(self.a.get("/api/admin/reports/").status_code, 403)
        rep = self.boss.get("/api/admin/reports/").json()["reports"]
        self.assertEqual((len(rep), rep[0]["target"]["name"], rep[0]["reason"]), (1, "Борис", "spam"))
        self.assertEqual(self.boss.get("/api/admin/stats/").json()["reports_open"], 1)
        done = self.boss.patch(f"/api/admin/reports/{rep[0]['id']}/", {"action": "block"}, content_type=JSON)
        self.assertEqual(done.status_code, 200)
        self.assertEqual(self.b.get("/api/me/").status_code, 403)  # заблокирован администратором
        self.assertEqual(self.boss.get("/api/admin/reports/").json()["reports"], [])
        self.assertEqual(self.boss.patch("/api/admin/reports/zzz/", {"action": "dismiss"}, content_type=JSON).status_code, 404)

    # --- статусы сообщений, «печатает», «в сети» ---
    def test_chat_receipts_typing_and_presence(self):
        mid = self.pair()
        url = f"/api/matches/{mid}/messages/"
        self.a.post(url, {"text": "привет"}, content_type=JSON)
        self.assertEqual(self.a.post(f"/api/matches/{mid}/typing/").status_code, 200)
        poll_b = self.b.get(url).json()
        self.assertTrue(poll_b["typing"] is False)  # сообщение уже отправлено — набор сброшен
        self.assertEqual([m["text"] for m in poll_b["messages"]], ["привет"])
        poll_a = self.a.get(url).json()
        self.assertGreaterEqual(poll_a["receipts"]["read_at"], poll_a["messages"][0]["created_at"])
        self.assertIn("online", poll_a["other"])
        self.b.post(f"/api/matches/{mid}/typing/")
        self.assertTrue(self.a.get(url).json()["typing"])
        self.assertEqual(Client().post(f"/api/matches/{mid}/typing/").status_code, 401)

    def test_goal_and_hide_online_settings(self):
        r = self.a.post("/api/me/", {"name": "Аня", "age": "25", "gender": "female", "looking_for": "male",
                                     "bio": "", "goal": "friends", "interests": ["Кино"]})
        self.assertEqual(r.json()["user"]["goal"], "friends")
        bad = self.a.post("/api/me/", {"name": "Аня", "age": "25", "gender": "female", "looking_for": "male", "goal": "x"})
        self.assertIn("goal", bad.json()["error"]["fields"])
        r = self.a.post("/api/me/settings/", {"hide_online": True}, content_type=JSON)
        self.assertTrue(r.json()["user"]["hide_online"])
        self.assertIsNone(self.b.get(f"/api/users/{self.ua['uid']}/").json()["profile"]["last_seen"])
