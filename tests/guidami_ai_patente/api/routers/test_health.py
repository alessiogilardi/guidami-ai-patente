"""Tests for the /health endpoint."""

from fastapi.testclient import TestClient
from pydantic import SecretStr

from commons.configs import PostgresConnectionConfig
from guidami_ai_patente.api.app import create_app
from guidami_ai_patente.configs import AppConfig


def _build_client() -> TestClient:
    config = AppConfig(
        postgres=PostgresConnectionConfig(
            host="localhost",
            user="guidami",
            password=SecretStr("guidami"),
            dbname="guidami_ai_patente_test",
        )
    )
    return TestClient(create_app(config))


def test_health_reports_ok_status() -> None:
    response = _build_client().get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
