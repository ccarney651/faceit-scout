"""docs/capture/refs.json builder: alive AND dead crops reach the browser matcher.

The engine matcher (docs/capture/engine/refs.js `bestMatch`) takes the best
score across every ref with the matching team variant, so a dead/dimmed replay
portrait matches a dead exemplar. The builder therefore has to stop filtering the
DB down to `state='alive'` and emit one entry per (hero, variant, state) — same
`{n,g,v,d}` shape, no new field.
"""

from __future__ import annotations

import sqlite3

from tools.build_capture_refs import ref_entries, select_ref_rows


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE hero_refs (
            hero_guid TEXT, profile_id INTEGER, state TEXT,
            variant TEXT, image_path TEXT, source TEXT
        );
        """
    )
    return conn


def test_select_ref_rows_returns_both_states() -> None:
    conn = _db()
    conn.executemany(
        "INSERT INTO hero_refs VALUES (?,4,?,?,?, 'capture')",
        [
            ("g-ana", "alive", "a", "ana_alive.png"),
            ("g-ana", "dead", "a", "ana_dead.png"),
            ("g-ana", "alive", "b", "ana_alive_b.png"),
        ],
    )
    rows = select_ref_rows(conn, profile_id=4)
    assert sorted((g, s, v) for g, v, s, _ in rows) == [
        ("g-ana", "alive", "a"),
        ("g-ana", "alive", "b"),
        ("g-ana", "dead", "a"),
    ]


def test_select_ref_rows_keeps_review_exemplars() -> None:
    conn = _db()
    conn.executemany(
        "INSERT INTO hero_refs VALUES ('g-ana',4,'alive','a',?,?)",
        [("canon.png", "capture"), ("harvested.png", "review")],
    )
    rows = select_ref_rows(conn, profile_id=4)
    assert {r[3] for r in rows} == {"canon.png", "harvested.png"}


def test_select_ref_rows_scopes_to_the_profile() -> None:
    conn = _db()
    conn.executemany(
        "INSERT INTO hero_refs VALUES (?,?,?,?,?, 'capture')",
        [
            ("g-ana", 4, "alive", "a", "keep.png"),
            ("g-ana", 3, "alive", "a", "other_profile.png"),
        ],
    )
    rows = select_ref_rows(conn, profile_id=4)
    assert [r[3] for r in rows] == ["keep.png"]


def test_ref_entries_keeps_alive_and_dead_under_one_variant() -> None:
    rows = [
        ("g-ana", "a", "alive", "alive.png"),
        ("g-ana", "a", "dead", "dead.png"),
    ]
    entries = ref_entries(rows, {"g-ana": "Ana"}, lambda p: b"x" * (64 * 36))
    assert [(e["n"], e["v"]) for e in entries] == [("Ana", "a"), ("Ana", "a")]
    assert all(e["g"] == "g-ana" for e in entries)
    assert entries[0]["d"] != "" and "d" in entries[1]


def test_ref_entries_skips_unreadable_images() -> None:
    rows = [
        ("g-ana", "a", "alive", "ok.png"),
        ("g-ana", "a", "dead", "gone.png"),
    ]

    def loader(path: str) -> bytes | None:
        return b"x" * (64 * 36) if path == "ok.png" else None

    entries = ref_entries(rows, {"g-ana": "Ana"}, loader)
    assert len(entries) == 1


def test_ref_entries_names_unknown_guid_from_its_prefix() -> None:
    rows = [("0x02E0000000000542", "a", "alive", "x.png")]
    entries = ref_entries(rows, {}, lambda p: b"x" * (64 * 36))
    assert entries[0]["n"] == "0x02E0"
