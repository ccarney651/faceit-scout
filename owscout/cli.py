"""Command-line interface for owscout.

Only ``owscout calibrate`` exists so far (SPEC 13 step 1). Later subcommands
(``refs``, ``capture``, ``codes``, ``scout``, ``comps``, ``export``, ``review``)
land with their build-order steps.

DB path config mirrors faceit-sync (SPEC 3):
  own DB:    ``--db``        -> ``$OWSCOUT_DB`` -> ``owscout.sqlite3``
  faceit DB: ``--faceit-db`` -> ``$FACEIT_DB``  -> ``faceit.sqlite3``
Calibration needs only the own DB; ``--faceit-db`` is accepted now for a stable
interface across the tool.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional, Sequence, cast

from dotenv import load_dotenv

from . import __version__
from .calibrate import default_frame_dir, run_calibration
from .capture import DEFAULT_WRITE_INTERVAL_MS, run_capture, run_hotkey_capture
from .errors import CaptureError
from .context import AmbiguousCode, CodeNotFound, derive_code_context, format_context
from .derive import (
    DEFAULT_MIN_SAMPLES,
    aggregate_comps,
    modal_comp,
    player_pool,
    render_rate,
    synthetic_comp,
)
from .integrity import verify_codes_report
from .db import Database
from .match import DEFAULT_CONFIDENCE_FLOOR, run_match
from .models import DEFAULT_DIVISION, DEFAULT_TEAM_SIZE, REF_STATES, SIDE_LEFT
from .refs import (
    DEFAULT_CLOSE_THRESHOLD,
    default_refs_dir,
    run_refs_capture,
    run_refs_from_frame,
    run_refs_from_sheet,
    run_refs_learn,
    run_refs_verify,
)

log = logging.getLogger("owscout")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else os.getenv("OWSCOUT_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _db_path(args: argparse.Namespace) -> str:
    return args.db or os.getenv("OWSCOUT_DB", "owscout.sqlite3")


def _faceit_db_path(args: argparse.Namespace) -> str:
    return args.faceit_db or os.getenv("FACEIT_DB", "faceit.sqlite3")


def cmd_calibrate(args: argparse.Namespace) -> int:
    db_path = _db_path(args)
    frame_dir = args.frame_dir or default_frame_dir(db_path)
    try:
        with Database(db_path) as db:
            run_calibration(
                db,
                hud_variant=args.hud_variant,
                team_size=args.team_size,
                frame_dir=frame_dir,
                dry_run=args.dry_run,
            )
    except CaptureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (RuntimeError, ValueError) as exc:
        # Empty ROI selection, too-small strip, etc. - operator error, not a bug.
        print(f"calibration aborted: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_refs_capture(args: argparse.Namespace) -> int:
    db_path = _db_path(args)
    refs_dir = args.refs_dir or default_refs_dir(db_path)
    states = (args.state,) if args.state != "both" else REF_STATES
    try:
        with Database(db_path) as db:
            run_refs_capture(
                db,
                _faceit_db_path(args),
                hud_variant=args.hud_variant,
                side=args.side,
                slot=args.slot,
                states=states,
                only=args.only,
                refs_dir=refs_dir,
                dry_run=args.dry_run,
            )
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_refs_from_frame(args: argparse.Namespace) -> int:
    db_path = _db_path(args)
    refs_dir = args.refs_dir or default_refs_dir(db_path)
    try:
        with Database(db_path) as db:
            run_refs_from_frame(
                db,
                _faceit_db_path(args),
                hud_variant=args.hud_variant,
                refs_dir=refs_dir,
                state=args.state,
                dry_run=args.dry_run,
            )
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_refs_from_sheet(args: argparse.Namespace) -> int:
    db_path = _db_path(args)
    refs_dir = args.refs_dir or default_refs_dir(db_path)
    try:
        with Database(db_path) as db:
            run_refs_from_sheet(
                db,
                _faceit_db_path(args),
                args.image,
                hud_variant=args.hud_variant,
                refs_dir=refs_dir,
                dry_run=args.dry_run,
            )
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_refs_learn(args: argparse.Namespace) -> int:
    db_path = _db_path(args)
    refs_dir = args.refs_dir or default_refs_dir(db_path)
    try:
        with Database(db_path) as db:
            run_refs_learn(
                db,
                _faceit_db_path(args),
                hud_variant=args.hud_variant,
                refs_dir=refs_dir,
                state=args.state,
                calibrate_slot=args.calibrate_slot,
                dry_run=args.dry_run,
            )
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_refs_verify(args: argparse.Namespace) -> int:
    try:
        with Database(_db_path(args)) as db:
            return run_refs_verify(
                db,
                _faceit_db_path(args),
                hud_variant=args.hud_variant,
                close_threshold=args.close_threshold,
            )
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def cmd_match(args: argparse.Namespace) -> int:
    try:
        with Database(_db_path(args)) as db:
            results = run_match(
                db,
                _faceit_db_path(args),
                frame_path=args.frame,
                match_id=args.match_id,
                game_no=args.game_no,
                team=args.team,
                side=args.side,
                hud_variant=args.hud_variant,
                confidence_floor=args.confidence_floor,
            )
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # Gate signal: non-zero if any slot failed to resolve.
    return 0 if all(r.resolved for r in results) else 1


def cmd_capture(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    require_division = None if args.division == "all" else args.division
    try:
        with Database(_db_path(args)) as db:
            if args.hotkey:
                run_hotkey_capture(
                    db, faceit_path,
                    demo_code=args.code, hud_variant=args.hud_variant,
                    side_a_team=args.side_a_team, hotkey=args.hotkey,
                    confidence_floor=args.confidence_floor,
                    require_division=require_division,
                    debug_dir=args.debug_dir, dry_run=args.dry_run,
                )
            else:
                run_capture(
                    db, faceit_path,
                    demo_code=args.code, hud_variant=args.hud_variant,
                    speed=args.speed, fps=args.fps, duration_s=args.duration,
                    side_a_team=args.side_a_team,
                    write_interval_ms=args.write_interval_ms,
                    confidence_floor=args.confidence_floor,
                    require_division=require_division, dry_run=args.dry_run,
                )
    except (CaptureError, CodeNotFound, AmbiguousCode, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _short_date(s: Optional[str]) -> str:
    return (s or "")[:10] or "?"


def cmd_codes_list(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    with Database(_db_path(args)) as db:
        rows = db.list_codes(
            faceit_path, team=args.team, uncaptured=args.uncaptured,
            include_wiped=args.include_wiped,
            division=None if args.division == "all" else args.division,
            limit=args.limit,
        )
    if not rows:
        hint = "" if args.include_wiped else " (all stored codes may pre-date the last wipe - try --include-wiped)"
        print(f"no capturable codes{hint}")
        return 0
    print(f"{'code':<8} {'date':<10} {'map':<14} {'stat':<5} matchup")
    print("-" * 64)
    for r in rows:
        flag = "done" if r.captured else ("dead" if r.wiped else "new")
        opp = f"{r.team_a or '?'} vs {r.team_b or '?'}"
        print(f"{r.demo_code:<8} {_short_date(r.finished_at):<10} "
              f"{(r.map_name or '?'):<14} {flag:<5} {opp}")
    print(f"\n{len(rows)} code(s).  done=captured  new=uncaptured  dead=wiped")
    return 0


def cmd_codes_mark(args: argparse.Namespace) -> int:
    with Database(_db_path(args)) as db:
        db.upsert_code_status(args.code, args.status, args.notes)
    print(f"marked {args.code} as {args.status}")
    return 0


def cmd_codes_age(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    with Database(_db_path(args)) as db:
        s = db.code_age_summary(faceit_path,
                                division=None if args.division == "all" else args.division)
    print(f"latest wipe:   {s['latest_wipe'] or '(none recorded)'}")
    print(f"stored codes:  {s['total_codes']}")
    print(f"  alive (post-wipe, capturable): {s['alive_codes']}")
    print(f"  dead  (pre-wipe, unrecoverable): {s['dead_codes']}")
    print(f"captured maps: {s['captured']}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    with Database(_db_path(args)) as db:
        if args.hero is not None:
            if args.observation is None or args.slot is None:
                print("error: --hero requires --observation and --slot", file=sys.stderr)
                return 2
            # Resolve one slot to a hero the operator names.
            if not os.path.exists(faceit_path):
                print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
                return 2
            from .faceit import connect_ro, hero_roles as load_hero_roles, load_heroes
            with connect_ro(faceit_path) as fdb:
                roles = load_hero_roles(fdb)
                heroes = load_heroes(fdb)
            by_name = {h.name.lower(): h.guid for h in heroes}
            guid = by_name.get(args.hero.lower())
            if guid is None:
                print(f"error: no hero named {args.hero!r}", file=sys.stderr)
                return 2
            names = {h.guid: h.name for h in heroes}
            done = db.resolve_slot(args.observation, args.slot, guid,
                                   hero_roles=roles, hero_names=names)
            print(f"resolved obs {args.observation} slot {args.slot} -> {args.hero}"
                  + ("  (observation now complete)" if done else ""))
            return 0
        # List the review queue.
        queue = db.unresolved_observations(limit=args.limit)
    if not queue:
        print("review queue empty - nothing unresolved.")
        return 0
    print(f"{len(queue)} unresolved observation(s):")
    for o in queue:
        slots = cast("list[dict[str, object]]", o["slots"])
        gaps = [s for s in slots if s["hero_guid"] is None]
        print(f"  obs {o['id']}  {o['demo_code']} {o['map_name']} side {o['side']} "
              f"@ {o['sample_ts_ms']}ms - {len(gaps)} slot(s) unresolved: "
              f"{[s['slot_index'] for s in gaps]}")
    print("\nResolve with:  owscout review --observation <id> --slot <i> --hero <name>")
    return 0


def _resolve_team(db: Database, faceit_path: str, name: str) -> Optional[tuple[str, str]]:
    from .faceit import connect_ro, resolve_team_id
    with connect_ro(faceit_path) as fdb:
        tid = resolve_team_id(fdb, name)
        if tid is None:
            return None
        row = fdb.execute("SELECT name FROM teams WHERE id = ?", (tid,)).fetchone()
    return tid, (row["name"] if row else name)


def cmd_comps_top(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    with Database(_db_path(args)) as db:
        captured, total = db.capture_coverage(faceit_path)
        stats = aggregate_comps(db.resolved_observations())
    # Mandatory sampling-bias disclosure (SPEC 10.3).
    pct = f"{100.0 * captured / total:.1f}%" if total else "0%"
    print(f"Based on {captured} maps captured of {total} played ({pct}). Captured maps are")
    print("those the operator chose to scout - this sample is NOT representative of the league.\n")
    if not stats:
        print("no resolved comps captured yet.")
        return 0
    stats = [s for s in stats if s.samples >= args.min_samples] or stats
    print(f"{'Wilson':>7} {'winrate':>9} {'maps':>5} {'teams':>6}  comp")
    print("-" * 72)
    for s in stats[: args.limit]:
        wr = render_rate(s.wins, round(s.games), args.min_samples)
        print(f"{s.wilson:>7.2f} {wr:>9} {s.distinct_maps:>5} {s.distinct_teams:>6}  {s.hero_names}")
    print("\nWin rate is map-level and directional, not causal (SPEC 10.3).")
    return 0


def cmd_scout_team(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    with Database(_db_path(args)) as db:
        resolved = _resolve_team(db, faceit_path, args.team)
        if resolved is None:
            print(f"error: team not found: {args.team!r}", file=sys.stderr)
            return 2
        team_id, team_name = resolved
        roster = db.team_roster(faceit_path, team_id)
        bans = db.team_ban_tendencies(faceit_path, team_id)
        obs = db.resolved_observations(team_id=team_id)
        mc = modal_comp(obs)
        from .faceit import connect_ro, hero_roles as load_hero_roles, load_heroes
        with connect_ro(faceit_path) as fdb:
            roles = load_hero_roles(fdb)
            names = {h.guid: h.name for h in load_heroes(fdb)}
        synth = synthetic_comp(obs, roles, db.comp_hero_guids())

    print(f"== {team_name} ==")
    print("\nroster (most-played, from faceit):")
    for _pid, nick, maps in roster:
        print(f"  {nick:<20} {maps} maps")
    print("\ntop hero bans (real data):")
    for hero, n in bans[:8]:
        print(f"  {hero:<20} {n}")
    if not bans:
        print("  (none attributed)")
    print("\nmodal comp (captured):")
    if mc is None:
        print("  (no captured comps yet for this team)")
    else:
        print(f"  {mc.hero_names}")
        print(f"  run on {mc.maps} map(s): {mc.wins}W-{mc.losses}L")
    if synth:
        print("\nSYNTHETIC likely comp (composite - may never have been fielded):")
        print("  " + ", ".join(names.get(g, g) for _role, g in synth))
    return 0


def cmd_scout_player(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    from .faceit import connect_ro, hero_roles as load_hero_roles, load_heroes, resolve_player_id
    with Database(_db_path(args)) as db:
        with connect_ro(faceit_path) as fdb:
            pid = resolve_player_id(fdb, args.player)
            if pid is None:
                print(f"error: player not found: {args.player!r}", file=sys.stderr)
                return 2
            roles = load_hero_roles(fdb)
            names = {h.guid: h.name for h in load_heroes(fdb)}
        entries, total = player_pool(db.player_hero_maps(pid), roles)
    print(f"== {args.player} - hero pool ==")
    if total == 0:
        print("  no resolved captures for this player yet.")
        print("  (per-player pools need player-name resolution during capture - SPEC 8.2.)")
        return 0
    print(f"  {total} map(s) captured\n")
    for e in entries:
        rate = render_rate(e.maps, total, args.min_samples)
        print(f"  {names.get(e.hero_guid, e.hero_guid):<18} {e.role or '-':<8} {rate}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui import main as gui_main
    return gui_main()


def cmd_export(args: argparse.Namespace) -> int:
    import csv as _csv
    import json as _json
    with Database(_db_path(args)) as db:
        rows = db.resolved_observations()

    if args.format == "dashboard":
        # The sync artifact: team-keyed comps for the faceit-scout dashboard.
        from .derive import dashboard_comps
        payload = _json.dumps(dashboard_comps(rows), indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload)
            teams = len(cast("dict[str, object]", dashboard_comps(rows)["teams"]))
            print(f"wrote {args.out} ({teams} team(s) with captured comps)")
        else:
            print(payload)
        return 0

    stats = aggregate_comps(rows)
    records = [
        {"comp": s.hero_names, "comp_id": s.comp_id, "samples": s.samples,
         "distinct_maps": s.distinct_maps, "distinct_teams": s.distinct_teams,
         "games": round(s.games, 2), "wins": round(s.wins, 2),
         "win_rate": round(s.win_rate, 4), "wilson": round(s.wilson, 4)}
        for s in stats
    ]
    out = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    try:
        if args.format == "json":
            out.write(_json.dumps(records, indent=2))
        else:
            w = _csv.DictWriter(out, fieldnames=list(records[0].keys()) if records
                                else ["comp", "comp_id", "samples", "distinct_maps",
                                      "distinct_teams", "games", "wins", "win_rate", "wilson"])
            w.writeheader()
            w.writerows(records)
    finally:
        if out is not sys.stdout:
            out.close()
    return 0


def cmd_verify_codes(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    with Database(_db_path(args)) as db:
        rep = verify_codes_report(db.verify_codes_rows(faceit_path))
    if rep.total == 0:
        print("no captured faceit instances yet - nothing to verify")
        return 0
    print(f"captured instances: {rep.total}  (map-checked: {rep.checked})")
    print(f"map mismatches:     {rep.mismatches}"
          + (f"  ({rep.mismatch_rate:.0%} of checked)" if rep.checked else ""))
    print(f"  in matches with a restart shell: {rep.mismatches_in_restart_matches}")
    print(f"  in clean matches:                {rep.mismatches_in_clean_matches}")
    if rep.clusters_on_restarts:
        print("\n[!] mismatches cluster entirely on post-restart matches - this confirms "
              "the faceit-sync demoURLs index-assignment bug (sync.py:400).")
    elif rep.mismatches:
        print("\nmismatches are not restart-only; investigate individually.")
    return 1 if rep.mismatches else 0


def cmd_code_show(args: argparse.Namespace) -> int:
    faceit_path = _faceit_db_path(args)
    if not os.path.exists(faceit_path):
        print(f"error: faceit DB not found: {faceit_path}", file=sys.stderr)
        return 2
    try:
        with Database(_db_path(args)) as db:
            ctx = derive_code_context(db, faceit_path, args.code)
    except CodeNotFound:
        print(
            f"error: demo_code {args.code!r} not found in the faceit DB "
            "(dead after a wipe, or never ingested)",
            file=sys.stderr,
        )
        return 2
    except AmbiguousCode as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_context(ctx))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="owscout",
        description="Overwatch 2 composition extraction from in-client replays.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--db", default=None,
                   help="owscout SQLite path (default: $OWSCOUT_DB or owscout.sqlite3)")
    p.add_argument("--faceit-db", default=None,
                   help="faceit-sync SQLite path, read-only (default: $FACEIT_DB or faceit.sqlite3)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("calibrate", help="capture and persist ROI/anchor boxes for the HUD")
    c.add_argument("--hud-variant", default="default",
                   help="name this HUD layout variant (default: 'default')")
    c.add_argument("--team-size", type=int, default=DEFAULT_TEAM_SIZE,
                   help=f"portraits per team strip (default: {DEFAULT_TEAM_SIZE})")
    c.add_argument("--frame-dir", default=None,
                   help="where to save the full calibration frame (default: calibration/ next to the DB)")
    c.add_argument("--dry-run", action="store_true", help="run the flow but do not write")
    c.set_defaults(func=cmd_calibrate)

    r = sub.add_parser("refs", help="build/verify the reference-portrait library")
    rsub = r.add_subparsers(dest="refs_command", required=True)

    rc = rsub.add_parser("capture", help="guided capture of hero refs (alive + dead)")
    rc.add_argument("--hud-variant", default="default", help="HUD variant to capture for")
    rc.add_argument("--side", default=SIDE_LEFT, choices=("a", "b"),
                    help="which HUD side holds the reference slot (default: a)")
    rc.add_argument("--slot", type=int, default=0,
                    help="slot index within the side's strip to crop (default: 0)")
    rc.add_argument("--state", default="both", choices=("both", *REF_STATES),
                    help="capture 'alive', 'dead', or 'both' (default: both)")
    rc.add_argument("--only", default=None,
                    help="restrict to heroes whose name contains this substring")
    rc.add_argument("--refs-dir", default=None,
                    help="where to store ref crops (default: refs/ next to the DB)")
    rc.add_argument("--dry-run", action="store_true", help="hash but do not write")
    rc.set_defaults(func=cmd_refs_capture)

    rs = rsub.add_parser("from-sheet",
                         help="build the whole library from one hero-gallery screenshot")
    rs.add_argument("image", help="path to the all-heroes gallery screenshot")
    rs.add_argument("--hud-variant", default="default", help="HUD variant to attach refs to")
    rs.add_argument("--refs-dir", default=None,
                    help="where to store ref crops (default: refs/ next to the DB)")
    rs.add_argument("--dry-run", action="store_true", help="detect + map but do not write")
    rs.set_defaults(func=cmd_refs_from_sheet)

    rf = rsub.add_parser("from-frame",
                         help="batch: name all heroes visible in one observer frame")
    rf.add_argument("--hud-variant", default="default", help="HUD variant to capture for")
    rf.add_argument("--state", default="alive", choices=REF_STATES,
                    help="visual state shown in this frame (default: alive)")
    rf.add_argument("--refs-dir", default=None,
                    help="where to store ref crops (default: refs/ next to the DB)")
    rf.add_argument("--dry-run", action="store_true", help="hash but do not write")
    rf.set_defaults(func=cmd_refs_from_frame)

    rl = rsub.add_parser("learn",
                         help="live loop: show each hero, confirm the guess -> HUD ref "
                              "(the reliable way to seed/upgrade the library)")
    rl.add_argument("--hud-variant", default="default", help="HUD variant to capture for")
    rl.add_argument("--state", default="alive", choices=REF_STATES,
                    help="visual state shown while learning (default: alive)")
    rl.add_argument("--calibrate-slot", action="store_true",
                    help="first drag ONE box around a single portrait, then learn from "
                         "only that box (best for a solo custom-game replay)")
    rl.add_argument("--refs-dir", default=None,
                    help="where to store ref crops (default: refs/ next to the DB)")
    rl.add_argument("--dry-run", action="store_true", help="guess + preview but do not write")
    rl.set_defaults(func=cmd_refs_learn)

    rv = rsub.add_parser("verify", help="report missing refs and near-duplicate portraits")
    rv.add_argument("--hud-variant", default="default", help="HUD variant to verify")
    rv.add_argument("--close-threshold", type=int, default=DEFAULT_CLOSE_THRESHOLD,
                    help=f"flag ref pairs within this Hamming distance (default: {DEFAULT_CLOSE_THRESHOLD})")
    rv.set_defaults(func=cmd_refs_verify)

    m = sub.add_parser(
        "match",
        help="constraint-aware match of one frame against the ref library (the gate)",
    )
    m.add_argument("--frame", required=True, help="path to a saved frame (PNG)")
    m.add_argument("--match-id", required=True, help="faceit match id for the map")
    m.add_argument("--game-no", type=int, required=True, help="game (map) number within the match")
    m.add_argument("--team", required=True, help="team whose comp to read on --side")
    m.add_argument("--side", default=SIDE_LEFT, choices=("a", "b"),
                   help="which HUD side that team is on (default: a / left)")
    m.add_argument("--hud-variant", default="default", help="HUD variant of the profile")
    m.add_argument("--confidence-floor", type=float, default=DEFAULT_CONFIDENCE_FLOOR,
                   help=f"below this score a slot is left unresolved (default: {DEFAULT_CONFIDENCE_FLOOR})")
    m.set_defaults(func=cmd_match)

    cap = sub.add_parser(
        "capture",
        help="sample a replay under speed-mode playback and store comp observations",
    )
    cap.add_argument("--code", required=True, help="the 6-char demo_code to capture")
    cap.add_argument("--hud-variant", default="default", help="HUD variant of the profile")
    cap.add_argument("--speed", type=float, default=1.0,
                     help="playback speed you set in the client, e.g. 4 (config, not detected)")
    cap.add_argument("--fps", type=float, default=1.5, help="capture rate (default: 1.5)")
    cap.add_argument("--duration", type=float, default=None,
                     help="stop after this many wall-clock seconds (default: until Ctrl+C)")
    cap.add_argument("--side-a-team", default=None,
                     help="team on the LEFT HUD strip (else assumes faction1 + warns)")
    cap.add_argument("--write-interval-ms", type=int, default=DEFAULT_WRITE_INTERVAL_MS,
                     help=f"heartbeat write cadence in GAME ms (default: {DEFAULT_WRITE_INTERVAL_MS})")
    cap.add_argument("--confidence-floor", type=float, default=DEFAULT_CONFIDENCE_FLOOR,
                     help=f"below this a slot is left unresolved (default: {DEFAULT_CONFIDENCE_FLOOR})")
    cap.add_argument("--division", default=DEFAULT_DIVISION,
                     help="only capture this division: master (default), expert, or all")
    cap.add_argument("--hotkey", default=None, metavar="KEY",
                     help="snapshot mode: press this key (e.g. f8) to grab the comp at "
                          "bookmarked moments, instead of the continuous loop")
    cap.add_argument("--debug-dir", default=None, metavar="DIR",
                     help="hotkey mode: save each snapshot's full frame here for diagnosis")
    cap.add_argument("--dry-run", action="store_true", help="match but do not write")
    cap.set_defaults(func=cmd_capture)

    codes = sub.add_parser("codes", help="list/mark demo codes and show wipe age")
    csub = codes.add_subparsers(dest="codes_command", required=True)
    cl = csub.add_parser("list", help="capturable codes (wipe-filtered, newest first)")
    cl.add_argument("--team", default=None, help="only this team's codes")
    cl.add_argument("--uncaptured", action="store_true", help="only codes not yet captured")
    cl.add_argument("--include-wiped", action="store_true", help="include dead (pre-wipe) codes")
    cl.add_argument("--division", default=DEFAULT_DIVISION,
                    help="skill division: master (default), expert, or all")
    cl.add_argument("--limit", type=int, default=None, help="cap the number shown")
    cl.set_defaults(func=cmd_codes_list)
    cm = csub.add_parser("mark", help="record operator intent/outcome for a code")
    cm.add_argument("--code", required=True)
    cm.add_argument("--status", required=True, choices=("unknown", "captured", "skipped", "failed"))
    cm.add_argument("--notes", default=None)
    cm.set_defaults(func=cmd_codes_mark)
    ca = csub.add_parser("age", help="wipe date and alive/dead code counts")
    ca.add_argument("--division", default=DEFAULT_DIVISION,
                    help="skill division: master (default), expert, or all")
    ca.set_defaults(func=cmd_codes_age)

    rev = sub.add_parser("review", help="the unresolved-observation queue (SPEC appendix)")
    rev.add_argument("--limit", type=int, default=None, help="cap queue entries listed")
    rev.add_argument("--observation", type=int, default=None, help="observation id to resolve")
    rev.add_argument("--slot", type=int, default=None, help="slot index to resolve")
    rev.add_argument("--hero", default=None, help="hero name to set for --observation/--slot")
    rev.set_defaults(func=cmd_review)

    scout = sub.add_parser("scout", help="scouting output for a team or player (SPEC 10)")
    ssub = scout.add_subparsers(dest="scout_command", required=True)
    sp = ssub.add_parser("player", help="a player's hero pool (the primary output)")
    sp.add_argument("player", help="player nickname")
    sp.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    sp.set_defaults(func=cmd_scout_player)
    st = ssub.add_parser("team", help="roster, ban tendencies, modal + synthetic comp")
    st.add_argument("team", help="team name")
    st.add_argument("--min-samples", type=int, default=DEFAULT_MIN_SAMPLES)
    st.set_defaults(func=cmd_scout_team)

    comps = sub.add_parser("comps", help="cross-team comp database (SPEC 10.3)")
    cpsub = comps.add_subparsers(dest="comps_command", required=True)
    ct = cpsub.add_parser("top", help="top comps by Wilson lower bound, with bias disclosure")
    ct.add_argument("--min-samples", type=int, default=10)
    ct.add_argument("--limit", type=int, default=25)
    ct.set_defaults(func=cmd_comps_top)

    gui = sub.add_parser("gui", help="launch the desktop app (clickable workflow)")
    gui.set_defaults(func=cmd_gui)

    ex = sub.add_parser("export", help="export the comp table to csv/json")
    ex.add_argument("--format", choices=("csv", "json", "dashboard"), default="csv",
                    help="csv/json: comp table; dashboard: team-keyed JSON for the scout site")
    ex.add_argument("--out", default=None, help="output file (default: stdout)")
    ex.set_defaults(func=cmd_export)

    vc = sub.add_parser(
        "verify-codes",
        help="report map-name mismatches over captured instances (SPEC 9.2)",
    )
    vc.set_defaults(func=cmd_verify_codes)

    code = sub.add_parser("code", help="inspect what a demo_code implies (via faceit)")
    codesub = code.add_subparsers(dest="code_command", required=True)
    cs = codesub.add_parser("show", help="derive and print a demo_code's full context")
    cs.add_argument("code", help="the 6-char demo_code")
    cs.set_defaults(func=cmd_code_show)
    return p


def _make_console_crashproof() -> None:
    """Windows consoles default to cp1252, which can't encode characters that
    appear in our messages (em-dashes, , hero names). Replace un-encodable
    characters instead of raising UnicodeEncodeError mid-print."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):  # pragma: no cover - stream can't reconfigure
                pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _make_console_crashproof()
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    func = args.func
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
