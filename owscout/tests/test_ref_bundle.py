"""Ref bundles: shipping a curator's learned library to another machine."""

from pathlib import Path
from typing import Iterator

import pytest

from owscout.calibrate import build_profile
from owscout.db import Database
from owscout.errors import CaptureError
from owscout.models import Anchor, Rect
from owscout.refs import export_ref_bundle, import_ref_bundle


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "curator.sqlite3"))
    yield database
    database.close()


def _profile(w: int = 2560, h: int = 1440):
    return build_profile(
        resolution_w=w, resolution_h=h, hud_variant="default", team_size=5,
        left_strip=Rect(100, 40, 500, 60), right_strip=Rect(1960, 40, 500, 60),
        anchors=[Anchor("objective_bar", Rect(1200, 20, 160, 30))])


def _seed_curator(db: Database, tmp_path: Path) -> int:
    pid = db.save_profile(_profile())
    for i, (guid, variant) in enumerate([("h1", "a"), ("h1", "b"), ("h2", "a")]):
        img = tmp_path / f"ref{i}.png"
        img.write_bytes(b"png-bytes-%d" % i)
        db.save_ref(hero_guid=guid, profile_id=pid, state="alive",
                    image_path=str(img), phash=f"hash{i}", variant=variant)
    db.add_custom_hero("Jetpack Cat", "support")
    img = tmp_path / "ref_custom.png"
    img.write_bytes(b"png-custom")
    db.save_ref(hero_guid="custom:jetpack_cat", profile_id=pid, state="alive",
                image_path=str(img), phash="hashc", variant="a")
    return pid


def test_bundle_round_trip_between_machines(db: Database, tmp_path: Path) -> None:
    """The distribution contract: curator exports, a fresh machine calibrates at a
    DIFFERENT resolution and imports, and ends up with the full library including
    custom heroes - identity intact, images on disk."""
    _seed_curator(db, tmp_path)
    bundle = tmp_path / "refs.zip"
    n = export_ref_bundle(db, bundle)
    assert n == {"exported": 4, "skipped": 0}

    other = Database(str(tmp_path / "teammate.sqlite3"))
    try:
        pid2 = other.save_profile(_profile(w=1920, h=1080))
        got = import_ref_bundle(other, bundle, tmp_path / "refs2")
        assert got == {"added": 4, "skipped": 0}
        refs = other.get_refs(pid2)
        assert {(r.hero_guid, r.variant) for r in refs} == {
            ("h1", "a"), ("h1", "b"), ("h2", "a"), ("custom:jetpack_cat", "a")}
        assert all(Path(r.image_path).is_file() for r in refs)
        # The custom hero arrived with its deterministic guid and role.
        customs = {h.guid: h for h in other.list_custom_heroes()}
        assert customs["custom:jetpack_cat"].role == "support"
    finally:
        other.close()


def test_reimport_is_idempotent(db: Database, tmp_path: Path) -> None:
    """Re-importing an updated bundle must only add what is new - otherwise every
    library refresh would balloon the review refs."""
    _seed_curator(db, tmp_path)
    bundle = tmp_path / "refs.zip"
    export_ref_bundle(db, bundle)
    other = Database(str(tmp_path / "teammate.sqlite3"))
    try:
        other.save_profile(_profile())
        assert import_ref_bundle(other, bundle, tmp_path / "r2")["added"] == 4
        again = import_ref_bundle(other, bundle, tmp_path / "r2")
        assert again == {"added": 0, "skipped": 4}
    finally:
        other.close()


def test_import_requires_a_calibration(db: Database, tmp_path: Path) -> None:
    """Refs hang off a profile; calibration is deliberately the ONLY per-machine
    step, so importing before it must fail with a pointer, not half-import."""
    _seed_curator(db, tmp_path)
    bundle = tmp_path / "refs.zip"
    export_ref_bundle(db, bundle)
    fresh = Database(str(tmp_path / "uncalibrated.sqlite3"))
    try:
        with pytest.raises(CaptureError, match="calibrate"):
            import_ref_bundle(fresh, bundle, tmp_path / "r3")
    finally:
        fresh.close()


def test_export_skips_missing_images_but_says_so(db: Database, tmp_path: Path) -> None:
    pid = _seed_curator(db, tmp_path)
    refs = db.get_refs(pid)
    Path(refs[0].image_path).unlink()          # one image lost from disk
    n = export_ref_bundle(db, tmp_path / "refs.zip")
    assert n == {"exported": 3, "skipped": 1}
