"""Tests for the filesystem MCP server (8 tests)."""

import json

import mcp_servers.filesystem.server as fs_server


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_write_and_read_roundtrip(workspace):
    content = "# Reporte de prueba\nContenido de ejemplo."
    write_res = json.loads(await fs_server._write_file({"path": "test.md", "content": content}))
    assert write_res["success"] is True
    assert write_res["data"]["bytes_written"] == len(content.encode())

    read_res = json.loads(await fs_server._read_file({"path": "test.md"}))
    assert read_res["success"] is True
    assert read_res["data"]["content"] == content


async def test_write_creates_intermediate_directories(workspace):
    result = json.loads(
        await fs_server._write_file({"path": "sub/dir/file.txt", "content": "deep file"})
    )

    assert result["success"] is True
    assert (workspace / "sub" / "dir" / "file.txt").exists()


async def test_list_files_returns_entries(workspace):
    (workspace / "a.md").write_text("a")
    (workspace / "b.md").write_text("b")

    result = json.loads(await fs_server._list_files({}))

    assert result["success"] is True
    names = [e["name"] for e in result["data"]]
    assert "a.md" in names
    assert "b.md" in names
    assert all(e["type"] == "file" for e in result["data"])


async def test_delete_file_removes_it(workspace):
    (workspace / "to_delete.txt").write_text("bye")

    del_res = json.loads(await fs_server._delete_file({"path": "to_delete.txt"}))
    assert del_res["success"] is True
    assert not (workspace / "to_delete.txt").exists()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

async def test_read_nonexistent_file_returns_error(workspace):
    result = json.loads(await fs_server._read_file({"path": "does_not_exist.md"}))

    assert result["success"] is False
    assert "no encontrado" in result["error"].lower()


async def test_write_missing_path_returns_error(workspace):
    result = json.loads(await fs_server._write_file({"path": "", "content": "data"}))

    assert result["success"] is False
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# Security — path traversal
# ---------------------------------------------------------------------------

async def test_path_traversal_write_is_blocked(workspace):
    """Any attempt to write outside workspace must be rejected."""
    for malicious in ["../../../etc/passwd", "..\\..\\windows\\system32", "sub/../../outside.txt"]:
        result = json.loads(await fs_server._write_file({"path": malicious, "content": "evil"}))
        assert result["success"] is False, f"Path traversal not blocked for: {malicious}"
        assert "traversal" in result["error"].lower() or "permitid" in result["error"].lower()


async def test_path_traversal_read_is_blocked(workspace):
    """Reading outside the sandbox must be rejected."""
    for malicious in ["../conftest.py", "../../pyproject.toml"]:
        result = json.loads(await fs_server._read_file({"path": malicious}))
        assert result["success"] is False, f"Path traversal not blocked for: {malicious}"
        assert "traversal" in result["error"].lower() or "permitid" in result["error"].lower()
