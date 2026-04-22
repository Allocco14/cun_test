"""MCP server — alertas epidemiológicas via disease.sh (gratuito, sin API key)."""

import asyncio
import json

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

BASE_URL = "https://disease.sh/v3/covid-19"
TIMEOUT = 10.0  # seconds

server = Server("external-api-mcp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: object) -> str:
    return json.dumps({"success": True, "data": data, "error": None})


def _err(message: str) -> str:
    return json.dumps({"success": False, "data": None, "error": message})


def _alert_level(today_cases: int, today_deaths: int, active: int) -> str:
    if today_deaths >= 50 or today_cases >= 1000:
        return "crítico"
    if today_deaths >= 10 or today_cases >= 100:
        return "advertencia"
    return "normal"


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_epidemiological_alerts",
            description=(
                "Consulta alertas epidemiológicas actuales para un país usando disease.sh. "
                "Retorna casos activos, fallecidos hoy, nivel de alerta y recomendaciones."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "country": {
                        "type": "string",
                        "description": "Nombre del país en inglés o código ISO (ej: 'colombia', 'CO')",
                        "default": "colombia",
                    },
                },
            },
        ),
        types.Tool(
            name="get_global_health_summary",
            description="Resumen global de situación epidemiológica (todos los países combinados).",
            inputSchema={"type": "object", "properties": {}},
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
        "get_epidemiological_alerts": _get_epidemiological_alerts,
        "get_global_health_summary":  _get_global_health_summary,
    }
    handler = handlers.get(name)
    if handler is None:
        return _err(f"Herramienta desconocida: {name}")
    return await handler(args)


async def _get_epidemiological_alerts(args: dict) -> str:
    country = args.get("country", "colombia").strip()
    if not country:
        country = "colombia"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/countries/{country}")
            response.raise_for_status()
            raw = response.json()
    except httpx.TimeoutException:
        return _err("La API de alertas no respondió (timeout). No se pudo verificar estado epidemiológico.")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return _err(f"País no encontrado en la API: {country}")
        return _err(f"Error HTTP {exc.response.status_code} al consultar alertas.")
    except httpx.RequestError as exc:
        return _err(f"Error de conexión al consultar alertas: {exc}")

    today_cases  = raw.get("todayCases", 0) or 0
    today_deaths = raw.get("todayDeaths", 0) or 0
    active       = raw.get("active", 0) or 0
    level        = _alert_level(today_cases, today_deaths, active)

    recommendations = _build_recommendations(level, today_cases, today_deaths, active)

    return _ok({
        "country":         raw.get("country"),
        "updated":         raw.get("updated"),
        "active_cases":    active,
        "today_cases":     today_cases,
        "today_deaths":    today_deaths,
        "critical_cases":  raw.get("critical", 0),
        "total_cases":     raw.get("cases", 0),
        "total_deaths":    raw.get("deaths", 0),
        "alert_level":     level,
        "recommendations": recommendations,
        "source":          "disease.sh",
    })


async def _get_global_health_summary(args: dict) -> str:  # noqa: ARG001
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{BASE_URL}/all")
            response.raise_for_status()
            raw = response.json()
    except httpx.TimeoutException:
        return _err("Timeout al consultar resumen global.")
    except httpx.HTTPStatusError as exc:
        return _err(f"Error HTTP {exc.response.status_code} al consultar resumen global.")
    except httpx.RequestError as exc:
        return _err(f"Error de conexión: {exc}")

    return _ok({
        "active_cases":   raw.get("active", 0),
        "today_cases":    raw.get("todayCases", 0),
        "today_deaths":   raw.get("todayDeaths", 0),
        "critical_cases": raw.get("critical", 0),
        "total_cases":    raw.get("cases", 0),
        "total_deaths":   raw.get("deaths", 0),
        "affected_countries": raw.get("affectedCountries", 0),
        "source":         "disease.sh",
    })


def _build_recommendations(level: str, today_cases: int, today_deaths: int, active: int) -> list[str]:
    recs = []
    if level == "crítico":
        recs.append("Activar protocolo de contingencia epidemiológica.")
        recs.append("Notificar al personal sobre incremento de casos activos.")
        recs.append("Verificar disponibilidad de EPP completo en la clínica.")
    elif level == "advertencia":
        recs.append("Mantener vigilancia activa de síntomas en pacientes entrantes.")
        recs.append("Reforzar medidas de higiene y ventilación.")
    else:
        recs.append("Situación epidemiológica estable. Continuar protocolos estándar.")

    if today_deaths >= 10:
        recs.append(f"Reportar {today_deaths} fallecidos hoy — escalar a dirección médica.")
    if active > 50_000:
        recs.append("Alto volumen de casos activos en el país. Aumentar triaje en recepción.")

    return recs


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
