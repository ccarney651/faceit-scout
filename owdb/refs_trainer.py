"""``refs trainer`` — a throwaway workshop code that marches 10 dummy bots through
the whole hero roster so ``owdb refs learn --auto`` can seed the library without a
human confirming every portrait.

Two halves, one contract:

* ``tools/scrim_code/gen_refs_trainer.py`` reads the roster, calls
  :func:`plan_sequence`, and bakes the result into ``refs_trainer.opy``.
* ``owdb.refs.run_refs_autolearn`` reads the SAME roster, calls the SAME
  :func:`plan_sequence`, OCRs the ``REFS <n>`` step counter the workshop draws,
  and labels each HUD slot from ``sequence[n]``.

Nothing here touches cv2 or the game — it is the pure, testable part. The
name↔``Hero.<ENUM>`` table and the chunking rule are the only things the two
sides must agree on, so they live in one module.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

# Overwatch heroes as their in-game display name -> the OverPy ``Hero.<X>`` enum
# member. Extracted from overpy's heroKw; regenerate when a hero is added (that
# is the one edit the "reuse it for new heroes" path needs). Heroes NOT in this
# table cannot be spawned by the workshop, so ``refs learn --auto`` skips them
# and ``refs verify`` reports them for a manual ``refs learn`` pass.
_HERO_ENUM: dict[str, str] = {
    "Ana": "ANA",
    "Anran": "ANRAN",
    "Ashe": "ASHE",
    "Baptiste": "BAPTISTE",
    "Bastion": "BASTION",
    "Brigitte": "BRIGITTE",
    "Cassidy": "CASSIDY",
    "Domina": "DOMINA",
    "D.Va": "DVA",
    "Doomfist": "DOOMFIST",
    "Echo": "ECHO",
    "Emre": "EMRE",
    "Freja": "FREJA",
    "Genji": "GENJI",
    "Hanzo": "HANZO",
    "Hazard": "HAZARD",
    "Illari": "ILLARI",
    "Jetpack Cat": "JETPACK_CAT",
    "Junker Queen": "JUNKER_QUEEN",
    "Junkrat": "JUNKRAT",
    "Juno": "JUNO",
    "Kiriko": "KIRIKO",
    "Lifeweaver": "LIFEWEAVER",
    "Lúcio": "LUCIO",
    "Mauga": "MAUGA",
    "Mei": "MEI",
    "Mercy": "MERCY",
    "Mizuki": "MIZUKI",
    "Moira": "MOIRA",
    "Orisa": "ORISA",
    "Pharah": "PHARAH",
    "Ramattra": "RAMATTRA",
    "Reaper": "REAPER",
    "Reinhardt": "REINHARDT",
    "Roadhog": "ROADHOG",
    "Shion": "SHION",
    "Sierra": "SIERRA",
    "Sigma": "SIGMA",
    "Sojourn": "SOJOURN",
    "Soldier: 76": "SOLDIER",
    "Sombra": "SOMBRA",
    "Symmetra": "SYMMETRA",
    "Torbjörn": "TORBJORN",
    "Tracer": "TRACER",
    "Vendetta": "VENDETTA",
    "Venture": "VENTURE",
    "Widowmaker": "WIDOWMAKER",
    "Winston": "WINSTON",
    "Wrecking Ball": "WRECKING_BALL",
    "Wuyang": "WUYANG",
    "Zarya": "ZARYA",
    "Zenyatta": "ZENYATTA",
}


def _norm(name: str) -> str:
    """Fold a hero name to a match key: strip accents and punctuation, lowercase.

    So ``D.Va``/``DVa``, ``Soldier: 76``/``Soldier 76`` and ``Lúcio``/``Lucio``
    all collapse to the same key — the roster and the enum table spell these
    inconsistently (see the hero-roster-additions notes)."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


_NORM_TO_ENUM: dict[str, str] = {_norm(k): v for k, v in _HERO_ENUM.items()}


def hero_enum(name: str) -> str | None:
    """The OverPy ``Hero.<X>`` enum member for a roster hero name, or None if the
    workshop has no constant for it (a brand-new hero missing from ``_HERO_ENUM``,
    or an owdb custom hero)."""
    return _NORM_TO_ENUM.get(_norm(name))


