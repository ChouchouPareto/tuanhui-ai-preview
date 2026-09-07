import os
import shutil
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="tuanhui-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'tests.db'}"
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["GENERATED_DIR"] = str(TEST_ROOT / "generated")
os.environ["ANALYZER_MODE"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(TEST_ROOT / "uploads", ignore_errors=True)
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
