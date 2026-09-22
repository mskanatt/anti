import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-key-please-change-1234567890")
os.environ.setdefault("STAFF_INVITE_CODE", "test-invite-code")
os.environ.setdefault("DATABASE_URL", "sqlite://")  # in-memory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)