def partition_roster(names: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split roster names into (mappable, unmapped), both sorted case-insensitively.

    Only the mappable set feeds :func:`plan_sequence`, so both sides of the
    contract must partition identically — hence one function."""
    uniq = sorted(set(names), key=str.lower)
    mappable = [n for n in uniq if hero_enum(n) is not None]
    unmapped = [n for n in uniq if hero_enum(n) is None]
    return mappable, unmapped


def plan_sequence(names: Iterable[str], team_size: int = 5) -> list[list[str]]:
    """The step -> hero-names table both the workshop and the tool march through.

    Roster is sorted case-insensitively and chunked into rows of ``team_size``.
    Every step shows the same heroes on BOTH teams, so each step yields a hero's
    blue ('a') and red ('b') portrait at once. The last row is padded by
    repeating its final hero to keep the workshop's 5 bot slots filled; the tool
    simply re-saves that hero's ref, which is harmless."""
    mappable, _ = partition_roster(names)
    if not mappable:
        return []
    rows: list[list[str]] = []
    for i in range(0, len(mappable), team_size):
        row = mappable[i : i + team_size]
        while len(row) < team_size:
            row.append(row[-1])
        rows.append(row)
    return rows


# --- .opy emission ---------------------------------------------------------

# The step counter the workshop draws (HudPosition.TOP) and the tool OCRs. This
# sentinel means "the roster march is finished".
DONE_SENTINEL = 999

_OPY_TEMPLATE = '''\
# GENERATED by tools/scrim_code/gen_refs_trainer.py -- do not hand-edit.
#
# A throwaway workshop code for building the owdb hero-ref library. Paste into a
# fresh custom game (Settings > orange Paste button), move to spectators, start
# the match. It sets Ilios Control (non-competitive) so the idle bots never cap
# and the round runs forever. It spawns 10 dummy bots and cycles all of them
# through the roster, {nsteps} steps of {team_size}, holding each step ~{hold:.0f}s. The
# "REFS <n>" counter it draws top-centre is what `owdb refs learn --auto` reads.
#
# Roster baked in below ({nheroes} heroes). Regenerate if the roster changes.

settings {{
    "main": {{
        "description": "owdb refs trainer -- throwaway hero-ref capture code",
        "modeName": "owdb refs trainer"
    }},
    "lobby": {{
        "spectatorSlots": 6
    }},
    "gamemodes": {{
        "control": {{
            "enableCompetitiveRules": false,
            "gamemodeStartTrigger": "immediately",
            "enabledMaps": ["ilios"]
        }}
    }}
}}

globalvar step
globalvar shown
globalvar slot
globalvar SEQ

rule "refs trainer: force the round live":
    @Event global
    # The spectator HUD portrait strip only renders once the match is in
    # progress. Blow straight past "assemble your heroes" and the setup phase by
    # zeroing their timers -- otherwise the bots exist but show no portrait.
    while true:
        if isInSetup() or isAssemblingHeroes():
            setMatchTime(0)
        wait(0.25)

rule "refs trainer: march the roster":
    @Event global
    SEQ = {seq_literal}
    step = 0
    shown = {done}
    waitUntil(isGameInProgress(), 120)
    wait(2)
    while step < {nsteps}:
        destroyAllDummies()
        wait({settle_destroy})
        for slot in range({team_size}):
            createDummy(SEQ[step][slot], Team.1, slot, null, null)
            createDummy(SEQ[step][slot], Team.2, slot, null, null)
        wait({settle})
        shown = step
        wait({hold})
        step += 1
    destroyAllDummies()
    shown = {done}

rule "refs trainer: draw the step counter":
    @Event global
    hudHeader(null, "REFS {{0}}".format(shown), HudPosition.TOP, 0,
              Color.WHITE, HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)
'''


def _seq_literal(rows: list[list[str]]) -> str:
    """Render the plan as an OverPy nested-array literal of ``Hero.<X>`` members."""
    lines = []
    for row in rows:
        members = ", ".join(f"Hero.{hero_enum(n)}" for n in row)
        lines.append(f"           [{members}]")
    body = ",\n".join(lines).lstrip()
    return f"[{body}]"


def render_opy(
    rows: list[list[str]],
    *,
    team_size: int = 5,
    hold: float = 6.0,
    settle: float = 2.0,
    settle_destroy: float = 0.5,
) -> str:
    """The full ``refs_trainer.opy`` source for a plan from :func:`plan_sequence`."""
    if not rows:
        raise ValueError("empty plan — no mappable heroes in the roster")
    nheroes = sum(len(set(r)) for r in rows[:-1]) + len(set(rows[-1]))
    return _OPY_TEMPLATE.format(
        seq_literal=_seq_literal(rows),
        nsteps=len(rows),
        team_size=team_size,
        nheroes=nheroes,
        hold=hold,
        settle=settle,
        settle_destroy=settle_destroy,
        done=DONE_SENTINEL,
    )
