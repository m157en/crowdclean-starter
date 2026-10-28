from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app import models  # noqa: F401 - register ORM models


@pytest.fixture()
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(test_engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with TestingSessionLocal() as session:
        yield session


@pytest.fixture()
def client(test_engine, tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    from app import audio_storage, config

    monkeypatch.setattr(config.settings, "storage_dir", Path(tmp_path))
    monkeypatch.setattr(audio_storage.settings, "storage_dir", Path(tmp_path))

    TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_get_db():
        with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
