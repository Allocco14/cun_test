"""MCP server — SQLite database for clinic operations."""

import asyncio
import json
import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/clinic.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

server = Server("database-mcp")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ok(data: object) -> str:
    return json.dumps({"success": True, "data": data, "error": None})


def _err(message: str) -> str:
    return json.dumps({"success": False, "data": None, "error": message})


@asynccontextmanager
async def _get_db() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


async def _fetchall(db: aiosqlite.Connection, sql: str, params: tuple = ()) -> list:
    cursor = await db.execute(sql, params)
    rows = await cursor.fetchall()
    await cursor.close()
    return rows


async def _fetchone(db: aiosqlite.Connection, sql: str, params: tuple = ()):
    cursor = await db.execute(sql, params)
    row = await cursor.fetchone()
    await cursor.close()
    return row


async def _init_db() -> None:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(schema)
        await db.commit()


def _stock_status(quantity: float, threshold: float) -> str:
    if quantity <= threshold * 0.5:
        return "crítico"
    if quantity <= threshold:
        return "bajo"
    return "normal"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_shift_summary",
            description="Resumen del turno: pacientes atendidos, horario inicio/cierre y médicos.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date":        {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                    "clinic_name": {"type": "string", "description": "Nombre de la clínica"},
                },
                "required": ["date", "clinic_name"],
            },
        ),
        types.Tool(
            name="get_top_diagnoses",
            description="Diagnósticos más frecuentes del día.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date":  {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                    "limit": {"type": "integer", "description": "Cantidad a retornar (default 3)", "default": 3},
                },
                "required": ["date"],
            },
        ),
        types.Tool(
            name="get_stock_status",
            description="Estado actual del inventario de medicamentos (normal/bajo/crítico).",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="get_daily_consumption",
            description="Medicamentos consumidos durante el día.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                },
                "required": ["date"],
            },
        ),
        types.Tool(
            name="compare_stock_consumption",
            description="Compara stock actual con consumo del día. Incluye días de inventario restantes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"},
                },
                "required": ["date"],
            },
        ),
        types.Tool(
            name="update_stock",
            description="Ajusta el stock de un medicamento (positivo = reposición, negativo = consumo).",
            inputSchema={
                "type": "object",
                "properties": {
                    "medication_name": {"type": "string"},
                    "quantity_delta":  {"type": "number", "description": "Positivo suma, negativo resta"},
                    "reason":          {"type": "string", "description": "Motivo del ajuste"},
                },
                "required": ["medication_name", "quantity_delta", "reason"],
            },
        ),
        types.Tool(
            name="create_patient",
            description="Registra un nuevo paciente en la base de datos.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name":       {"type": "string"},
                    "birth_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "gender":     {"type": "string", "enum": ["M", "F", "O"]},
                },
                "required": ["name"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    args = arguments or {}
    try:
        result = await _dispatch(name, args)
    except Exception as exc:
        result = _err(str(exc))
    return [types.TextContent(type="text", text=result)]


async def _dispatch(name: str, args: dict) -> str:
    handlers = {
        "get_shift_summary":         _get_shift_summary,
        "get_top_diagnoses":         _get_top_diagnoses,
        "get_stock_status":          _get_stock_status,
        "get_daily_consumption":     _get_daily_consumption,
        "compare_stock_consumption": _compare_stock_consumption,
        "update_stock":              _update_stock,
        "create_patient":            _create_patient,
    }
    handler = handlers.get(name)
    if handler is None:
        return _err(f"Herramienta desconocida: {name}")
    return await handler(args)


async def _get_shift_summary(args: dict) -> str:
    date = args.get("date", "")
    clinic = args.get("clinic_name", "")
    if not date or not clinic:
        return _err("Se requieren 'date' y 'clinic_name'")

    async with _get_db() as db:
        rows = await _fetchall(
            db,
            """SELECT v.id, p.name AS patient, v.check_in_time, v.check_out_time,
                      v.attending_physician
               FROM visits v
               JOIN patients p ON p.id = v.patient_id
               WHERE v.visit_date = ? AND v.clinic_name = ?
               ORDER BY v.check_in_time""",
            (date, clinic),
        )

    if not rows:
        return _ok({
            "total_visits": 0,
            "patients": [],
            "shift_start": None,
            "shift_end": None,
            "attending_physicians": [],
            "note": "Sin pacientes registrados para esta fecha y clínica.",
        })

    physicians = sorted({r["attending_physician"] for r in rows if r["attending_physician"]})
    return _ok({
        "total_visits": len(rows),
        "patients": [{"name": r["patient"], "check_in": r["check_in_time"], "check_out": r["check_out_time"]} for r in rows],
        "shift_start": rows[0]["check_in_time"],
        "shift_end": rows[-1]["check_out_time"],
        "attending_physicians": physicians,
    })


async def _get_top_diagnoses(args: dict) -> str:
    date = args.get("date", "")
    limit = int(args.get("limit", 3))
    if not date:
        return _err("Se requiere 'date'")

    async with _get_db() as db:
        rows = await _fetchall(
            db,
            """SELECT d.icd_code, d.description, COUNT(*) AS count
               FROM diagnoses d
               JOIN visits v ON v.id = d.visit_id
               WHERE v.visit_date = ?
               GROUP BY d.icd_code, d.description
               ORDER BY count DESC
               LIMIT ?""",
            (date, limit),
        )

    return _ok([dict(r) for r in rows])


async def _get_stock_status(args: dict) -> str:  # noqa: ARG001
    async with _get_db() as db:
        rows = await _fetchall(
            db,
            """SELECT m.id, m.name, m.unit, s.quantity, s.minimum_threshold, s.last_updated
               FROM stock s
               JOIN medications m ON m.id = s.medication_id
               ORDER BY s.quantity ASC""",
        )

    result = []
    for r in rows:
        d = dict(r)
        d["status"] = _stock_status(d["quantity"], d["minimum_threshold"])
        result.append(d)
    return _ok(result)


async def _get_daily_consumption(args: dict) -> str:
    date = args.get("date", "")
    if not date:
        return _err("Se requiere 'date'")

    async with _get_db() as db:
        rows = await _fetchall(
            db,
            """SELECT m.name AS medication_name, m.unit,
                      SUM(mc.quantity) AS total_consumed,
                      COUNT(DISTINCT mc.visit_id) AS visit_count
               FROM medication_consumption mc
               JOIN medications m ON m.id = mc.medication_id
               WHERE mc.consumption_date = ?
               GROUP BY m.id
               ORDER BY total_consumed DESC""",
            (date,),
        )

    return _ok([dict(r) for r in rows])


async def _compare_stock_consumption(args: dict) -> str:
    date = args.get("date", "")
    if not date:
        return _err("Se requiere 'date'")

    async with _get_db() as db:
        rows = await _fetchall(
            db,
            """SELECT m.name, m.unit,
                      s.quantity AS current_stock,
                      s.minimum_threshold,
                      COALESCE(SUM(mc.quantity), 0) AS consumed_today
               FROM stock s
               JOIN medications m ON m.id = s.medication_id
               LEFT JOIN medication_consumption mc
                   ON mc.medication_id = s.medication_id AND mc.consumption_date = ?
               GROUP BY m.id
               ORDER BY consumed_today DESC""",
            (date,),
        )

    result = []
    for r in rows:
        d = dict(r)
        remaining = d["current_stock"] - d["consumed_today"]
        d["stock_after_today"] = round(remaining, 2)
        d["status"] = _stock_status(remaining, d["minimum_threshold"])
        d["days_remaining"] = (
            round(remaining / d["consumed_today"], 1) if d["consumed_today"] > 0 else None
        )
        result.append(d)
    return _ok(result)


async def _update_stock(args: dict) -> str:
    name = args.get("medication_name", "").strip()
    delta = args.get("quantity_delta")
    reason = args.get("reason", "")
    if not name or delta is None:
        return _err("Se requieren 'medication_name' y 'quantity_delta'")

    async with _get_db() as db:
        row = await _fetchone(
            db,
            "SELECT s.quantity FROM stock s JOIN medications m ON m.id = s.medication_id WHERE m.name = ?",
            (name,),
        )
        if row is None:
            return _err(f"Medicamento no encontrado: {name}")

        old_qty = row["quantity"]
        new_qty = round(old_qty + float(delta), 4)
        if new_qty < 0:
            return _err(f"Stock resultante negativo ({new_qty}). Operación rechazada.")

        await db.execute(
            """UPDATE stock SET quantity = ?, last_updated = date('now')
               WHERE medication_id = (SELECT id FROM medications WHERE name = ?)""",
            (new_qty, name),
        )
        await db.commit()

    return _ok({"medication_name": name, "old_quantity": old_qty, "new_quantity": new_qty, "reason": reason})


async def _create_patient(args: dict) -> str:
    name = args.get("name", "").strip()
    birth_date = args.get("birth_date")
    gender = args.get("gender")
    if not name:
        return _err("Se requiere 'name'")

    async with _get_db() as db:
        cursor = await db.execute(
            "INSERT INTO patients (name, birth_date, gender) VALUES (?, ?, ?)",
            (name, birth_date, gender),
        )
        await db.commit()
        patient_id = cursor.lastrowid

    return _ok({"id": patient_id, "name": name})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    await _init_db()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
