"""The gate's constraint logic (SPEC §8.1, revised): ban exclusion, ult-overlay
masking, full-set matching with role read from the matched hero, composition
consistency, confidence floor. Exercised without OpenCV via injected primitives.

The HUD slot order is not role-fixed (operator-confirmed), so there is no
per-slot role pre-assignment — role comes from whatever hero wins each slot."""

from __future__ import annotations

from owscout.match import (
    composition_consistent,
    face_subrect,
    format_matches,
    match_frame,
    reduce_candidates,
    role_counts,
)
from owscout.models import Rect, HeroRef

# hero_guid -> role, and a small ref library (alive + dead per hero).
ROLES = {"tank": "Tank", "dps1": "Damage", "dps2": "Damage", "sup1": "Support", "sup2": "Support"}
NAMES = {g: g.upper() for g in ROLES}


def _refs() -> list[HeroRef]:
    refs: list[HeroRef] = []
    for guid in ROLES:
        for state in ("alive", "dead"):
            refs.append(HeroRef(
                hero_guid=guid, profile_id=1, state=state,
                image_path=f"{guid}_{state}.png", phash="0" * 16, source="capture",
            ))
    return refs


# --- role composition (sanity check, not a filter) ---------------------------


def test_role_counts() -> None:
    team = ["Support", "Damage", "Tank", "Support", "Damage"]
    assert role_counts(team) == {"Tank": 1, "Damage": 2, "Support": 2}


def test_role_counts_ignores_unlabelled() -> None:
    assert role_counts(["Tank", "None", "Damage", None, "Support"]) == {  # type: ignore[list-item]
        "Tank": 1, "Damage": 1, "Support": 1,
    }


def test_composition_consistent_true_when_matches() -> None:
    matched = ["Tank", "Damage", "Damage", "Support", "Support"]
    team = ["Support", "Damage", "Tank", "Support", "Damage"]
    assert composition_consistent(matched, team) is True


def test_composition_inconsistent_when_roles_differ() -> None:
    matched = ["Tank", "Tank", "Damage", "Support", "Support"]  # 2 tanks
    team = ["Tank", "Damage", "Damage", "Support", "Support"]
    assert composition_consistent(matched, team) is False


def test_composition_true_when_incomplete() -> None:
    # Any unresolved (None) slot -> nothing to contradict.
    matched = ["Tank", None, "Damage", "Support", "Support"]
    team = ["Tank", "Damage", "Damage", "Support", "Support"]
    assert composition_consistent(matched, team) is True


# --- face_subrect (ult-overlay mask) -----------------------------------------


def test_face_subrect_keeps_right_portion() -> None:
    # 141px cell (measured pitch), 55% overlay -> 78px cut, 63px face on the right.
    face = face_subrect(Rect(57, 95, 141, 55), 0.55)
    assert face == Rect(57 + 78, 95, 141 - 78, 55)
    assert face.y == 95 and face.h == 55  # vertical unchanged


def test_face_subrect_default_fraction() -> None:
    face = face_subrect(Rect(0, 0, 100, 50))
    assert face.x == 55 and face.w == 45


def test_face_subrect_rejects_bad_fraction() -> None:
    import pytest
    with pytest.raises(ValueError):
        face_subrect(Rect(0, 0, 100, 50), 1.0)


# --- reduce_candidates -------------------------------------------------------


def test_ban_excludes_hero_everywhere() -> None:
    cands = reduce_candidates(
        _refs(), state="alive", expected_role=None,
        banned_guids={"dps1"}, hero_roles=ROLES,
    )
    guids = {c.hero_guid for c in cands}
    assert "dps1" not in guids and "dps2" in guids


def test_role_filter_available_but_optional() -> None:
    # reduce_candidates still supports an explicit role filter (used by a future
    # assignment pass); the default match path passes expected_role=None.
    cands = reduce_candidates(
        _refs(), state="alive", expected_role="Tank",
        banned_guids=set(), hero_roles=ROLES,
    )
    assert {c.hero_guid for c in cands} == {"tank"}


