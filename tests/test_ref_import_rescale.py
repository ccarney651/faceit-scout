"""Importing a ref bundle rescales portraits to THIS machine's resolution.

HUD portraits scale with screen height, so a library learned at 1440p is the
wrong pixel size at 1080p - and once a ref is larger than the padded crop the
matcher loses its slide-to-align step, which is where most of the accuracy comes
from. A friend at a different resolution getting a wall of unrecognised heroes is
exactly this bug; import must rescale rather than copy verbatim.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from owscout.db import Database
from owscout.models import Rect, RoiProfile
from owscout.refs import BUNDLE_FORMAT, import_ref_bundle, phash_image


def _profile(res_w: int, res_h: int) -> RoiProfile:
    slots = {"a": [Rect(10 * i, 10, 58, 33) for i in range(5)],
             "b": [Rect(500 + 10 * i, 10, 58, 33) for i in range(5)]}
    return RoiProfile(res_w, res_h, "default", 5, slots, [])


def _make_bundle(path: Path, *, res_w: int, res_h: int, ref_w: int, ref_h: int) -> None:
    """A one-ref bundle whose portrait is ref_w x ref_h, learned at res_w x res_h."""
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, (ref_h, ref_w, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    phash = phash_image(img)
    manifest = {
        "format": BUNDLE_FORMAT,
        "tool_version": "test",
        "profile": {"resolution_w": res_w, "resolution_h": res_h,
                    "hud_variant": "default", "team_size": 5},
        "custom_heroes": {},
        "refs": [{"hero_guid": "0x02E0000000000002", "hero_name": "Reaper",
                  "state": "alive", "variant": "a", "source": "capture",
                  "phash": phash, "file": "refs/0000.png"}],
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("refs/0000.png", buf.tobytes())


def test_import_rescales_refs_to_local_resolution(tmp_path: Path) -> None:
    # Bundle learned at 1440p with a 77x44 portrait; this machine runs 1080p.
    bundle = tmp_path / "lib.zip"
    _make_bundle(bundle, res_w=2560, res_h=1440, ref_w=77, ref_h=44)
    db = Database(str(tmp_path / "ow.sqlite3"))
    pid = db.save_profile(_profile(1920, 1080))

    res = import_ref_bundle(db, bundle, tmp_path / "refs")
    assert res == {"added": 1, "skipped": 0}

    stored = db.get_refs(pid)
    assert len(stored) == 1
    h, w = cv2.imread(stored[0].image_path).shape[:2]
    # 0.75x of 77x44 -> ~58x33.
    assert (w, h) == (58, 33)
    # phash was recomputed from the rescaled image, not copied from the bundle.
    assert stored[0].phash == phash_image(cv2.imread(stored[0].image_path))
    db.close()


def test_same_resolution_imports_verbatim(tmp_path: Path) -> None:
    bundle = tmp_path / "lib.zip"
    _make_bundle(bundle, res_w=1920, res_h=1080, ref_w=58, ref_h=33)
    db = Database(str(tmp_path / "ow.sqlite3"))
    pid = db.save_profile(_profile(1920, 1080))

    import_ref_bundle(db, bundle, tmp_path / "refs")
    stored = db.get_refs(pid)
    h, w = cv2.imread(stored[0].image_path).shape[:2]
    assert (w, h) == (58, 33)          # untouched
    db.close()


def test_reimport_after_rescale_is_idempotent(tmp_path: Path) -> None:
    """Re-importing the same cross-resolution bundle must not duplicate: the
    dedup key uses the rescaled phash, computed deterministically each time."""
    bundle = tmp_path / "lib.zip"
    _make_bundle(bundle, res_w=2560, res_h=1440, ref_w=77, ref_h=44)
    db = Database(str(tmp_path / "ow.sqlite3"))
    pid = db.save_profile(_profile(1920, 1080))

    first = import_ref_bundle(db, bundle, tmp_path / "refs")
    second = import_ref_bundle(db, bundle, tmp_path / "refs")
    assert first == {"added": 1, "skipped": 0}
    assert second == {"added": 0, "skipped": 1}
    assert len(db.get_refs(pid)) == 1
    db.close()
