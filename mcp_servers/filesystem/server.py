"""MCP server — sandboxed filesystem operations under /workspace."""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

load_dotenv()

WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_PATH", "workspace")).resolve()

server = Server("filesystem-mcp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(data: object) -> str:
    return json.dumps({"success": True, "data": data, "error": None})


def _err(message: str) -> str:
    return json.dumps({"success": False, "data": None, "error": message})


def _safe_path(relative: str) -> Path | None:
    """Resolve path and verify it stays inside WORKSPACE_ROOT (no traversal)."""
    # Strip leading slashes/backslashes so join works correctly
    cleaned = relative.lstrip("/\\")
    candidate = (WORKSPACE_ROOT / cleaned).resolve()
    try:
        candidate.relative_to(WORKSPACE_ROOT)
        return candidate
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="write_file",
            description="Escribe contenido en un archivo dentro del workspace. Crea directorios intermedios si no existen.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Ruta relativa al workspace (ej: cierre_2026-04-21.md)"},
                    "content": {"type": "string", "description": "Contenido a escribir"},
                },
                "required": ["path", "content"],
            },
        ),
        types.Tool(
            name="read_file",
            description="Lee el contenido de un archivo dentro del workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta relativa al workspace"},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="list_files",
            description="Lista archivos y subdirectorios dentro del workspace (o de un subdirectorio del mismo).",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Subdirectorio a listar (vacío = raíz del workspace)",
                        "default": "",
                    },
                },
            },
        ),
        types.Tool(
            name="delete_file",
            description="Elimina un archivo dentro del workspace.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta relativa al workspace"},
                },
                "required": ["path"],
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
        "write_file":  _write_file,
        "read_file":   _read_file,
        "list_files":  _list_files,
        "delete_file": _delete_file,
    }
    handler = handlers.get(name)
    if handler is None:
        return _err(f"Herramienta desconocida: {name}")
    return await handler(args)


async def _write_file(args: dict) -> str:
    raw_path = args.get("path", "")
    content = args.get("content", "")
    if not raw_path:
        return _err("Se requiere 'path'")

    target = _safe_path(raw_path)
    if target is None:
        return _err(f"Ruta no permitida (path traversal detectado): {raw_path}")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_sync, target, content)
    return _ok({"path": str(target.relative_to(WORKSPACE_ROOT)), "bytes_written": len(content.encode())})


def _write_sync(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


async def _read_file(args: dict) -> str:
    raw_path = args.get("path", "")
    if not raw_path:
        return _err("Se requiere 'path'")

    target = _safe_path(raw_path)
    if target is None:
        return _err(f"Ruta no permitida (path traversal detectado): {raw_path}")
    if not target.exists():
        return _err(f"Archivo no encontrado: {raw_path}")
    if not target.is_file():
        return _err(f"La ruta no es un archivo: {raw_path}")

    loop = asyncio.get_event_loop()
    content = await loop.run_in_executor(None, target.read_text, "utf-8")
    return _ok({"path": str(target.relative_to(WORKSPACE_ROOT)), "content": content})


async def _list_files(args: dict) -> str:
    sub = args.get("directory", "") or ""
    target = _safe_path(sub) if sub else WORKSPACE_ROOT

    if target is None:
        return _err(f"Ruta no permitida: {sub}")
    if not target.exists():
        return _err(f"Directorio no encontrado: {sub}")
    if not target.is_dir():
        return _err(f"La ruta no es un directorio: {sub}")

    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(None, _list_sync, target)
    return _ok(entries)


def _list_sync(directory: Path) -> list[dict]:
    entries = []
    for entry in sorted(directory.iterdir()):
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "size_bytes": entry.stat().st_size if entry.is_file() else None,
            "path": str(entry.relative_to(WORKSPACE_ROOT)),
        })
    return entries


async def _delete_file(args: dict) -> str:
    raw_path = args.get("path", "")
    if not raw_path:
        return _err("Se requiere 'path'")

    target = _safe_path(raw_path)
    if target is None:
        return _err(f"Ruta no permitida (path traversal detectado): {raw_path}")
    if not target.exists():
        return _err(f"Archivo no encontrado: {raw_path}")
    if not target.is_file():
        return _err(f"Solo se pueden eliminar archivos, no directorios: {raw_path}")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, target.unlink)
    return _ok({"deleted": str(target.relative_to(WORKSPACE_ROOT))})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
