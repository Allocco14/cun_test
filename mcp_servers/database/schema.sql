CREATE TABLE IF NOT EXISTS patients (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL,
    birth_date TEXT,
    gender  TEXT CHECK(gender IN ('M', 'F', 'O'))
);

CREATE TABLE IF NOT EXISTS visits (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id          INTEGER NOT NULL,
    visit_date          TEXT    NOT NULL,  -- YYYY-MM-DD
    check_in_time       TEXT,              -- HH:MM
    check_out_time      TEXT,              -- HH:MM
    clinic_name         TEXT    NOT NULL,
    attending_physician TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(id)
);

CREATE TABLE IF NOT EXISTS diagnoses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id    INTEGER NOT NULL,
    icd_code    TEXT,
    description TEXT    NOT NULL,
    FOREIGN KEY (visit_id) REFERENCES visits(id)
);

CREATE TABLE IF NOT EXISTS medications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    unit        TEXT    NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS stock (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    medication_id       INTEGER NOT NULL UNIQUE,
    quantity            REAL    NOT NULL DEFAULT 0,
    minimum_threshold   REAL    NOT NULL DEFAULT 10,
    last_updated        TEXT    NOT NULL,
    FOREIGN KEY (medication_id) REFERENCES medications(id)
);

CREATE TABLE IF NOT EXISTS medication_consumption (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id        INTEGER NOT NULL,
    medication_id   INTEGER NOT NULL,
    quantity        REAL    NOT NULL,
    consumption_date TEXT   NOT NULL,  -- YYYY-MM-DD
    FOREIGN KEY (visit_id)      REFERENCES visits(id),
    FOREIGN KEY (medication_id) REFERENCES medications(id)
);
