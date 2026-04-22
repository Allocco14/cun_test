# CUN · AI Agent + MCP — Cierre de Turno Clínico

Agente autónomo construido con **Google ADK** que orquesta 4 servidores MCP propios para generar el cierre de turno diario de una clínica ambulatoria con un único prompt en lenguaje natural.

---

## Requisitos

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Cuenta Google AI Studio → `GOOGLE_API_KEY`

---

## Inicio rápido

```bash
# 1. Clonar e instalar dependencias
git clone <repo-url>
cd cun_test
uv sync

# 2. Configurar entorno
cp .env.example .env
# Editar .env y completar GOOGLE_API_KEY

# 3. Poblar base de datos con datos del turno de hoy
uv run python -m mcp_servers.database.seed

# 4. Ejecutar el agente
uv run cun-agent "Genera el cierre del turno de hoy para la clínica Centro Médico Norte"
```

El reporte queda en `workspace/cierre_YYYY-MM-DD.md`.

---

## Tests

```bash
# Todos los tests
uv run pytest

# Un archivo específico
uv run pytest tests/test_database_mcp.py -v

# Un test por nombre
uv run pytest tests/test_filesystem_mcp.py::test_path_traversal_write_is_blocked -v
```

35 tests automatizados — happy path, errores y seguridad (path traversal, SQL injection).

---

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `GOOGLE_API_KEY` | — | **Requerida.** Clave de Google AI Studio |
| `AGENT_MODEL` | `gemini-3-flash-preview` | Modelo Gemini a usar |
| `DATABASE_PATH` | `data/clinic.db` | Ruta al archivo SQLite |
| `WORKSPACE_PATH` | `workspace` | Directorio de salida de reportes |

---

## Arquitectura

```
┌─────────────────────────────────────────────────┐
│                  Google ADK Agent                │
│  (gemini-3-flash-preview · orquesta herramientas MCP)  │
└──────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │
  ┌────▼───┐ ┌───▼────┐ ┌───▼───┐ ┌────▼──────┐
  │   DB   │ │  File  │ │  API  │ │Calculator │
  │  MCP   │ │System  │ │  MCP  │ │   MCP     │
  │        │ │  MCP   │ │       │ │           │
  │SQLite  │ │/worksp.│ │diseas │ │Ocupación  │
  │7 tools │ │4 tools │ │e.sh   │ │Proyección │
  │        │ │sandbox │ │2 tools│ │3 tools    │
  └────────┘ └────────┘ └───────┘ └───────────┘
```

### MCP servers

| Server | Herramientas | Responsabilidad |
|---|---|---|
| `mcp_servers/database` | 7 | Lecturas y escrituras SQLite (pacientes, visitas, diagnósticos, stock) |
| `mcp_servers/filesystem` | 4 | Leer/escribir/listar/borrar archivos dentro de `/workspace` |
| `mcp_servers/external_api` | 2 | Alertas epidemiológicas vía [disease.sh](https://disease.sh) (gratuito, sin API key) |
| `mcp_servers/calculator` | 3 | Ocupación del turno, proyección de stock, recomendaciones |

Cada herramienta retorna siempre `{"success": bool, "data": ..., "error": str | null}`. Si `success` es `false`, el agente anota el error en el reporte y continúa.

### Base de datos

Esquema en `mcp_servers/database/schema.sql`. Tablas: `patients`, `visits`, `diagnoses`, `medications`, `stock`, `medication_consumption`.

### Flujo del agente (5 pasos ordenados)

1. `get_epidemiological_alerts` → alertas sanitarias de Colombia
2. `get_shift_summary` + `get_top_diagnoses` → resumen del turno
3. `get_stock_status` + `compare_stock_consumption` → inventario vs consumo
4. `calculate_occupancy` + `project_stock` + `generate_recommendations` → cálculos
5. `write_file` → escribe `workspace/cierre_YYYY-MM-DD.md`

---

## Docker

```bash
# Construir imagen
docker compose build

# 1. Poblar la base de datos
docker compose run --rm seed

# 2. Ejecutar el agente (requiere GOOGLE_API_KEY en .env)
docker compose run --rm agent

# Prompt personalizado
docker compose run --rm agent "Genera el cierre del turno de hoy para la clínica Sur"

# Correr los tests dentro del contenedor (no requiere API key)
docker compose run --rm test
```

El reporte queda en `./workspace/` del host gracias al bind mount.

---

## Lint

```bash
uv run ruff check .
uv run ruff format .
```

---

## Caso de uso documentado

Ver [`use_cases/cierre_turno.md`](use_cases/cierre_turno.md).
