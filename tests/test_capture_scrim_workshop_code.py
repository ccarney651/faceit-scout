"""The capture page must name the workshop code the tool depends on.

`B44BZ`, and the fact that hero bans and scoreboard stats are readable ONLY in a
lobby running it, lived in tools/scrim_code/README.md and ARCHITECTURE.md and
nowhere an operator would see them. In a stock ScrimTime lobby the ban read
abstains with "could not read the ban row", which reads as a tool bug rather
than as the wrong lobby; ScrimTime Lite has no spectator scoreboard at all, so
it can never support the stats read either.

The page also carries a SEPARATE warning about FACEIT *replay* codes
(refuseIfLeagueCode). Same word, opposite meaning, opposite remedy - so the two
have to be worded so an operator can tell them apart.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "docs" / "capture" / "scrim.html"
README = ROOT / "tools" / "scrim_code" / "README.md"


def _html() -> str:
    return APP.read_text(encoding="utf-8")


def test_the_share_code_the_readme_mints_is_the_one_the_page_names() -> None:
    """One source of truth: if the code is re-minted, this test fails loudly."""
    minted = re.search(r"\*\*`([A-Z0-9]{5})`\*\* — minted", README.read_text(encoding="utf-8"))
    assert minted, "the README no longer states a minted share code in the expected form"
    assert minted.group(1) in _html(), (
        f"scrim.html does not name the current share code {minted.group(1)}"
    )


def test_the_page_says_bans_and_stats_need_this_lobby() -> None:
    html = _html().lower()
    assert "workshop code" in html, "the page never uses the phrase 'workshop code'"
    assert "scrimtime" in html, "the page does not mention the modes it cannot read"


def test_the_workshop_code_is_not_confusable_with_a_replay_code() -> None:
    """Both warnings exist on this page; they must not both just say 'code'."""
    html = _html()
    assert "workshop code" in html.lower()
    assert "replay code" in html.lower(), (
        "the league-code block must say 'replay code' so it cannot be read as "
        "the workshop code the scoreboard read depends on"
    )
