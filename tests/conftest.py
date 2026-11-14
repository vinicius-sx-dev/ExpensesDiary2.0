import os
import tempfile
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory()
# Never reuse the application DATABASE_URL, including a developer's real SQLite DB.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "sqlite:///" + str(Path(TEST_DIR.name) / "tests.db")
)
os.environ.setdefault("JWT_SECRET", "testing-only-secret-with-more-than-32-characters")
os.environ["ENVIRONMENT"] = "test"
from cryptography.fernet import Fernet
os.environ["STATEMENT_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
import pytest
from fastapi.testclient import TestClient

from app import auth
from app.db import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def database():
    # Never drop a supplied MySQL database; integration runs must create their own disposable DB.
    assert engine.url.database and (
        engine.dialect.name == "sqlite" or engine.url.database.endswith("_test")
    )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client(monkeypatch):
    sent = []
    monkeypatch.setattr(auth, "send_code", lambda email, code: sent.append((email, code)))
    with TestClient(app) as c:
        c.sent = sent
        yield c
