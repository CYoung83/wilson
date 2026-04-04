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


# ---------------------------------------------------------------------------
# Task 2: name-based lookup confidence threshold
# ---------------------------------------------------------------------------

def test_name_similarity_above_threshold_proceeds():
    """
    When name similarity >= 60%, fallback proceeds normally.
    Similarity between 'Daubert v. Merrell Dow' and
    'Daubert v. Merrell Dow Pharmaceuticals, Inc.' should be >= 60.
    """
    from rapidfuzz import fuzz
    user_input = "Daubert v. Merrell Dow"
    actual = "Daubert v. Merrell Dow Pharmaceuticals, Inc."
    score = fuzz.partial_ratio(user_input.lower(), actual.lower())
    assert score >= 60


def test_name_similarity_below_threshold_blocked():
    """
    When name similarity < 60%, the fallback should not proceed.
    Completely unrelated names should score below threshold.
    """
    from rapidfuzz import fuzz
    user_input = "Smith v. Jones"
    actual = "Daubert v. Merrell Dow Pharmaceuticals, Inc."
    score = fuzz.partial_ratio(user_input.lower(), actual.lower())
    assert score < 60


# ---------------------------------------------------------------------------
# Task 3: CSV update check
# ---------------------------------------------------------------------------

def test_parse_csv_date_valid():
    """parse_csv_date extracts date from standard filename."""
    from api import parse_csv_date
    from datetime import date
    result = parse_csv_date("citations-2026-03-31.csv")
    assert result == date(2026, 3, 31)


def test_parse_csv_date_full_path():
    """parse_csv_date handles full file paths."""
    from api import parse_csv_date
    from datetime import date
    result = parse_csv_date("/var/data/citations-2025-12-01.csv")
    assert result == date(2025, 12, 1)


def test_parse_csv_date_no_date_returns_none():
    """parse_csv_date returns None when filename has no parseable date."""
    from api import parse_csv_date
    result = parse_csv_date("citations.csv")
    assert result is None


def test_parse_csv_date_none_input_returns_none():
    """parse_csv_date returns None for None input."""
    from api import parse_csv_date
    result = parse_csv_date(None)
    assert result is None