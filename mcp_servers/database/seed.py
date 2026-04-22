"""Populates the SQLite database with realistic sample data for today's shift."""

import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path("data/clinic.db")
SCHEMA_PATH = Path("mcp_servers/database/schema.sql")
TODAY = date.today().isoformat()
CLINIC = "Centro Médico Norte"


def seed() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    _seed_patients(conn)
    _seed_medications(conn)
    _seed_stock(conn)
    _seed_visits(conn)
    _seed_diagnoses(conn)
    _seed_consumption(conn)

    conn.commit()
    conn.close()
    print(f"Seed completed for {TODAY} — {CLINIC}")


def _seed_patients(conn: sqlite3.Connection) -> None:
    patients = [
        ("María García",       "1975-03-15", "F"),
        ("Carlos López",       "1988-07-22", "M"),
        ("Ana Martínez",       "1962-11-08", "F"),
        ("Pedro Rodríguez",    "1990-02-14", "M"),
        ("Luisa Hernández",    "1995-09-30", "F"),
        ("Jorge Gómez",        "1958-04-20", "M"),
        ("Carmen Díaz",        "2000-01-17", "F"),
        ("Roberto Torres",     "1982-06-05", "M"),
        ("Isabel Flores",      "1971-12-28", "F"),
        ("Miguel Sánchez",     "1945-08-10", "M"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO patients (name, birth_date, gender) VALUES (?, ?, ?)",
        patients,
    )


def _seed_medications(conn: sqlite3.Connection) -> None:
    medications = [
        ("Metformina",   "tableta 500mg", "Antidiabético oral"),
        ("Lisinopril",   "tableta 10mg",  "IECA antihipertensivo"),
        ("Amoxicilina",  "cápsula 500mg", "Antibiótico betalactámico"),
        ("Ibuprofeno",   "tableta 400mg", "Antiinflamatorio no esteroideo"),
        ("Omeprazol",    "cápsula 20mg",  "Inhibidor bomba de protones"),
        ("Lorazepam",    "tableta 1mg",   "Ansiolítico benzodiazepínico"),
        ("Salbutamol",   "inhalador",     "Broncodilatador"),
        ("Paracetamol",  "tableta 500mg", "Analgésico antipirético"),
        ("Enalapril",    "tableta 5mg",   "IECA antihipertensivo"),
        ("Clonazepam",   "tableta 0.5mg", "Antiepiléptico/ansiolítico"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO medications (name, unit, description) VALUES (?, ?, ?)",
        medications,
    )


def _seed_stock(conn: sqlite3.Connection) -> None:
    # (medication_name, quantity, minimum_threshold)
    # normal: qty > threshold | low: qty <= threshold | critical: qty <= threshold * 0.5
    stock_data = [
        ("Metformina",  45,  20),   # normal
        ("Lisinopril",   8,  10),   # low
        ("Amoxicilina",  4,  15),   # critical
        ("Ibuprofeno",  60,  15),   # normal
        ("Omeprazol",   18,  10),   # normal
        ("Lorazepam",    2,   5),   # critical
        ("Salbutamol",   5,   8),   # low
        ("Paracetamol", 120, 25),   # normal
        ("Enalapril",   14,  10),   # normal
        ("Clonazepam",   3,   6),   # critical (3 <= 3.0)
    ]
    for name, qty, threshold in stock_data:
        row = conn.execute("SELECT id FROM medications WHERE name = ?", (name,)).fetchone()
        if row:
            conn.execute(
                """INSERT INTO stock (medication_id, quantity, minimum_threshold, last_updated)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(medication_id) DO UPDATE SET
                       quantity=excluded.quantity,
                       minimum_threshold=excluded.minimum_threshold,
                       last_updated=excluded.last_updated""",
                (row[0], qty, threshold, TODAY),
            )


def _seed_visits(conn: sqlite3.Connection) -> None:
    # 8 visits today for CLINIC
    visits = [
        (1, TODAY, "08:00", "08:45", CLINIC, "Dr. Ramírez"),
        (2, TODAY, "08:50", "09:30", CLINIC, "Dr. Ramírez"),
        (3, TODAY, "09:35", "10:15", CLINIC, "Dr. Castro"),
        (4, TODAY, "10:20", "11:00", CLINIC, "Dr. Ramírez"),
        (5, TODAY, "11:05", "11:50", CLINIC, "Dr. Castro"),
        (6, TODAY, "14:00", "14:45", CLINIC, "Dr. Ramírez"),
        (7, TODAY, "15:00", "15:40", CLINIC, "Dr. Castro"),
        (8, TODAY, "16:00", "16:45", CLINIC, "Dr. Ramírez"),
    ]
    # Only insert if no visits exist for today
    existing = conn.execute(
        "SELECT COUNT(*) FROM visits WHERE visit_date = ? AND clinic_name = ?",
        (TODAY, CLINIC),
    ).fetchone()[0]
    if existing == 0:
        conn.executemany(
            """INSERT INTO visits
               (patient_id, visit_date, check_in_time, check_out_time, clinic_name, attending_physician)
               VALUES (?, ?, ?, ?, ?, ?)""",
            visits,
        )


def _seed_diagnoses(conn: sqlite3.Connection) -> None:
    visit_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM visits WHERE visit_date = ? AND clinic_name = ? ORDER BY id",
            (TODAY, CLINIC),
        ).fetchall()
    ]
    if not visit_ids or len(visit_ids) < 8:
        return

    diagnoses = [
        (visit_ids[0], "I10",   "Hipertensión esencial"),
        (visit_ids[1], "J06.9", "Infección respiratoria aguda alta"),
        (visit_ids[2], "E11",   "Diabetes mellitus tipo 2"),
        (visit_ids[3], "J06.9", "Infección respiratoria aguda alta"),
        (visit_ids[4], "F41.1", "Trastorno de ansiedad generalizada"),
        (visit_ids[5], "I10",   "Hipertensión esencial"),
        (visit_ids[6], "K29.7", "Gastritis no especificada"),
        (visit_ids[7], "J06.9", "Infección respiratoria aguda alta"),
    ]
    existing = conn.execute(
        "SELECT COUNT(*) FROM diagnoses WHERE visit_id = ?", (visit_ids[0],)
    ).fetchone()[0]
    if existing == 0:
        conn.executemany(
            "INSERT INTO diagnoses (visit_id, icd_code, description) VALUES (?, ?, ?)",
            diagnoses,
        )


