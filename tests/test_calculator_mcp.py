"""Tests for the calculator MCP server (8 tests — pure computation, no I/O)."""

import json

import pytest

import mcp_servers.calculator.server as calc_server


# ---------------------------------------------------------------------------
# calculate_occupancy
# ---------------------------------------------------------------------------

async def test_occupancy_optimal():
    result = json.loads(
        await calc_server._calculate_occupancy({"visits_today": 10, "max_capacity": 15})
    )

    assert result["success"] is True
    data = result["data"]
    assert data["occupancy_pct"] == pytest.approx(66.7, abs=0.1)
    assert data["status"] == "óptimo"
    assert data["available_slots_remaining"] == 5


async def test_occupancy_overloaded():
    result = json.loads(
        await calc_server._calculate_occupancy({"visits_today": 14, "max_capacity": 15})
    )

    assert result["success"] is True
    assert result["data"]["occupancy_pct"] == pytest.approx(93.3, abs=0.1)
    assert result["data"]["status"] == "sobrecargado"


async def test_occupancy_underutilized():
    result = json.loads(
        await calc_server._calculate_occupancy({"visits_today": 3, "max_capacity": 15})
    )

    assert result["success"] is True
    assert result["data"]["status"] == "subutilizado"


async def test_occupancy_invalid_capacity_returns_error():
    result = json.loads(
        await calc_server._calculate_occupancy({"visits_today": 5, "max_capacity": 0})
    )

    assert result["success"] is False
    assert result["error"] is not None


async def test_occupancy_missing_params_returns_error():
    result = json.loads(await calc_server._calculate_occupancy({}))

    assert result["success"] is False


# ---------------------------------------------------------------------------
# project_stock
# ---------------------------------------------------------------------------

async def test_project_stock_sorts_urgent_first():
    items = [
        {"name": "Paracetamol", "current_stock": 100, "consumed_today": 2, "minimum_threshold": 20, "status": "normal"},
        {"name": "Amoxicilina", "current_stock": 3,   "consumed_today": 2, "minimum_threshold": 15, "status": "crítico"},
        {"name": "Lisinopril",  "current_stock": 8,   "consumed_today": 1, "minimum_threshold": 10, "status": "bajo"},
    ]
    result = json.loads(await calc_server._project_stock({"stock_items": items}))

    assert result["success"] is True
    projections = result["data"]
    assert projections[0]["name"] == "Amoxicilina"  # urgent first
    assert projections[0]["needs_reorder"] is True
    assert projections[0]["projected_stock_tomorrow"] == 1.0   # 3 - 2

    paracetamol = next(p for p in projections if p["name"] == "Paracetamol")
    assert paracetamol["needs_reorder"] is False
    assert paracetamol["days_until_stockout"] == 50  # 100 // 2


async def test_project_stock_zero_consumption_no_days_remaining():
    items = [
        {"name": "Salbutamol", "current_stock": 5, "consumed_today": 0, "minimum_threshold": 8, "status": "bajo"},
    ]
    result = json.loads(await calc_server._project_stock({"stock_items": items}))

    assert result["success"] is True
    assert result["data"][0]["days_until_stockout"] is None
    assert result["data"][0]["projected_stock_tomorrow"] == 5.0


async def test_project_stock_empty_list():
    result = json.loads(await calc_server._project_stock({"stock_items": []}))

    assert result["success"] is True
    assert result["data"] == []


# ---------------------------------------------------------------------------
# generate_recommendations
# ---------------------------------------------------------------------------

async def test_recommendations_with_critical_stock_sets_overall_critical():
    occupancy = {"status": "óptimo", "occupancy_pct": 70, "avg_minutes_per_patient": 30}
    stock = [
        {"name": "Amoxicilina", "reorder_priority": "urgente", "days_until_stockout": 1,
         "projected_stock_tomorrow": 1, "status": "crítico"},
    ]
    result = json.loads(
        await calc_server._generate_recommendations({"occupancy_data": occupancy, "stock_projections": stock})
    )

    assert result["success"] is True
    data = result["data"]
    assert data["overall_status"] == "crítico"
    assert "Amoxicilina" in data["urgent_reorders"]
    assert len(data["alerts"]) >= 1


async def test_recommendations_all_normal_status():
    occupancy = {"status": "óptimo", "occupancy_pct": 75, "avg_minutes_per_patient": 25}
    stock = [
        {"name": "Paracetamol", "reorder_priority": "normal", "days_until_stockout": 50,
         "projected_stock_tomorrow": 98, "status": "normal"},
    ]
    result = json.loads(
        await calc_server._generate_recommendations({"occupancy_data": occupancy, "stock_projections": stock})
    )

    assert result["success"] is True
    data = result["data"]
    assert data["overall_status"] == "normal"
    assert data["urgent_reorders"] == []
    assert len(data["recommendations"]) >= 1
