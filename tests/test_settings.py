"""
Tests for Wilson settings panel API endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock


def test_get_ollama_models_available():
    """GET /settings/ollama-models returns model list when Ollama is available."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen3.5:35b"},
            {"name": "llama3:latest"}
        ]
    }
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.get("/settings/ollama-models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "current" in data
    assert "ollama_available" in data
    assert data["ollama_available"] is True
    assert "qwen3.5:35b" in data["models"]


def test_get_ollama_models_unavailable():
    """GET /settings/ollama-models returns empty list when Ollama is unavailable."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    with patch("api.http_requests.get", side_effect=Exception("connection refused")):
        response = client.get("/settings/ollama-models")
    assert response.status_code == 200
    data = response.json()
    assert data["ollama_available"] is False
    assert data["models"] == []


def test_post_ollama_model_valid():
    """POST /settings/ollama-model updates model and returns success."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    with patch("api.write_env_value", return_value=True):
        response = client.post(
            "/settings/ollama-model",
            json={"model": "llama3:latest"}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["model"] == "llama3:latest"


def test_post_ollama_host_test_only():
    """POST /settings/ollama-host with save=false tests without persisting."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}]}
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.post(
            "/settings/ollama-host",
            json={"host": "http://localhost:11434", "save": False}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True


def test_post_courtlistener_token_valid():
    """POST /settings/courtlistener-token validates token against CL API."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.post(
            "/settings/courtlistener-token",
            json={"token": "abc123", "save": False}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True


def test_post_courtlistener_token_invalid():
    """POST /settings/courtlistener-token returns valid=False for bad token."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.post(
            "/settings/courtlistener-token",
            json={"token": "badtoken", "save": False}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False


def test_write_env_value_updates_existing_key():
    """write_env_value updates an existing key in .env content."""
    from api import write_env_value
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env',
                                     delete=False) as f:
        f.write("OLLAMA_MODEL=llama3\nCOURTLISTENER_TOKEN=abc\n")
        tmp_path = f.name
    try:
        with patch("api.ENV_PATH", tmp_path):
            result = write_env_value("OLLAMA_MODEL", "qwen3.5:35b")
        assert result is True
        content = open(tmp_path).read()
        assert "OLLAMA_MODEL=qwen3.5:35b" in content
        assert "OLLAMA_MODEL=llama3" not in content
    finally:
        os.unlink(tmp_path)