def test_full_set_when_no_role_filter() -> None:
    cands = reduce_candidates(
        _refs(), state="alive", expected_role=None,
        banned_guids=set(), hero_roles=ROLES,
    )
    assert {c.hero_guid for c in cands} == set(ROLES)  # all 5 heroes


def test_state_filter() -> None:
    cands = reduce_candidates(
        _refs(), state="dead", expected_role=None,
        banned_guids=set(), hero_roles=ROLES,
    )
    assert all(c.state == "dead" for c in cands)
    assert {c.hero_guid for c in cands} == set(ROLES)


# --- match_frame (injected primitives) ---------------------------------------


class _FakeFrame:
    """Slicing returns the (y, x) top-left as a stand-in crop token."""

    def __getitem__(self, key: tuple[slice, slice]) -> tuple[int, int]:
        ys, xs = key
        return (ys.start, xs.start)


def _crop(frame: _FakeFrame, rect: Rect) -> tuple[int, int]:
    return frame[rect.y : rect.y + rect.h, rect.x : rect.x + rect.w]


def _slots() -> list[Rect]:
    # 5 slots at distinct x offsets so crops are distinguishable.
    return [Rect(x=i * 100, y=0, w=90, h=90) for i in range(5)]


def test_match_frame_reads_role_from_matched_hero() -> None:
    slots = _slots()
    # Truth: slot i should resolve to this guid (order is arbitrary — not role-fixed).
    truth = ["sup1", "tank", "dps2", "sup2", "dps1"]

    def score(crop: tuple[int, int], ref: HeroRef) -> float:
        slot_i = crop[1] // 100
        return 0.95 if ref.hero_guid == truth[slot_i] and ref.state == "alive" else 0.10

    results = match_frame(
        _FakeFrame(), slots, _refs(), ROLES, set(), NAMES,
        confidence_floor=0.80, crop_fn=_crop, score_fn=score,
    )
    assert [r.hero_guid for r in results] == truth
    assert all(r.resolved for r in results)
    # Role is read off the matched hero, not the slot position.
    assert [r.matched_role for r in results] == [
        "Support", "Tank", "Damage", "Support", "Damage",
    ]
    # Candidate count is distinct heroes (both states collapse), no role filter.
    assert [r.candidates for r in results] == [5, 5, 5, 5, 5]


def test_bans_shrink_candidate_set() -> None:
    slots = _slots()[:1]
    results = match_frame(
        _FakeFrame(), slots, _refs(), ROLES, {"dps1", "sup2"}, NAMES,
        confidence_floor=0.80, crop_fn=_crop,
        score_fn=lambda _c, r: 0.9 if r.hero_guid == "tank" else 0.0,
    )
    assert results[0].candidates == 3  # 5 heroes - 2 bans (distinct heroes)


def test_below_floor_left_unresolved() -> None:
    results = match_frame(
        _FakeFrame(), _slots(), _refs(), ROLES, set(), NAMES,
        confidence_floor=0.80, crop_fn=_crop,
        score_fn=lambda _c, _r: 0.50,  # all low
    )
    assert all(not r.resolved for r in results)
    assert all(r.hero_guid is None and r.matched_role is None for r in results)


def test_state_comes_from_winning_ref() -> None:
    # A dead hero is still on the field: its dead ref wins -> hero identified,
    # state reported as 'dead', hero still counts in the comp.
    slots = _slots()[:1]

    def score(crop: tuple[int, int], ref: HeroRef) -> float:
        return 0.95 if ref.hero_guid == "tank" and ref.state == "dead" else 0.10

    results = match_frame(
        _FakeFrame(), slots, _refs(), ROLES, set(), NAMES,
        confidence_floor=0.80, crop_fn=_crop, score_fn=score,
    )
    assert results[0].hero_guid == "tank"   # detected regardless of state
    assert results[0].state == "dead"
    assert results[0].resolved


def test_format_matches_smoke() -> None:
    slots = _slots()[:1]
    results = match_frame(
        _FakeFrame(), slots, _refs(), ROLES, set(), NAMES,
        confidence_floor=0.80, crop_fn=_crop,
        score_fn=lambda _c, r: 0.9 if r.hero_guid == "tank" else 0.0,
    )
    out = format_matches(results)
    assert "resolved 1/1 slots" in out and "TANK" in out
