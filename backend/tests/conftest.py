"""Isolated API tests. No test starts the application's production lifespan."""

from datetime import datetime
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Base, get_db, make_engine
from app.main import app
from app.services import common, planner, reminder


class Clock:
    def __init__(self):
        self.value = datetime.fromisoformat("2026-09-21T04:00:00+00:00")

    def set(self, value):
        self.value = datetime.fromisoformat(value)

    def now(self):
        return self.value

    def iso(self):
        return self.value.isoformat()


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(common, "utc_now", clock.now)
    monkeypatch.setattr(reminder, "utc_now", clock.now)
    monkeypatch.setattr(planner, "now_iso", clock.iso)
    return clock


@pytest.fixture
def session_factory(tmp_path, clock):
    engine = make_engine(f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        common.settings(session)
        session.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def client(session_factory):
    def isolated_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = isolated_db
    # Using the client without its context manager intentionally skips lifespan.
    client = TestClient(app)
    yield client
    client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def create(client):
    def post(collection, **data):
        response = client.post(f"/api/{collection}", json=data)
        assert response.status_code == 201, response.text
        return response.json()

    return post


@pytest.fixture
def action(client):
    def act(task, operation, **values):
        response = client.post(
            f"/api/tasks/{task['id']}/actions",
            json={"action": operation, "version": task["version"], **values},
        )
        assert response.status_code == 200, response.text
        return response.json()

    return act
