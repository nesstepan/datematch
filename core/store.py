"""Слой хранения. Две реализации с одинаковым интерфейсом:

* FirestoreStore — боевая, Firebase Firestore через firebase-admin;
* MemoryStore    — в памяти процесса, для разработки без Firebase и для тестов.

Запросы специально используют только равенство / array_contains / сортировку по одному полю,
поэтому составные индексы в Firestore создавать не нужно.
"""
import json
import threading
import uuid
from collections import defaultdict

from .exceptions import StoreError


class Store:
    def new_id(self):
        return uuid.uuid4().hex[:20]

    def get(self, path, doc_id):  # -> dict | None (с ключом "id")
        raise NotImplementedError

    def set(self, path, doc_id, data):
        raise NotImplementedError

    def update(self, path, doc_id, data):  # KeyError, если документа нет
        raise NotImplementedError

    def delete(self, path, doc_id):
        raise NotImplementedError

    def query(self, path, filters=(), order_by=None, descending=False, limit=None):
        raise NotImplementedError


def _match(doc, field, op, value):
    current = doc.get(field)
    if op == "==":
        return current == value
    if op == "array_contains":
        return isinstance(current, (list, tuple)) and value in current
    if current is None:
        return False
    return {">": current > value, ">=": current >= value, "<": current < value}[op]


class MemoryStore(Store):
    def __init__(self):
        self._data = defaultdict(dict)
        self._lock = threading.RLock()

    def get(self, path, doc_id):
        with self._lock:
            doc = self._data[path].get(doc_id)
            return {**json.loads(json.dumps(doc)), "id": doc_id} if doc is not None else None

    def set(self, path, doc_id, data):
        with self._lock:
            self._data[path][doc_id] = json.loads(json.dumps({k: v for k, v in data.items() if k != "id"}))

    def update(self, path, doc_id, data):
        with self._lock:
            if doc_id not in self._data[path]:
                raise KeyError(doc_id)
            self._data[path][doc_id].update(json.loads(json.dumps(data)))

    def delete(self, path, doc_id):
        with self._lock:
            self._data[path].pop(doc_id, None)

    def query(self, path, filters=(), order_by=None, descending=False, limit=None):
        with self._lock:
            docs = [{**json.loads(json.dumps(d)), "id": i} for i, d in self._data[path].items()
                    if all(_match(d, f, op, v) for f, op, v in filters)]
        if order_by:
            docs.sort(key=lambda d: (d.get(order_by) is None, d.get(order_by)), reverse=descending)
        return docs[:limit] if limit else docs


class FirestoreStore(Store):
    def __init__(self, client):
        self.db = client

    def _run(self, fn):
        try:
            return fn()
        except KeyError:
            raise
        except Exception as exc:  # сетевые ошибки, права, квоты
            from google.api_core.exceptions import NotFound
            if isinstance(exc, NotFound):
                raise KeyError("not found") from exc
            raise StoreError(f"Ошибка Firestore: {exc}") from exc

    def get(self, path, doc_id):
        def run():
            snap = self.db.collection(path).document(doc_id).get()
            if not snap.exists:
                return None
            return {**snap.to_dict(), "id": snap.id}
        return self._run(run)

    def set(self, path, doc_id, data):
        clean = {k: v for k, v in data.items() if k != "id"}
        self._run(lambda: self.db.collection(path).document(doc_id).set(clean))

    def update(self, path, doc_id, data):
        self._run(lambda: self.db.collection(path).document(doc_id).update(data))

    def delete(self, path, doc_id):
        self._run(lambda: self.db.collection(path).document(doc_id).delete())

    def query(self, path, filters=(), order_by=None, descending=False, limit=None):
        def run():
            from google.cloud.firestore_v1 import Query
            from google.cloud.firestore_v1.base_query import FieldFilter
            q = self.db.collection(path)
            for field, op, value in filters:
                q = q.where(filter=FieldFilter(field, op, value))
            if order_by:
                q = q.order_by(order_by, direction=Query.DESCENDING if descending else Query.ASCENDING)
            if limit:
                q = q.limit(limit)
            return [{**s.to_dict(), "id": s.id} for s in q.stream()]
        return self._run(run)


_store = None
_lock = threading.Lock()


def set_store(store):
    """Подменить хранилище (используется в тестах)."""
    global _store
    _store = store


def _init_firestore():
    import firebase_admin
    from django.conf import settings
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        if settings.FIREBASE_CREDENTIALS_JSON:
            cred = credentials.Certificate(json.loads(settings.FIREBASE_CREDENTIALS_JSON))
        elif settings.FIREBASE_CREDENTIALS_FILE:
            cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_FILE)
        else:
            raise StoreError(
                "Firebase не настроен: задайте FIREBASE_CREDENTIALS_JSON или FIREBASE_CREDENTIALS_FILE "
                "(либо USE_MEMORY_DB=1 для локального запуска без Firebase)")
        firebase_admin.initialize_app(cred)
    return FirestoreStore(firestore.client())


def get_store():
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                from django.conf import settings
                _store = MemoryStore() if settings.USE_MEMORY_DB else _init_firestore()
    return _store
