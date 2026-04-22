FROM python:3.12-slim

# Install uv from the official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# ── Dependency layer (cached; only rebuilds on pyproject.toml / uv.lock changes) ──
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# ── Source layer ──
COPY agent/       agent/
COPY mcp_servers/ mcp_servers/
COPY tests/       tests/

# Install the project package itself
RUN uv sync --frozen

# Runtime directories (overridable via volumes)
RUN mkdir -p data workspace

ENV DATABASE_PATH=data/clinic.db \
    WORKSPACE_PATH=workspace \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["uv", "run", "cun-agent"]
CMD ["Genera el cierre del turno de hoy para la clínica Centro Médico Norte"]
