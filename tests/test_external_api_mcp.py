"""Tests for the external API MCP server (5 tests — all mocked, no real network)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import mcp_servers.external_api.server as api_server


def _make_mock_client(json_data: dict, status_code: int = 200):
    """Returns a mock async context manager that simulates httpx.AsyncClient."""
    response = MagicMock()
    response.status_code = status_code
    response.raise_for_status = MagicMock()
    response.json.return_value = json_data

    mock_client = AsyncMock()
    mock_client.get.return_value = response

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


_COLOMBIA_PAYLOAD = {
    "country": "Colombia",
    "updated": 1_700_000_000,
    "todayCases": 50,
    "todayDeaths": 2,
    "active": 5_000,
    "critical": 100,
    "cases": 6_000_000,
    "deaths": 140_000,
}

_GLOBAL_PAYLOAD = {
    "updated": 1_700_000_000,
    "todayCases": 50_000,
    "todayDeaths": 800,
    "active": 2_000_000,
    "critical": 40_000,
    "cases": 700_000_000,
    "deaths": 7_000_000,
    "affectedCountries": 230,
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_get_alerts_success():
    with patch("mcp_servers.external_api.server.httpx.AsyncClient", return_value=_make_mock_client(_COLOMBIA_PAYLOAD)):
        result = json.loads(await api_server._get_epidemiological_alerts({"country": "colombia"}))

    assert result["success"] is True
    data = result["data"]
    assert data["country"] == "Colombia"
    assert data["alert_level"] in ("normal", "advertencia", "crítico")
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) >= 1
    assert data["source"] == "disease.sh"


async def test_get_global_summary_success():
    with patch("mcp_servers.external_api.server.httpx.AsyncClient", return_value=_make_mock_client(_GLOBAL_PAYLOAD)):
        result = json.loads(await api_server._get_global_health_summary({}))

    assert result["success"] is True
    assert result["data"]["affected_countries"] == 230
    assert result["data"]["source"] == "disease.sh"


# ---------------------------------------------------------------------------
# Error cases (simulates API unavailability — required by spec)
# ---------------------------------------------------------------------------

async def test_get_alerts_timeout_returns_error_without_crashing():
    """Agent must continue the flow when API times out — success=False, not an exception."""
    ctx = MagicMock()
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.TimeoutException("timed out")
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("mcp_servers.external_api.server.httpx.AsyncClient", return_value=ctx):
        result = json.loads(await api_server._get_epidemiological_alerts({"country": "colombia"}))

    assert result["success"] is False
    assert "timeout" in result["error"].lower()
    assert result["data"] is None


async def test_get_alerts_invalid_country_returns_error():
    response = MagicMock()
    response.status_code = 404
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=response
    )

    mock_client = AsyncMock()
    mock_client.get.return_value = response

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("mcp_servers.external_api.server.httpx.AsyncClient", return_value=ctx):
        result = json.loads(await api_server._get_epidemiological_alerts({"country": "xyzinvalid"}))

    assert result["success"] is False
    assert "xyzinvalid" in result["error"] or "404" in result["error"] or "encontrado" in result["error"].lower()


# ---------------------------------------------------------------------------
# Alert level logic (pure, no I/O)
# ---------------------------------------------------------------------------

async def test_alert_level_classification():
    """_alert_level must classify correctly without network calls."""
    assert api_server._alert_level(0, 0, 0) == "normal"
    assert api_server._alert_level(100, 0, 0) == "advertencia"
    assert api_server._alert_level(1000, 0, 0) == "crítico"
    assert api_server._alert_level(0, 50, 0) == "crítico"
    assert api_server._alert_level(99, 9, 1000) == "normal"