def _seed_consumption(conn: sqlite3.Connection) -> None:
    visit_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM visits WHERE visit_date = ? AND clinic_name = ? ORDER BY id",
            (TODAY, CLINIC),
        ).fetchall()
    ]
    if not visit_ids or len(visit_ids) < 8:
        return

    def med_id(name: str) -> int:
        return conn.execute("SELECT id FROM medications WHERE name = ?", (name,)).fetchone()[0]

    # (visit_idx, medication_name, quantity)
    consumptions = [
        (0, "Lisinopril",   1),  # hypertension
        (0, "Enalapril",    1),
        (1, "Amoxicilina",  1),  # respiratory
        (1, "Paracetamol",  1),
        (2, "Metformina",   2),  # diabetes
        (3, "Amoxicilina",  1),  # respiratory
        (3, "Ibuprofeno",   1),
        (4, "Lorazepam",    1),  # anxiety
        (4, "Clonazepam",   1),
        (5, "Lisinopril",   1),  # hypertension
        (6, "Omeprazol",    1),  # gastritis
        (6, "Ibuprofeno",   1),
        (7, "Amoxicilina",  1),  # respiratory
        (7, "Paracetamol",  1),
    ]
    existing = conn.execute(
        "SELECT COUNT(*) FROM medication_consumption WHERE consumption_date = ?", (TODAY,)
    ).fetchone()[0]
    if existing == 0:
        conn.executemany(
            """INSERT INTO medication_consumption
               (visit_id, medication_id, quantity, consumption_date)
               VALUES (?, ?, ?, ?)""",
            [
                (visit_ids[vi], med_id(med), qty, TODAY)
                for vi, med, qty in consumptions
            ],
        )


if __name__ == "__main__":
    seed()
