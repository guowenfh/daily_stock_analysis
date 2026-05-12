# -*- coding: utf-8 -*-
"""Integration tests for signal creators API."""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.config import Config
from src.signal.models import ensure_signal_tables
from src.storage import DatabaseManager


@pytest.fixture
def client():
    DatabaseManager.reset_instance()
    Config.reset_instance()
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "signal_api_test.db"
        os.environ["DATABASE_PATH"] = str(db_path)

        db_manager = DatabaseManager(db_url=f"sqlite:///{db_path}")
        ensure_signal_tables(db_manager._engine)

        from api.app import create_app

        app = create_app()
        with TestClient(app) as c:
            yield c

    DatabaseManager.reset_instance()
    Config.reset_instance()


class TestCreatorsAPI:
    def test_create_and_list(self, client):
        resp = client.post(
            "/api/v1/signals/creators",
            json={
                "platform_uid": "12345",
                "name": "测试UP主",
                "category": "财经",
                "manual_weight": 1.5,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "测试UP主"
        assert data["manual_weight"] == 1.5

        resp = client.get("/api/v1/signals/creators")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_update_creator(self, client):
        client.post(
            "/api/v1/signals/creators",
            json={
                "platform_uid": "111",
                "name": "A",
            },
        )
        resp = client.put(
            "/api/v1/signals/creators/1",
            json={
                "manual_weight": 0.5,
                "is_active": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["manual_weight"] == 0.5
        assert resp.json()["is_active"] is False

    def test_duplicate_uid_rejected(self, client):
        client.post(
            "/api/v1/signals/creators",
            json={
                "platform_uid": "222",
                "name": "B",
            },
        )
        resp = client.post(
            "/api/v1/signals/creators",
            json={
                "platform_uid": "222",
                "name": "C",
            },
        )
        assert resp.status_code == 400
