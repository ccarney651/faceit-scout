"""First-run / progress helpers, extracted from the retired native GUI.

The desktop GUI these served (`owscout/gui.py`) was removed; the pure, tested
logic it carried was kept here rather than thrown away. Nothing else imports
this module today — it is the surviving testable core of a dead surface.
"""

from __future__ import annotations


def eta_text(done: int, total: int, elapsed: float) -> str:
    """"match 12 of 380 - about 4 min left", or without the estimate too early.

    The first few matches are a terrible sample (connection warm-up, then FACEIT's
    rate limiter settling in), so no time is quoted until there is enough history
    for the number not to swing wildly and look broken.
    """
    head = f"match {done} of {total}"
    if done < 5 or done >= total or elapsed <= 0:
        return head
    remaining = (elapsed / done) * (total - done)
    if remaining < 90:
        return f"{head} - under a minute left"
    mins = int(remaining // 60) + 1
    return f"{head} - about {mins} min left"


def setup_hint(calibrated: bool, has_codes: bool) -> str:
    """The single next step for a new user, from what's done so far. Drives the
    banner so the app always answers 'what do I do now?' - the main gap a
    non-technical first-timer hits."""
    if not calibrated:
        return ("Step 1 of 3  ·  open a replay in Overwatch (BORDERLESS/FULLSCREEN, "
                "native resolution), then click “Calibrate to my screen”.")
    if not has_codes:
        return ("Step 2 of 3  ·  click “Sync codes from FACEIT” "
                "to load the match list.")
    return ("Step 3 of 3  ·  pick a Replay below, choose the left team, then "
            "“Start hotkey capture”.  Review + Publish when done.")


def faceit_is_empty(faceit_db_path: str) -> bool:
    """True if this is a fresh machine: the faceit DB is missing or has no
    championships yet. Read-only, so it never CREATES the file (a plain connect
    would, and an empty file then looks 'present but empty' to everything else)."""
    import sqlite3
    try:
        with sqlite3.connect(f"file:{faceit_db_path}?mode=ro", uri=True) as conn:
            return conn.execute("SELECT COUNT(*) FROM championships").fetchone()[0] == 0
    except Exception:  # noqa: BLE001 - missing file / no such table -> treat as empty
        return True
