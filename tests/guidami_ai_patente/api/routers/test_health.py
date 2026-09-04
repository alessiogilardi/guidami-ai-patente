"""Tests for the /health endpoint."""

from fastapi.testclient import TestClient


def test_health_reports_ok_status(api_client: TestClient) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
