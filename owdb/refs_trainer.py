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

from .models import STATE_ALIVE, STATE_DEAD

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
    "D.Mon": "DMON",
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


# --- alive/dead marker contract ------------------------------------------------
# Each roster row is shown twice: once with the bots alive, once after they are
# killed. The workshop can only broadcast ONE integer (the "REFS <n>" counter),
# so the state is folded into it: n = 2*step + (0 alive | 1 dead). Both the .opy
# emitter and ``run_refs_autolearn`` decode it the same way, so this pair is the
# single source of truth — same role ``DONE_SENTINEL`` plays for "finished".


def encode_marker(step: int, state: str) -> int:
    """The ``REFS <n>`` counter value for a roster row in a given visual state."""
    return step * 2 + (0 if state == STATE_ALIVE else 1)


def decode_marker(marker: int) -> tuple[int, str] | None:
    """``(step, state)`` for an OCR'd counter value, or None for the done sentinel."""
    if marker == DONE_SENTINEL:
        return None
    step, rem = divmod(marker, 2)
    return step, (STATE_ALIVE if rem == 0 else STATE_DEAD)


_OPY_TEMPLATE = '''\
# GENERATED by tools/scrim_code/gen_refs_trainer.py -- do not hand-edit.
#
# A throwaway workshop code for building the owdb hero-ref library. Paste into a
# fresh custom game (Settings > orange Paste button). Each team has one open
# slot -- JOIN ONE AS A PLAYER (not spectator) before starting the match, then
# start it. Overwatch only saves a replay for a match you played in; a match
# you only spectated never gets one, so this is what makes the run reviewable
# afterwards through the replay viewer, not just live.
#
# Getting a save has turned out to need more than just being a player, or
# even an explicit "in progress" state plus an explicit end (specs/2026-09-11-
# replay-save-research.md): testing showed the replay only actually saves
# once a real Control round has played out and concluded on its own first.
# So: THE ROSTER MARCH NO LONGER STARTS THE MOMENT THE MATCH GOES LIVE. Play
# one real round -- capture speed is 500% and movement speed 200% below, so
# it's quick (the compiler accepts higher than 500%, but the in-game lobby
# slider tops out there, so it's unclear a bigger number would do anything --
# untested) -- then press INTERACT (F by default) once you want
# the dummy roster cycle to begin; REFS stays at 999 on the HUD until you do.
# The OPEN SLOT ON TEAM 2 should be filled with an AI bot (Beginner Mercy is
# fine) via the lobby's own "Add AI" feature before starting, so that round
# has someone to actually contest/cap the point -- workshop scripting has no
# action to spawn a moving/acting bot, only the stationary training dummies
# this script already uses for the roster march, so that part can't be baked
# into the code and has to be a manual lobby step each time.
#
# It sets Ilios Control (non-competitive). It spawns {nbots} dummy bots
# ({team_size} per team, one slot short of a full side) and cycles all of them
# through the roster, {nsteps} steps of {team_size}. Each step is shown twice --
# bots alive, then killed -- ~{hold:.0f}s per state, so the library gets both the
# living and the eliminated portrait.
# The "REFS <n>" counter it draws top-centre is what `owdb refs learn --auto`
# reads (n = 2*step, +1 for the dead pass).
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
            "enabledMaps": ["ilios"],
            "captureSpeed%": 500
        }}
    }},
    "heroes": {{
        "allTeams": {{
            "general": {{
                "movementSpeed%": 200
            }}
        }}
    }}
}}

globalvar step
globalvar shown
globalvar slot
globalvar SEQ
globalvar targets

rule "refs trainer: force the round live":
    @Event global
    # The spectator HUD portrait strip only renders once the match is in
    # progress. Blow straight past "assemble your heroes" and the setup phase by
    # zeroing their timers -- otherwise the bots exist but show no portrait.
    #
    # Bounded to stop the instant the match is genuinely in progress (specs/
    # 2026-09-11-replay-save-research.md): Overwatch only saves a replay for a
    # match that reaches "in progress" and then "ends" -- an unbounded reset
    # loop risks re-firing setMatchTime if setup/assembling-heroes ever reads
    # true again later (e.g. a Control round transition), which could keep
    # re-arming the very state that blocks a save. Once in progress, this rule
    # has done its job and gets out of the way for good.
    while not isGameInProgress():
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
    # A replay only actually saved once a real Control round played out and
    # concluded on its own -- forcing "in progress" then an immediate
    # Declare Match Draw wasn't enough by itself (specs/2026-09-11-replay-
    # save-research.md). So the roster march no longer starts the instant the
    # match goes live: let one real round happen first (capture speed and
    # movement speed above make that fast), then press INTERACT (F by
    # default) to begin the dummy cycle. REFS stays at {done} on the HUD the
    # whole time you're waiting to press it.
    waitUntil(hostPlayer().isHoldingButton(Button.INTERACT), 99999)
    while step < {nsteps}:
        destroyAllDummies()
        wait({settle_destroy})
        for slot in range({team_size}):
            createDummy(SEQ[step][slot], Team.1, slot, null, null)
            createDummy(SEQ[step][slot], Team.2, slot, null, null)
        wait({settle})
        shown = step * 2
        wait({hold})
        # Dead pass: kill every bot and stop it respawning, so the spectator
        # portrait holds its eliminated state (no respawn countdown) through the
        # whole capture window. Fresh bots next step are spawned from scratch.
        #
        # getAllPlayers() is EVERY player, not just the roster dummies -- it was
        # killing and permanently un-respawning the real human operator too, every
        # single step, which is why a player was stuck death-spectating almost
        # immediately into the run. Exclude the host (the operator, who started
        # the match) so only the dummy roster dies here.
        targets = getAllPlayers().filter(lambda p: p != hostPlayer())
        targets.disableRespawn()
        kill(targets, null)
        wait({kill_settle})
        shown = step * 2 + 1
        wait({hold})
        step += 1
    destroyAllDummies()
    shown = {done}
    # Force a deterministic, immediate "match ends" event instead of leaving it
    # to Control's own round timer -- Blizzard's stated save condition is "in
    # progress AND ends" (specs/2026-09-11-replay-save-research.md), and this
    # makes the "ends" half happen on our terms rather than depending on
    # however the built-in round clock behaves after everything we've done to
    # match/setup time. No-op in free-for-all modes; Control isn't one.
    wait(1)
    declareDraw()

rule "refs trainer: draw the step counter":
    @Event global
    # visibleTo is hudHeader's FIRST argument, not an unused slot -- null means
    # visible to nobody, not "everyone" (its documented default is
    # getAllPlayers()). Passing null here was a pre-existing bug that only
    # stayed hidden because this always ran pure-spectator before; it's why
    # nothing drew once a real player joined.
    hudHeader(getAllPlayers(), "REFS {{0}}".format(shown), HudPosition.TOP, 0,
              Color.WHITE, HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)

rule "refs trainer: draw match-state debug":
    @Event global
    # Diagnostic for the replay-not-saving investigation (specs/2026-09-11-
    # replay-save-research.md): the setup-phase timer reset above may be
    # keeping the match from ever reaching "in progress", which would explain
    # why no replay gets saved independent of spectator-vs-player. Watch this
    # during a test run -- if prog stays False the whole time bots are
    # cycling, or it drops back to True setup/assemble mid-run (e.g. between
    # Control rounds), that is the mechanism. Remove once confirmed either way.
    hudSubheader(getAllPlayers(), "prog={{0}} setup={{1}} assemble={{2}}".format(
                     isGameInProgress(), isInSetup(), isAssemblingHeroes()),
                 HudPosition.TOP, 1, Color.YELLOW,
                 HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)
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
    kill_settle: float = 1.0,
) -> str:
    """The full ``refs_trainer.opy`` source for a plan from :func:`plan_sequence`."""
    if not rows:
        raise ValueError("empty plan — no mappable heroes in the roster")
    nheroes = sum(len(set(r)) for r in rows[:-1]) + len(set(rows[-1]))
    return _OPY_TEMPLATE.format(
        seq_literal=_seq_literal(rows),
        nsteps=len(rows),
        team_size=team_size,
        nbots=2 * team_size,
        nheroes=nheroes,
        hold=hold,
        settle=settle,
        settle_destroy=settle_destroy,
        kill_settle=kill_settle,
        done=DONE_SENTINEL,
    )
