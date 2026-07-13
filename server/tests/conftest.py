import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

STATEMENT = (
    "05.01.2026 10:00:00\t05.01.2026\t*1\tOK\t-100,00\tRUB\t-100,00\tRUB\t\tSuper\t5411\tLenta\t0\t0\t-100,00\n"  # noqa: E501
    "06.01.2026 11:00:00\t06.01.2026\t*1\tOK\t-200,00\tRUB\t-200,00\tRUB\t\tSuper\t5411\tOkey\t0\t0\t-200,00\n"  # noqa: E501
)


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    monkeypatch.setenv("MONORI_DB", db_path)
    import app.db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", db_path)
    dbmod.connect(db_path).close()

    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    return TestClient(fastapi_app)


class Api:
    """Thin helper over the HTTP client for arranging test state. Bodies that
    should always succeed assert 200; error paths are exercised with the raw
    `client` in the tests themselves."""

    statement = STATEMENT

    def __init__(self, client):
        self.client = client

    def group(self, name, kind="expense"):
        r = self.client.post("/api/groups", json={"name": name, "kind": kind})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def category(self, name, group_id, keywords=""):
        r = self.client.post(
            "/api/categories", json={"name": name, "groupId": group_id, "keywords": keywords}
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def tx(self, date, amount, **kw):
        r = self.client.post("/api/transactions", json={"date": date, "amount": amount, **kw})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def snapshot(self):
        return self.client.get("/api/snapshot").json()

    def cat(self, cat_id):
        return next(c for c in self.snapshot()["categories"] if c["id"] == cat_id)

    def tx_by(self, tx_id):
        return next(t for t in self.snapshot()["transactions"] if t["id"] == tx_id)

    def preview(self, text):
        return self.client.post("/api/import/preview", json={"text": text}).json()["rows"]


@pytest.fixture()
def api(client):
    return Api(client)
