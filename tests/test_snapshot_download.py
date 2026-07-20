"""The site-snapshot fast path for a fresh install.

A first run downloads the CI-built faceit DB instead of re-crawling ~2,100
rate-limited FACEIT calls. The one hard rule: this must never leave a broken or
half-written DB in place - any failure returns False so the caller falls back to
the (slow but working) keyless crawl.
"""

from __future__ import annotations

import gzip
import os
import sqlite3

import pytest

from owscout.contribute import fetch_faceit_snapshot


def _valid_db_bytes() -> bytes:
    """A minimal but real faceit DB with the tables the validator checks."""
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    try:
        con = sqlite3.connect(path)
        for t in ("matches", "games", "teams", "championships"):
            con.execute(f"CREATE TABLE {t}(id TEXT)")
            con.execute(f"INSERT INTO {t}(id) VALUES ('x')")
        con.commit()
        con.close()
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.remove(path)


class _Resp:
    def __init__(self, status: int, body: bytes):
        self.status_code = status
        self._body = body
        self.headers = {"Content-Length": str(len(body))}

    def iter_content(self, chunk_size: int = 65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]


class _Session:
    def __init__(self, resp: _Resp):
        self._resp = resp

    def get(self, url: str, timeout: float | None = None, stream: bool = False) -> _Resp:
        return self._resp


def _gz(data: bytes) -> bytes:
    return gzip.compress(data)


def test_valid_snapshot_is_installed(tmp_path) -> None:
    dest = str(tmp_path / "faceit.sqlite3")
    ok = fetch_faceit_snapshot(dest, session=_Session(_Resp(200, _gz(_valid_db_bytes()))))
    assert ok is True
    assert os.path.exists(dest)
    con = sqlite3.connect(dest)
    assert con.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1
    con.close()


def test_progress_is_reported(tmp_path) -> None:
    seen: list[tuple[int, int]] = []
    body = _gz(_valid_db_bytes())
    fetch_faceit_snapshot(str(tmp_path / "f.sqlite3"),
                          session=_Session(_Resp(200, body)),
                          progress=lambda d, t: seen.append((d, t)))
    assert seen and seen[-1][0] == len(body)          # ends at 100%
    assert all(t == len(body) for _, t in seen)       # total from Content-Length


def test_http_error_leaves_no_file(tmp_path) -> None:
    dest = str(tmp_path / "faceit.sqlite3")
    assert fetch_faceit_snapshot(dest, session=_Session(_Resp(404, b""))) is False
    assert not os.path.exists(dest)


def test_corrupt_download_is_rejected_and_leaves_no_file(tmp_path) -> None:
    """A truncated body or an HTML error page must not become the user's DB."""
    dest = str(tmp_path / "faceit.sqlite3")
    assert fetch_faceit_snapshot(dest, session=_Session(_Resp(200, b"not gzip"))) is False
    assert not os.path.exists(dest)


def test_wrong_schema_is_rejected(tmp_path) -> None:
    """A real SQLite file that isn't the faceit DB (missing tables) is refused,
    so it can't silently shadow the crawl with an unusable database."""
    empty = sqlite3.connect(":memory:")
    import tempfile
    fd, p = tempfile.mkstemp(suffix=".sqlite3"); os.close(fd)
    sqlite3.connect(p).close()  # valid but table-less SQLite file
    with open(p, "rb") as f:
        body = _gz(f.read())
    os.remove(p)
    dest = str(tmp_path / "faceit.sqlite3")
    assert fetch_faceit_snapshot(dest, session=_Session(_Resp(200, body))) is False
    assert not os.path.exists(dest)


def test_never_raises_when_offline(tmp_path) -> None:
    class Boom:
        def get(self, *a, **k):
            raise OSError("no network")

    assert fetch_faceit_snapshot(str(tmp_path / "f.sqlite3"), session=Boom()) is False
