"""MCP server — cálculos de ocupación y proyección de inventario (sin I/O externo)."""

import asyncio
import json
import math

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

server = Server("calculator-mcp")

REORDER_DAYS_THRESHOLD = 3   # alert if stock runs out in ≤ 3 days
OPTIMAL_OCCUPANCY_MIN  = 60  # % below which capacity is underutilized
OPTIMAL_OCCUPANCY_MAX  = 90  # % above which clinic is overloaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: object) -> str:
    return json.dumps({"success": True, "data": data, "error": None})


def _err(message: str) -> str:
    return json.dumps({"success": False, "data": None, "error": message})


def _occupancy_status(pct: float) -> str:
    if pct < OPTIMAL_OCCUPANCY_MIN:
        return "subutilizado"
    if pct <= OPTIMAL_OCCUPANCY_MAX:
        return "óptimo"
    return "sobrecargado"


def _reorder_priority(days_remaining: float | None, status: str) -> str:
    if status == "crítico" or (days_remaining is not None and days_remaining <= 1):
        return "urgente"
    if status == "bajo" or (days_remaining is not None and days_remaining <= REORDER_DAYS_THRESHOLD):
        return "alta"
    return "normal"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="calculate_occupancy",
            description=(
                "Calcula el porcentaje de ocupación del turno y métricas derivadas "
                "(tiempo promedio por paciente, estado de capacidad)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "visits_today": {
                        "type": "integer",
                        "description": "Número de pacientes atendidos en el turno",
                    },
                    "max_capacity": {
                        "type": "integer",
                        "description": "Capacidad máxima de pacientes por turno",
                    },
                    "shift_duration_minutes": {
                        "type": "integer",
                        "description": "Duración total del turno en minutos (default 480 = 8 h)",
                        "default": 480,
                    },
                },
                "required": ["visits_today", "max_capacity"],
            },
        ),
        types.Tool(
            name="project_stock",
            description=(
                "Proyecta el inventario para mañana y calcula días hasta agotamiento "
                "por medicamento, basándose en el consumo de hoy."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "stock_items": {
                        "type": "array",
                        "description": "Lista de medicamentos con su stock y consumo del día",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":               {"type": "string"},
                                "current_stock":      {"type": "number"},
                                "consumed_today":     {"type": "number"},
                                "minimum_threshold":  {"type": "number"},
                                "status":             {"type": "string"},
                            },
                            "required": ["name", "current_stock", "consumed_today", "minimum_threshold"],
                        },
                    },
                },
                "required": ["stock_items"],
            },
        ),
        types.Tool(
            name="generate_recommendations",
            description=(
                "Genera recomendaciones automáticas consolidadas cruzando datos de "
                "ocupación y proyección de inventario."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "occupancy_data": {
                        "type": "object",
                        "description": "Resultado de calculate_occupancy",
                    },
                    "stock_projections": {
                        "type": "array",
                        "description": "Resultado de project_stock (campo data)",
                    },
                },
                "required": ["occupancy_data", "stock_projections"],
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
        "calculate_occupancy":    _calculate_occupancy,
        "project_stock":          _project_stock,
        "generate_recommendations": _generate_recommendations,
    }
    handler = handlers.get(name)
    if handler is None:
        return _err(f"Herramienta desconocida: {name}")
    return await handler(args)


async def _calculate_occupancy(args: dict) -> str:
    visits_today = args.get("visits_today")
    max_capacity = args.get("max_capacity")
    shift_minutes = int(args.get("shift_duration_minutes", 480))

    if visits_today is None or max_capacity is None:
        return _err("Se requieren 'visits_today' y 'max_capacity'")
    if not isinstance(visits_today, int) or visits_today < 0:
        return _err("'visits_today' debe ser un entero no negativo")
    if not isinstance(max_capacity, int) or max_capacity <= 0:
        return _err("'max_capacity' debe ser un entero positivo")

    occupancy_pct = round((visits_today / max_capacity) * 100, 1)
    avg_minutes   = round(shift_minutes / visits_today, 1) if visits_today > 0 else None
    status        = _occupancy_status(occupancy_pct)

    # Projected visits for tomorrow using same occupancy rate
    projected_tomorrow = visits_today  # baseline: same demand

    return _ok({
        "visits_today":          visits_today,
        "max_capacity":          max_capacity,
        "occupancy_pct":         occupancy_pct,
        "status":                status,
        "avg_minutes_per_patient": avg_minutes,
        "shift_duration_minutes":  shift_minutes,
        "projected_visits_tomorrow": projected_tomorrow,
        "available_slots_remaining": max(0, max_capacity - visits_today),
    })


