import os
import shutil
from pathlib import Path

Path("./data").mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///./data/test_tuanhui.db"
os.environ["UPLOAD_DIR"] = "./data/test_uploads"
os.environ["ANALYZER_MODE"] = "mock"

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    shutil.rmtree(Path("./data/test_uploads"), ignore_errors=True)
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
