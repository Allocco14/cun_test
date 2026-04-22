"""Tests for the database MCP server (11 tests)."""

import json
import sqlite3

import pytest

import mcp_servers.database.server as db_server
from tests.conftest import TODAY, TEST_CLINIC


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_shift_summary_returns_patients(seeded_db):
    result = json.loads(await db_server._get_shift_summary({"date": TODAY, "clinic_name": TEST_CLINIC}))

    assert result["success"] is True
    data = result["data"]
    assert data["total_visits"] == 2
    assert data["shift_start"] == "08:00"
    assert data["shift_end"] == "09:40"
    assert len(data["patients"]) == 2
    assert any("María" in p["name"] for p in data["patients"])


async def test_top_diagnoses_sorted_by_frequency(seeded_db):
    result = json.loads(await db_server._get_top_diagnoses({"date": TODAY, "limit": 3}))

    assert result["success"] is True
    diags = result["data"]
    assert len(diags) >= 1
    codes = [d["icd_code"] for d in diags]
    assert "J06.9" in codes
    assert "I10" in codes


async def test_stock_status_contains_critical_item(seeded_db):
    result = json.loads(await db_server._get_stock_status({}))

    assert result["success"] is True
    statuses = {item["name"]: item["status"] for item in result["data"]}
    assert statuses["Amoxicilina"] == "crítico"
    assert statuses["Paracetamol"] == "normal"


async def test_daily_consumption_aggregates_correctly(seeded_db):
    result = json.loads(await db_server._get_daily_consumption({"date": TODAY}))

    assert result["success"] is True
    consumed = {row["medication_name"]: row["total_consumed"] for row in result["data"]}
    assert consumed["Amoxicilina"] == 2
    assert consumed["Paracetamol"] == 1


async def test_compare_stock_consumption_calculates_remaining(seeded_db):
    result = json.loads(await db_server._compare_stock_consumption({"date": TODAY}))

    assert result["success"] is True
    items = {row["name"]: row for row in result["data"]}

    amoxi = items["Amoxicilina"]
    assert amoxi["stock_after_today"] == 1.0   # 3 - 2
    assert amoxi["consumed_today"] == 2
    assert amoxi["status"] == "crítico"


async def test_update_stock_increases_quantity(seeded_db):
    result = json.loads(
        await db_server._update_stock(
            {"medication_name": "Amoxicilina", "quantity_delta": 20, "reason": "Reposición de prueba"}
        )
    )

    assert result["success"] is True
    assert result["data"]["new_quantity"] == 23.0   # 3 + 20
    assert result["data"]["old_quantity"] == 3.0


async def test_create_patient_returns_id(seeded_db):
    result = json.loads(
        await db_server._create_patient(
            {"name": "Nuevo Paciente", "birth_date": "2000-05-10", "gender": "F"}
        )
    )

    assert result["success"] is True
    assert result["data"]["id"] is not None
    assert result["data"]["name"] == "Nuevo Paciente"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

async def test_shift_summary_no_patients_returns_empty(seeded_db):
    result = json.loads(
        await db_server._get_shift_summary({"date": "2000-01-01", "clinic_name": TEST_CLINIC})
    )

    assert result["success"] is True
    assert result["data"]["total_visits"] == 0
    assert "note" in result["data"]


async def test_shift_summary_missing_params_returns_error(seeded_db):
    result = json.loads(await db_server._get_shift_summary({}))

    assert result["success"] is False
    assert result["error"] is not None


async def test_update_stock_prevents_negative_balance(seeded_db):
    result = json.loads(
        await db_server._update_stock(
            {"medication_name": "Amoxicilina", "quantity_delta": -999, "reason": "Reducción imposible"}
        )
    )

    assert result["success"] is False
    assert "negativo" in result["error"].lower()


async def test_create_patient_missing_name_returns_error(seeded_db):
    result = json.loads(await db_server._create_patient({}))

    assert result["success"] is False
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

async def test_sql_injection_in_clinic_name_is_safe(seeded_db):
    """Parameterized queries must neutralize SQL injection attempts."""
    malicious = "'; DROP TABLE patients; --"
    result = json.loads(
        await db_server._get_shift_summary({"date": TODAY, "clinic_name": malicious})
    )

    # Should return empty, not crash
    assert result["success"] is True
    assert result["data"]["total_visits"] == 0

    # Table must still exist and contain rows
    conn = sqlite3.connect(seeded_db)
    count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    conn.close()
    assert count >= 2
