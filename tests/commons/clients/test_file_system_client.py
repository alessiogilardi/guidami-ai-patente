"""Unit tests for commons.clients.file_system.

Covers BaseFileSystemClient security helpers, LocalFileSystemClient sync I/O,
and AsyncLocalFileSystemClient async I/O — including round-trips, error paths,
path traversal enforcement, and auto-creation of missing parent directories.
"""

from collections.abc import AsyncIterable
from pathlib import Path

import pytest

from commons.clients.file_system import (
    AsyncLocalFileSystemClient,
    BaseFileSystemClient,
    LocalFileSystemClient,
)

# ---------------------------------------------------------------------------
# TestBaseFileSystemClient
# ---------------------------------------------------------------------------


class TestBaseFileSystemClient:
    def test_resolve_path_traversal_raises_permission_error(self, tmp_path: Path) -> None:
        client = BaseFileSystemClient(tmp_path)
        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            client._resolve_path("../outside.txt")

    def test_resolve_valid_path_returns_absolute_path(self, tmp_path: Path) -> None:
        client = BaseFileSystemClient(tmp_path)
        result = client._resolve_path("some/nested/file.txt")
        assert result.is_absolute()
        assert result == (tmp_path / "some" / "nested" / "file.txt").resolve()

    def test_read_nonexistent_file_raises_file_not_found(self, tmp_path: Path) -> None:
        client = BaseFileSystemClient(tmp_path)
        with pytest.raises(FileNotFoundError):
            client._get_safe_read_path("does_not_exist.txt")

    def test_write_path_traversal_raises_permission_error(self, tmp_path: Path) -> None:
        client = BaseFileSystemClient(tmp_path)
        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            client._get_safe_write_path("../../escape.txt")

    def test_write_missing_parents_created_automatically(self, tmp_path: Path) -> None:
        client = BaseFileSystemClient(tmp_path)
        result = client._get_safe_write_path("deep/nested/dir/file.txt")
        assert result.parent.exists(), "Parent directories should have been created automatically"


# ---------------------------------------------------------------------------
# TestLocalFileSystemClient
# ---------------------------------------------------------------------------


class TestLocalFileSystemClient:
    def test_write_text_read_text_roundtrip(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        content = "Hello, world!"
        client.write_text("file.txt", content)
        assert client.read_text("file.txt") == content

    def test_utf8_preserved(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        content = "àèìòù"
        client.write_text("utf8.txt", content)
        assert client.read_text("utf8.txt") == content

    def test_write_bytes_read_bytes_roundtrip(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        data = b"\x00\x01\x02\x03binary"
        client.write_bytes("data.bin", data)
        assert client.read_bytes("data.bin") == data

    def test_write_stream_read_stream_roundtrip(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        chunks = [b"chunk1", b"chunk2", b"chunk3"]
        client.write_stream("stream.bin", iter(chunks))
        collected = b"".join(client.read_stream("stream.bin", chunk_size=6))
        assert collected == b"".join(chunks)

    def test_write_creates_missing_parent_dirs(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        client.write_text("a/b/c/file.txt", "content")
        assert (tmp_path / "a" / "b" / "c" / "file.txt").exists()

    def test_overwrite_existing_file(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        client.write_text("file.txt", "original")
        client.write_text("file.txt", "overwritten")
        assert client.read_text("file.txt") == "overwritten"

    def test_exists_returns_none_for_existing_file(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        client.write_text("present.txt", "here")
        result = client.exists_or_raise("present.txt")
        assert result is None

    def test_exists_raises_file_not_found_for_missing_file(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        with pytest.raises(FileNotFoundError):
            client.exists_or_raise("ghost.txt")

    def test_exists_raises_permission_error_on_traversal_before_not_found(
        self, tmp_path: Path
    ) -> None:
        client = LocalFileSystemClient(tmp_path)
        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            client.exists_or_raise("../escaped.txt")

    def test_list_files_sorted(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        (tmp_path / "dir").mkdir()
        client.write_text("dir/b.json", "{}")
        client.write_text("dir/a.json", "{}")
        client.write_text("dir/c.json", "{}")

        result = client.list_files("dir")

        assert [p.name for p in result] == ["a.json", "b.json", "c.json"]

    def test_list_files_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        assert client.list_files("does_not_exist") == []

    def test_list_files_rejects_traversal(self, tmp_path: Path) -> None:
        client = LocalFileSystemClient(tmp_path)
        with pytest.raises(PermissionError, match="Path traversal attempt detected"):
            client.list_files("../outside")


# ---------------------------------------------------------------------------
# TestAsyncLocalFileSystemClient
# ---------------------------------------------------------------------------


class TestAsyncLocalFileSystemClient:
    async def test_write_text_read_text_roundtrip(self, tmp_path: Path) -> None:
        client = AsyncLocalFileSystemClient(tmp_path)
        content = "Hello async world!"
        await client.write_text("file.txt", content)
        assert await client.read_text("file.txt") == content

    async def test_utf8_preserved(self, tmp_path: Path) -> None:
        client = AsyncLocalFileSystemClient(tmp_path)
        content = "àèìòù"
        await client.write_text("utf8.txt", content)
        assert await client.read_text("utf8.txt") == content

    async def test_write_bytes_read_bytes_roundtrip(self, tmp_path: Path) -> None:
        client = AsyncLocalFileSystemClient(tmp_path)
        data = b"\x00\x01\x02binary"
        await client.write_bytes("data.bin", data)
        assert await client.read_bytes("data.bin") == data

    async def test_write_stream_read_stream_roundtrip(self, tmp_path: Path) -> None:
        client = AsyncLocalFileSystemClient(tmp_path)
        chunks = [b"async1", b"async2", b"async3"]

        async def _source() -> AsyncIterable[bytes]:
            for chunk in chunks:
                yield chunk

        await client.write_stream("stream.bin", _source())
        collected = b""
        async for chunk in client.read_stream("stream.bin", chunk_size=6):
            collected += chunk
        assert collected == b"".join(chunks)

    async def test_write_creates_missing_parent_dirs(self, tmp_path: Path) -> None:
        client = AsyncLocalFileSystemClient(tmp_path)
        await client.write_text("x/y/z/file.txt", "async content")
        assert (tmp_path / "x" / "y" / "z" / "file.txt").exists()

    async def test_exists_returns_none_for_existing_file(self, tmp_path: Path) -> None:
        client = AsyncLocalFileSystemClient(tmp_path)
        await client.write_text("present.txt", "here")
        result = await client.exists_or_raise("present.txt")
        assert result is None

    async def test_exists_raises_file_not_found_for_missing_file(self, tmp_path: Path) -> None:
        client = AsyncLocalFileSystemClient(tmp_path)
        with pytest.raises(FileNotFoundError):
            await client.exists_or_raise("ghost.txt")

    async def test_list_files_matches_sync(self, tmp_path: Path) -> None:
        sync_client = LocalFileSystemClient(tmp_path)
        (tmp_path / "dir").mkdir()
        sync_client.write_text("dir/b.json", "{}")
        sync_client.write_text("dir/a.json", "{}")

        async_client = AsyncLocalFileSystemClient(tmp_path)
        result = await async_client.list_files("dir")

        assert [p.name for p in result] == sorted(p.name for p in sync_client.list_files("dir"))
