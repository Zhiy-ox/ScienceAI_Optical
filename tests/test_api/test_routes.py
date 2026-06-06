"""Tests for the FastAPI routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import science_ai.api.routes as routes_module
from science_ai.main import app
from science_ai.storage.models import ResearchSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(
    session_id: str = "test-session-id",
    status: str = "running",
    question: str = "Test question",
    phase: int = 3,
    result: dict | None = None,
    cost_records: list | None = None,
) -> MagicMock:
    """Build a mock that behaves like a ResearchSession ORM row."""
    s = MagicMock(spec=ResearchSession)
    s.session_id = session_id
    s.status = status
    s.question = question
    s.phase = phase
    s.result = result
    s.cost_records = cost_records
    return s


def _mock_repo(
    get_session_return=None,
    list_sessions_return=None,
):
    """Return an AsyncMock shaped like SessionRepository."""
    repo = AsyncMock()
    repo.get_session.return_value = get_session_return
    repo.list_sessions.return_value = list_sessions_return or []
    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_check():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.4.0"


def test_health_version_is_0_4_0():
    client = TestClient(app)
    resp = client.get("/api/v1/health")
    data = resp.json()
    assert data["version"] == "0.4.0"


def test_start_research_returns_session_id():
    repo = _mock_repo()
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/research/start",
            json={"question": "What are the latest advances in optical phased arrays?"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert data["status"] == "started"
    repo.create_session.assert_called_once()


def test_start_research_with_phase_1():
    repo = _mock_repo()
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/research/start",
            json={"question": "Test", "phase": 1, "max_papers": 10},
        )
    assert resp.status_code == 200


def test_start_research_with_phase_3():
    repo = _mock_repo()
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/research/start",
            json={
                "question": "Liquid crystal OPA",
                "phase": 3,
                "user_background": "Photonics researcher",
            },
        )
    assert resp.status_code == 200


def test_start_research_default_phase_is_3():
    repo = _mock_repo()
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/research/start",
            json={"question": "Test question"},
        )
    assert resp.status_code == 200
    # Verify phase=3 was passed to create_session
    _, kwargs = repo.create_session.call_args
    assert kwargs.get("phase", repo.create_session.call_args[0][2]) == 3


def test_status_returns_running_for_known_session():
    session = _make_session(status="running")
    repo = _mock_repo(get_session_return=session)
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get(f"/api/v1/research/{session.session_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["session_id"] == session.session_id


def test_status_404_for_unknown_session():
    repo = _mock_repo(get_session_return=None)
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get("/api/v1/research/nonexistent/status")
    assert resp.status_code == 404


def test_results_202_while_running():
    session = _make_session(status="running")
    repo = _mock_repo(get_session_return=session)
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get(f"/api/v1/research/{session.session_id}/results")
    assert resp.status_code == 202


def test_results_404_for_unknown_session():
    repo = _mock_repo(get_session_return=None)
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get("/api/v1/research/nonexistent/results")
    assert resp.status_code == 404


def test_results_returns_data_for_completed_session():
    result_payload = {
        "status": "completed",
        "plan": {"queries": ["OPA beam steering"]},
        "papers_found": 5,
        "triage_results": [],
        "knowledge_objects": [],
        "critiques": [],
        "gaps": [],
        "verified_gaps": [],
        "ideas": [],
        "experiment_plans": [],
        "report": None,
        "cost_summary": None,
    }
    session = _make_session(status="completed", result=result_payload)
    repo = _mock_repo(get_session_return=session)
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get(f"/api/v1/research/{session.session_id}/results")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["papers_found"] == 5


def test_cost_404_for_unknown_session():
    repo = _mock_repo(get_session_return=None)
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get("/api/v1/research/nonexistent/cost")
    assert resp.status_code == 404


def test_cost_404_when_no_tracker_and_no_stored_records():
    session = _make_session(status="completed", cost_records=None)
    repo = _mock_repo(get_session_return=session)
    with patch.object(routes_module, "_session_repo", repo):
        # Ensure in-memory tracker is absent
        routes_module._cost_trackers.pop(session.session_id, None)
        client = TestClient(app)
        resp = client.get(f"/api/v1/research/{session.session_id}/cost")
    assert resp.status_code == 404


def test_list_sessions_returns_db_sessions():
    sessions = [
        _make_session("sid-1", question="Q1"),
        _make_session("sid-2", question="Q2"),
    ]
    repo = _mock_repo(list_sessions_return=sessions)
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get("/api/v1/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    ids = {item["session_id"] for item in data}
    assert ids == {"sid-1", "sid-2"}


def test_list_sessions_empty():
    repo = _mock_repo(list_sessions_return=[])
    with patch.object(routes_module, "_session_repo", repo):
        client = TestClient(app)
        resp = client.get("/api/v1/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_start_research_invalid_phase():
    """Phase must be between 1 and 3."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/research/start",
        json={"question": "Test", "phase": 4},
    )
    assert resp.status_code == 422


def test_start_research_exceeds_max_papers():
    """max_papers has a maximum cap enforced by the schema."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/research/start",
        json={"question": "Test", "max_papers": 9999},
    )
    assert resp.status_code == 422
