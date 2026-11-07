"""HTTP-тесты лайков и комментариев к постам (нужен Django): USE_MEMORY_DB=1 python manage.py test"""
from django.test import Client, SimpleTestCase, override_settings

from core import security, services, store
from core.tests.test_api import reg_data

JSON = "application/json"


@override_settings(USE_MEMORY_DB=True, ADMIN_EMAILS={"boss@example.com"})
class PostSocialApiTests(SimpleTestCase):
    def register(self, client, email, **kw):
        return client.post("/api/auth/register/", reg_data(email, **kw))

    def setUp(self):
        security.ITERATIONS = 1000
        security.login_limiter._hits.clear()
        store.set_store(store.MemoryStore())
        services.reset_cache()
        self.a, self.b = Client(), Client()
        self.ua = self.register(self.a, "a@example.com", name="Аня").json()["user"]
        self.ub = self.register(self.b, "b@example.com", name="Борис", gender="male", looking="female").json()["user"]
        r = self.a.post("/api/me/posts/", {"text": "Мой пост"})
        self.post_id = r.json()["post"]["id"]
        self.base = f"/api/users/{self.ua['uid']}/posts/{self.post_id}"

    def test_like_and_unlike(self):
        r = self.b.post(self.base + "/like/")
        self.assertEqual(r.json(), {"liked": True, "likes": 1})
        self.assertEqual(self.b.delete(self.base + "/like/").json(), {"liked": False, "likes": 0})
        self.assertEqual(self.b.post(self.base.replace(self.post_id, "nope") + "/like/").status_code, 404)

    def test_like_requires_login(self):
        self.assertEqual(Client().post(self.base + "/like/").status_code, 401)
        self.assertEqual(Client().get(self.base + "/comments/").status_code, 401)

    def test_comments_flow(self):
        r = self.b.post(self.base + "/comments/", {"text": "Привет!"}, content_type=JSON)
        self.assertEqual(r.status_code, 201)
        cid = r.json()["comment"]["id"]
        listed = self.a.get(self.base + "/comments/").json()["comments"]
        self.assertEqual([c["text"] for c in listed], ["Привет!"])
        self.assertTrue(listed[0]["can_delete"])  # хозяин поста может удалить
        self.assertEqual(self.b.post(self.base + "/comments/", {"text": "  "}, content_type=JSON).status_code, 422)
        self.assertEqual(self.b.post(self.base + "/comments/", {"text": "x" * 501}, content_type=JSON).status_code, 422)
        stranger = Client()
        self.register(stranger, "c@example.com", name="Вера")
        self.assertEqual(stranger.delete(f"{self.base}/comments/{cid}/").status_code, 403)
        self.assertEqual(self.b.delete(f"{self.base}/comments/{cid}/").json(), {"comments": 0})

    def test_counters_in_post_lists(self):
        self.b.post(self.base + "/like/")
        self.b.post(self.base + "/comments/", {"text": "ок"}, content_type=JSON)
        page = self.b.get(f"/api/users/{self.ua['uid']}/").json()["posts"][0]
        self.assertEqual((page["likes"], page["liked"], page["comments"]), (1, True, 1))
        notes = [n["type"] for n in self.a.get("/api/notifications/").json()["notifications"]]
        self.assertIn("post_like", notes); self.assertIn("comment", notes)
