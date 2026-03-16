"""Tests for the FastAPI routes."""

from fastapi.testclient import TestClient

from science_ai.main import app

client = TestClient(app)


def test_health_check():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.2.0"


def test_start_research_returns_session_id():
    resp = client.post(
        "/api/v1/research/start",
        json={"question": "What are the latest advances in optical phased arrays?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["status"] == "started"


def test_start_research_with_phase():
    resp = client.post(
        "/api/v1/research/start",
        json={
            "question": "Liquid crystal OPA research",
            "phase": 1,
            "max_papers": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data


def test_start_research_default_phase_is_2():
    resp = client.post(
        "/api/v1/research/start",
        json={"question": "Test question"},
    )
    assert resp.status_code == 200


def test_status_404_for_unknown_session():
    resp = client.get("/api/v1/research/nonexistent/status")
    assert resp.status_code == 404


def test_results_404_for_unknown_session():
    resp = client.get("/api/v1/research/nonexistent/results")
    assert resp.status_code == 404
