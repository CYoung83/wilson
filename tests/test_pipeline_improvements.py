"""
Tests for Wilson pipeline improvements:
- CourtListener blocked flag compliance
- Name-based lookup confidence threshold
- CSV update check notification
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Task 1: blocked flag compliance
# ---------------------------------------------------------------------------

def test_fetch_cluster_blocked_returns_true():
    """fetch_cluster_blocked returns True when cluster has blocked=True."""
    from api import fetch_cluster_blocked
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"blocked": True, "id": 111170}
    with patch("api.http_requests.get", return_value=mock_resp):
        result = fetch_cluster_blocked(111170)
    assert result is True


def test_fetch_cluster_blocked_returns_false():
    """fetch_cluster_blocked returns False when cluster has blocked=False."""
    from api import fetch_cluster_blocked
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"blocked": False, "id": 111170}
    with patch("api.http_requests.get", return_value=mock_resp):
        result = fetch_cluster_blocked(111170)
    assert result is False


def test_fetch_cluster_blocked_api_error_returns_false():
    """fetch_cluster_blocked returns False on API error -- do not block on uncertainty."""
    from api import fetch_cluster_blocked
    with patch("api.http_requests.get", side_effect=Exception("timeout")):
        result = fetch_cluster_blocked(111170)
    assert result is False


def test_fetch_cluster_blocked_missing_field_returns_false():
    """fetch_cluster_blocked returns False when blocked field is absent."""
    from api import fetch_cluster_blocked
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 111170}
    with patch("api.http_requests.get", return_value=mock_resp):
        result = fetch_cluster_blocked(111170)
    assert result is False