async def _project_stock(args: dict) -> str:
    items = args.get("stock_items")
    if not isinstance(items, list):
        return _err("Se requiere 'stock_items' como lista")
    if len(items) == 0:
        return _ok([])

    projections = []
    for item in items:
        name      = item.get("name", "desconocido")
        stock     = float(item.get("current_stock", 0))
        consumed  = float(item.get("consumed_today", 0))
        threshold = float(item.get("minimum_threshold", 0))
        status    = item.get("status", _stock_status_from_values(stock, threshold))

        projected_tomorrow = round(stock - consumed, 4)
        projected_tomorrow = max(0.0, projected_tomorrow)

        days_remaining = (
            math.floor(stock / consumed) if consumed > 0 else None
        )

        priority = _reorder_priority(days_remaining, status)

        projections.append({
            "name":                   name,
            "current_stock":          stock,
            "consumed_today":         consumed,
            "projected_stock_tomorrow": projected_tomorrow,
            "days_until_stockout":    days_remaining,
            "reorder_priority":       priority,
            "status":                 status,
            "needs_reorder":          priority in ("urgente", "alta"),
        })

    # Sort: urgent first
    priority_order = {"urgente": 0, "alta": 1, "normal": 2}
    projections.sort(key=lambda x: priority_order.get(x["reorder_priority"], 9))

    return _ok(projections)


async def _generate_recommendations(args: dict) -> str:
    occupancy = args.get("occupancy_data") or {}
    stock_proj = args.get("stock_projections") or []

    if not occupancy and not stock_proj:
        return _err("Se requiere al menos 'occupancy_data' o 'stock_projections'")

    recommendations: list[str] = []
    alerts: list[str] = []

    # --- Occupancy recommendations ---
    occ_status = occupancy.get("status")
    occ_pct    = occupancy.get("occupancy_pct", 0)

    if occ_status == "sobrecargado":
        alerts.append(f"Ocupación al {occ_pct}% — clínica sobrecargada.")
        recommendations.append("Considerar apertura de turno adicional o derivación de pacientes.")
        recommendations.append("Revisar agenda del día siguiente para evitar sobredemanda.")
    elif occ_status == "subutilizado":
        recommendations.append(f"Ocupación baja ({occ_pct}%). Verificar ausentismo o problemas en agendamiento.")
    else:
        recommendations.append(f"Ocupación óptima ({occ_pct}%). Sin acciones requeridas en capacidad.")

    avg_min = occupancy.get("avg_minutes_per_patient")
    if avg_min and avg_min < 10:
        alerts.append(f"Tiempo promedio por paciente muy bajo ({avg_min} min). Revisar calidad de atención.")

    # --- Stock recommendations ---
    urgent  = [p for p in stock_proj if p.get("reorder_priority") == "urgente"]
    high    = [p for p in stock_proj if p.get("reorder_priority") == "alta"]
    zero    = [p for p in stock_proj if p.get("projected_stock_tomorrow", 1) <= 0]

    for med in zero:
        alerts.append(f"ACCIÓN URGENTE: {med['name']} se agotará mañana. Stock actual: {med['current_stock']}.")
    for med in urgent:
        alerts.append(f"Reordenar HOY: {med['name']} (días restantes: {med.get('days_until_stockout', '?')}).")
    for med in high:
        recommendations.append(f"Gestionar reposición pronto: {med['name']} (días restantes: {med.get('days_until_stockout', '?')}).")

    if not urgent and not high:
        recommendations.append("Inventario de medicamentos en niveles aceptables para mañana.")

    overall = "crítico" if alerts else ("advertencia" if high else "normal")

    return _ok({
        "overall_status":    overall,
        "alerts":            alerts,
        "recommendations":   recommendations,
        "urgent_reorders":   [m["name"] for m in urgent],
        "high_priority_reorders": [m["name"] for m in high],
    })


def _stock_status_from_values(quantity: float, threshold: float) -> str:
    if threshold <= 0:
        return "normal"
    if quantity <= threshold * 0.5:
        return "crítico"
    if quantity <= threshold:
        return "bajo"
    return "normal"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
