"""Integrity checks (SPEC §9, build step 6).

These are the difference between a scouting tool and one that quietly lies to
you. Two matter most and are built here:

* §9.1 — a slot that resolves to a *banned* hero is provably wrong (a banned
  hero cannot be on the field), so it signals a stale ROI profile. It is a
  better HUD-drift detector than the anchors because it is a logical
  impossibility, not a similarity score.
* §9.2 — the map OCR'd from the replay not matching ``games.map_name`` for that
  code exposes faceit-sync's ``demoURLs`` index-misalignment bug. owscout can
  see the map; faceit-sync cannot. This makes owscout a validator for it.

The comparison/aggregation logic is pure and unit-tested; the OCR that feeds
§9.2 is a runtime concern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, Sequence

# Fail a capture run if more than this fraction of resolved slots land on a
# banned hero — a low rate is noise, a high rate means the ROIs have drifted
# (SPEC §9.1).
BAN_HIT_FAIL_RATE = 0.02

# OCR is imprecise; accept a map-name match above this normalised-similarity.
MAP_NAME_MATCH_RATIO = 0.85


def banned_hero_hits(
    slot_guids: Sequence[Optional[str]], banned_guids: set[str]
) -> list[str]:
    """The banned hero_guids that (wrongly) appear among resolved slots. A
    non-empty result means the ROI profile is likely stale (SPEC §9.1)."""
    return [g for g in slot_guids if g is not None and g in banned_guids]


def over_ban_hit_threshold(
    banned_hits: int, resolved_slots: int, rate: float = BAN_HIT_FAIL_RATE
) -> bool:
    """True if the banned-hero-hit rate exceeds ``rate`` (SPEC §9.1). With no
    resolved slots there is nothing to judge, so it is not over threshold."""
    if resolved_slots <= 0:
        return False
    return (banned_hits / resolved_slots) > rate


def _normalise_map(name: str) -> str:
    """Lower-case, drop punctuation/whitespace so OCR quirks (e.g. "King's Row"
    vs "kings row") don't cause false mismatches."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def map_names_match(ocr_name: str, expected_name: str, ratio: float = MAP_NAME_MATCH_RATIO) -> bool:
    """Whether an OCR'd map name matches the expected faceit map (SPEC §9.2).
    Exact after normalisation, or fuzzily above ``ratio`` to tolerate OCR noise."""
    a, b = _normalise_map(ocr_name), _normalise_map(expected_name)
    if not a or not b:
        return False
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= ratio


@dataclass(frozen=True)
class VerifyCodesRow:
    """One captured instance's map-verification outcome for §9.2 reporting."""

    match_id: str
    game_no: int
    map_verified: Optional[int]     # 1 ok, 0 mismatch, None not checked
    match_has_restart: bool         # does the match contain a restart shell?


@dataclass(frozen=True)
class VerifyCodesReport:
    total: int
    checked: int
    mismatches: int
    mismatch_rate: float
    mismatches_in_restart_matches: int
    mismatches_in_clean_matches: int
    # The §9.2 signal: mismatches clustering on post-restart matches confirms the
    # demoURLs index-assignment bug in sync.py.
    clusters_on_restarts: bool


def verify_codes_report(rows: Sequence[VerifyCodesRow]) -> VerifyCodesReport:
    """Aggregate captured instances into the §9.2 mismatch report.

    ``clusters_on_restarts`` is True when mismatches exist and every one falls in
    a match that contains a restart shell — the fingerprint of the index bug."""
    checked = [r for r in rows if r.map_verified is not None]
    mism = [r for r in checked if r.map_verified == 0]
    in_restart = sum(1 for r in mism if r.match_has_restart)
    in_clean = len(mism) - in_restart
    return VerifyCodesReport(
        total=len(rows),
        checked=len(checked),
        mismatches=len(mism),
        mismatch_rate=(len(mism) / len(checked)) if checked else 0.0,
        mismatches_in_restart_matches=in_restart,
        mismatches_in_clean_matches=in_clean,
        clusters_on_restarts=bool(mism) and in_clean == 0,
    )
