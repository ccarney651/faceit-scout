"""refs verify set logic, hero_refs persistence, and read-only faceit access."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from owscout.db import Database
from owscout.faceit import connect_ro, load_heroes
from owscout.models import FaceitHero, HeroRef
from owscout.refs import find_close_pairs, find_missing


# --- fixtures ----------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "owscout.sqlite3"))
    yield database
    database.close()


def _make_faceit_db(path: Path) -> str:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        "CREATE TABLE heroes (guid TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT);"
    )
    conn.executemany(
        "INSERT INTO heroes (guid, name, role) VALUES (?, ?, ?)",
        [("g-winston", "Winston", "Tank"),
         ("g-ana", "Ana", "Support"),
         ("g-tracer", "Tracer", "Damage")],
    )
    conn.commit()
    conn.close()
    return str(path)


def _ref(guid: str, state: str, phash: str, source: str = "capture") -> HeroRef:
    return HeroRef(
        hero_guid=guid, profile_id=1, state=state,
        image_path=f"{guid}_{state}.png", phash=phash, source=source,
    )


# --- read-only faceit access -------------------------------------------------


def test_load_heroes(tmp_path: Path) -> None:
    fpath = _make_faceit_db(tmp_path / "faceit.sqlite3")
    with connect_ro(fpath) as conn:
        heroes = load_heroes(conn)
    assert [h.name for h in heroes] == ["Ana", "Tracer", "Winston"]  # ordered by name


def test_faceit_connection_is_read_only(tmp_path: Path) -> None:
    fpath = _make_faceit_db(tmp_path / "faceit.sqlite3")
    with connect_ro(fpath) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO heroes (guid, name) VALUES ('x', 'X')")


def test_missing_faceit_db_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        connect_ro(str(tmp_path / "nope.sqlite3"))


# --- find_missing ------------------------------------------------------------


def test_find_missing_reports_gaps() -> None:
    heroes = [FaceitHero("g-winston", "Winston", "Tank"),
              FaceitHero("g-ana", "Ana", "Support")]
    refs = [_ref("g-winston", "alive", "0" * 16),
            _ref("g-winston", "dead", "1" * 16)]
    missing = find_missing(heroes, refs)
    assert missing == {"g-ana": ["alive", "dead"]}


def test_find_missing_empty_when_complete() -> None:
    heroes = [FaceitHero("g-ana", "Ana", "Support")]
    refs = [_ref("g-ana", "alive", "0" * 16), _ref("g-ana", "dead", "f" * 16)]
    assert find_missing(heroes, refs) == {}


def test_find_missing_partial_state() -> None:
    heroes = [FaceitHero("g-ana", "Ana", "Support")]
    refs = [_ref("g-ana", "alive", "0" * 16)]
    assert find_missing(heroes, refs) == {"g-ana": ["dead"]}


# --- find_close_pairs --------------------------------------------------------


def test_close_pairs_flags_different_heroes() -> None:
    refs = [_ref("g-ana", "alive", "0000000000000000"),
            _ref("g-tracer", "alive", "0000000000000001")]  # distance 1
    pairs = find_close_pairs(refs, threshold=6)
    assert len(pairs) == 1 and pairs[0].distance == 1


def test_close_pairs_ignores_same_hero() -> None:
    # A hero's own alive/dead crops are expected to be similar — not a hazard.
    refs = [_ref("g-ana", "alive", "0000000000000000"),
            _ref("g-ana", "dead", "0000000000000001")]
    assert find_close_pairs(refs, threshold=6) == []


def test_close_pairs_respects_threshold() -> None:
    refs = [_ref("g-ana", "alive", "0" * 16),
            _ref("g-tracer", "alive", "f" * 16)]  # distance 64
    assert find_close_pairs(refs, threshold=6) == []


def test_close_pairs_sorted_closest_first() -> None:
    refs = [
        _ref("g-a", "alive", "0000000000000000"),
        _ref("g-b", "alive", "0000000000000003"),  # d=2 from a
        _ref("g-c", "alive", "0000000000000001"),  # d=1 from a
    ]
    dists = [p.distance for p in find_close_pairs(refs, threshold=6)]
    assert dists == sorted(dists)


# --- hero_refs persistence ---------------------------------------------------


def _profile(db: Database) -> int:
    from owscout.calibrate import build_profile
    from owscout.models import Rect
    return db.save_profile(build_profile(
        resolution_w=2560, resolution_h=1440, hud_variant="default", team_size=5,
        left_strip=Rect(0, 0, 500, 60), right_strip=Rect(1000, 0, 500, 60), anchors=[],
    ))


def test_save_and_get_refs(db: Database) -> None:
    pid = _profile(db)
    db.save_ref(hero_guid="g-ana", profile_id=pid, state="alive",
                image_path="a.png", phash="0" * 16)
    db.save_ref(hero_guid="g-ana", profile_id=pid, state="dead",
                image_path="d.png", phash="f" * 16)
    refs = db.get_refs(pid)
    assert {r.state for r in refs} == {"alive", "dead"}
    assert db.get_refs(pid, state="alive")[0].image_path == "a.png"


def test_capture_ref_is_idempotent(db: Database) -> None:
    pid = _profile(db)
    db.save_ref(hero_guid="g-ana", profile_id=pid, state="alive",
                image_path="old.png", phash="0" * 16)
    db.save_ref(hero_guid="g-ana", profile_id=pid, state="alive",
                image_path="new.png", phash="1" * 16)
    refs = db.get_refs(pid, state="alive")
    assert len(refs) == 1
    assert refs[0].image_path == "new.png"  # replaced, not duplicated


def test_review_refs_accumulate(db: Database) -> None:
    pid = _profile(db)
    db.save_ref(hero_guid="g-ana", profile_id=pid, state="alive",
                image_path="cap.png", phash="0" * 16, source="capture")
    db.save_ref(hero_guid="g-ana", profile_id=pid, state="alive",
                image_path="rev1.png", phash="1" * 16, source="review")
    db.save_ref(hero_guid="g-ana", profile_id=pid, state="alive",
                image_path="rev2.png", phash="2" * 16, source="review")
    assert len(db.get_refs(pid, state="alive")) == 3
    assert len(db.get_refs(pid, source="review")) == 2
