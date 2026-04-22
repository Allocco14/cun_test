"""Shared fixtures for all test modules."""

import sqlite3
from datetime import date

import pytest

TODAY = date.today().isoformat()
TEST_CLINIC = "Clínica Test"


@pytest.fixture
def today() -> str:
    return TODAY


@pytest.fixture
def test_clinic() -> str:
    return TEST_CLINIC


# ---------------------------------------------------------------------------
# Database fixture — temp SQLite with seeded data
# ---------------------------------------------------------------------------

@pytest.fixture
async def seeded_db(tmp_path, monkeypatch):
    """Temporary SQLite database seeded with minimal clinic data for today."""
    import mcp_servers.database.server as db_server

    db_file = str(tmp_path / "test_clinic.db")
    monkeypatch.setattr(db_server, "DATABASE_PATH", db_file)
    await db_server._init_db()

    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON")

    cur = conn.execute(
        "INSERT INTO patients (name, birth_date, gender) VALUES (?, ?, ?)",
        ("María García", "1975-01-01", "F"),
    )
    p1 = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO patients (name, birth_date, gender) VALUES (?, ?, ?)",
        ("Carlos López", "1988-06-15", "M"),
    )
    p2 = cur.lastrowid

    cur = conn.execute(
        "INSERT INTO visits (patient_id, visit_date, check_in_time, check_out_time, clinic_name, attending_physician) VALUES (?, ?, ?, ?, ?, ?)",
        (p1, TODAY, "08:00", "08:45", TEST_CLINIC, "Dr. Ramírez"),
    )
    v1 = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO visits (patient_id, visit_date, check_in_time, check_out_time, clinic_name, attending_physician) VALUES (?, ?, ?, ?, ?, ?)",
        (p2, TODAY, "09:00", "09:40", TEST_CLINIC, "Dr. Castro"),
    )
    v2 = cur.lastrowid

    conn.execute(
        "INSERT INTO diagnoses (visit_id, icd_code, description) VALUES (?, ?, ?)",
        (v1, "J06.9", "Infección respiratoria aguda"),
    )
    conn.execute(
        "INSERT INTO diagnoses (visit_id, icd_code, description) VALUES (?, ?, ?)",
        (v2, "I10", "Hipertensión esencial"),
    )

    cur = conn.execute("INSERT INTO medications (name, unit) VALUES (?, ?)", ("Amoxicilina", "cápsula 500mg"))
    m1 = cur.lastrowid
    cur = conn.execute("INSERT INTO medications (name, unit) VALUES (?, ?)", ("Paracetamol", "tableta 500mg"))
    m2 = cur.lastrowid

    # Amoxicilina: critical stock; Paracetamol: normal
    conn.execute(
        "INSERT INTO stock (medication_id, quantity, minimum_threshold, last_updated) VALUES (?, ?, ?, ?)",
        (m1, 3, 15, TODAY),
    )
    conn.execute(
        "INSERT INTO stock (medication_id, quantity, minimum_threshold, last_updated) VALUES (?, ?, ?, ?)",
        (m2, 80, 20, TODAY),
    )

    conn.execute(
        "INSERT INTO medication_consumption (visit_id, medication_id, quantity, consumption_date) VALUES (?, ?, ?, ?)",
        (v1, m1, 2, TODAY),
    )
    conn.execute(
        "INSERT INTO medication_consumption (visit_id, medication_id, quantity, consumption_date) VALUES (?, ?, ?, ?)",
        (v2, m2, 1, TODAY),
    )

    conn.commit()
    conn.close()
    yield db_file


# ---------------------------------------------------------------------------
# Filesystem fixture — temp workspace directory
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Temporary workspace directory with WORKSPACE_ROOT monkeypatched."""
    import mcp_servers.filesystem.server as fs_server

    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setattr(fs_server, "WORKSPACE_ROOT", ws)
    return ws
