import os
import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


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
