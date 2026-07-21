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
from .contribute import CONTRIB_DIR
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
from .models import DEFAULT_DIVISION, DEFAULT_TEAM_SIZE, REF_STATES, REGIONS, SIDE_LEFT
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
            region=getattr(args, "region", None),
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


def cmd_drafts(args: argparse.Namespace) -> int:
    with Database(_db_path(args)) as db:
        if args.fix is not None:
            map_id_s, side, wrong, right = args.fix
            if side not in ("a", "b"):
                print("error: SIDE must be 'a' or 'b'", file=sys.stderr)
                return 2
            from .faceit import connect_ro, hero_roles as load_roles, load_heroes
            with connect_ro(_faceit_db_path(args)) as fdb:
                heroes = load_heroes(fdb) + db.list_custom_heroes()
                roles = load_roles(fdb)
            for h in db.list_custom_heroes():
                if h.role:
                    roles[h.guid] = h.role
            by_name = {h.name.lower(): h.guid for h in heroes}
            guid_to_name = {h.guid: h.name for h in heroes}
            wg, rg = by_name.get(wrong.lower()), by_name.get(right.lower())
            if not wg or not rg:
                print(f"error: unknown hero {wrong!r} or {right!r}", file=sys.stderr)
                return 2
            n = db.correct_hero_in_map(int(map_id_s), side, wg, rg,
                                       hero_roles=roles, hero_names=guid_to_name)
            print(f"fixed {wrong} -> {right} on side {side} of map {map_id_s} "
                  f"({n} observation(s)).")
            _harvest(db, args, int(map_id_s), side, rg, guid_to_name.get(rg, right))
            return 0
        if args.finalize is not None:
            db.finalize_map(args.finalize)
            print(f"finalized map {args.finalize} - now included in exports.")
            return 0
        if args.discard is not None:
            db.discard_map(args.discard)
            print(f"discarded draft map {args.discard}.")
            return 0
        drafts = db.list_draft_maps()
        if not drafts:
            print("no draft maps - capture a replay first (captures are drafts).")
            return 0
        print(f"{len(drafts)} draft map(s) awaiting review (NOT yet in exports):")
        for d in drafts:
            print(f"  map {d.id}  {d.demo_code or '-'}  {d.map_name or '?'}  "
                  f"[{d.side_a or '?'} vs {d.side_b or '?'}]  {d.observations} obs")
            comps = db.map_side_comps(d.id)
            for side, label in (("a", d.side_a), ("b", d.side_b)):
                for names, n, resolved, sub, rnd, conf in (comps.get(side) or []):
                    tag = "" if resolved else " [unresolved]"
                    if conf is not None and conf < 0.62:
                        tag += f" (!) low conf {conf:.2f}"
                    pre = " ".join(t for t in (f"R{rnd}" if rnd else "",
                                               f"[{sub}]" if sub else "") if t)
                    pre = (pre + " ") if pre else ""
                    print(f"      {side} {label or '?':<16} {pre}x{n}: {names}{tag}")
        print("\nFinalize with:  owscout drafts --finalize <map_id>"
              "   |   discard:  owscout drafts --discard <map_id>")
    return 0


def _harvest(db: Database, args: argparse.Namespace, map_id: int, side: str,
             right_guid: str, hero_name: str) -> None:
    """Feed a correction back into the ref library. Best-effort: a failure here
    must never make the operator think the correction itself did not apply."""
    try:
        from .refs import default_refs_dir, harvest_correction
        prof = db.latest_active_profile(getattr(args, "hud_variant", "default"))
        if prof is None or prof.id is None:
            return
        # `drafts` carries neither --refs-dir nor --hud-variant, so both are
        # looked up defensively rather than assumed onto the namespace.
        path = harvest_correction(
            db, getattr(args, "refs_dir", None) or default_refs_dir(_db_path(args)),
            map_instance_id=map_id, side=side, right_guid=right_guid,
            hero_name=hero_name, profile_id=prof.id)
        if path:
            print(f"  learned a new {hero_name} reference from this fix.")
        else:
            print("  (no stored crop to learn from - captured before crop storage)")
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not harvest a ref: {exc})")


def cmd_contribute_export(args: argparse.Namespace) -> int:
    """Write this machine's captures in the shared exchange format."""
    import json as _json
    from .contribute import CONTRIB_DIR, build_contribution

    out = args.out or os.path.join(CONTRIB_DIR, f"{args.contributor}.json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with Database(_db_path(args)) as db:
        data = build_contribution(db, contributor=args.contributor,
                                  tool_version=__version__,
                                  finalized_only=not args.include_drafts)
    with open(out, "w", encoding="utf-8") as fh:
        _json.dump(data, fh, indent=2)
    obs = sum(len(m["observations"]) for m in data["maps"])
    print(f"wrote {out}: {len(data['maps'])} map(s), {obs} observation(s), "
          f"contributor '{args.contributor}'.")
    if not data["maps"]:
        print("  (nothing to share yet - captures must be FINALIZED in Review first)")
    return 0


def cmd_contribute_push(args: argparse.Namespace) -> int:
    """Export this machine's captures AND upload them to the site repo."""
    import json as _json
    from .contribute import CONTRIB_DIR, build_contribution, push_contribution

    with Database(_db_path(args)) as db:
        settings = db.get_settings("sync.")
        data = build_contribution(db, contributor=args.contributor,
                                  tool_version=__version__)
    if not data["maps"]:
        print("nothing to upload - finalize maps in Review first.")
        return 0
    body = _json.dumps(data, indent=2).encode("utf-8")

    from .contribute import DEFAULT_UPLOAD_ENDPOINT, push_to_endpoint
    endpoint = (args.endpoint or settings.get("sync.endpoint", "")
                or DEFAULT_UPLOAD_ENDPOINT)
    if endpoint:
        import secrets as _secrets
        ident = settings.get("sync.identity", "")
        if not ident:
            ident = _secrets.token_hex(24)
            with Database(_db_path(args)) as db:
                db.set_settings({"sync.identity": ident})
        res = push_to_endpoint(body, endpoint=endpoint,
                               name=args.contributor.lower(), token=ident)
        print(f"uploaded {res.get('maps')} map(s) ({res.get('action')}). "
              "The site rebuilds itself within a couple of minutes.")
        return 0

    token = args.token or os.getenv("OWSCOUT_SYNC_TOKEN") or settings.get("sync.token", "")
    repo = args.repo or settings.get("sync.repo", "ccarney651/faceit-scout")
    if not token:
        print("error: no endpoint configured and no GitHub token (curator path)",
              file=sys.stderr)
        return 2
    res = push_contribution(body, repo=repo, token=token,
                            path=f"{CONTRIB_DIR}/{args.contributor}.json")
    print(f"uploaded {len(data['maps'])} map(s) to {repo} ({res['action']}). "
          "The site rebuilds itself within a couple of minutes.")
    return 0


def cmd_contribute_unscout(args: argparse.Namespace) -> int:
    """Undo an accidental publish: add (or --undo remove) a game in the exclude
    list of overrides.json, so the merge drops it from the report AND the
    already-scouted feed and the code frees up in the apps again."""
    import json as _json
    import sqlite3
    from .contribute import OVERRIDES_FILE

    raw = args.code.strip()
    if ":" in raw:
        mid, _, gno = raw.rpartition(":")
        try:
            match_id, game_no = mid, int(gno)
        except ValueError:
            print(f"bad match:game key {raw!r}", file=sys.stderr)
            return 2
    else:
        path = _faceit_db_path(args)
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            row = con.execute(
                "SELECT match_id, game_no FROM games WHERE demo_code = ?", (raw,)
            ).fetchone()
            con.close()
        except sqlite3.Error as exc:
            print(f"cannot read faceit DB {path}: {exc}", file=sys.stderr)
            return 2
        if not row:
            print(f"code {raw!r} not found in the faceit DB", file=sys.stderr)
            return 2
        match_id, game_no = str(row[0]), int(row[1])

    ov_path = os.path.join(args.dir, OVERRIDES_FILE)
    data: dict[str, object] = {}
    if os.path.exists(ov_path):
        with open(ov_path, encoding="utf-8") as fh:
            data = _json.load(fh)
    raw_excl = data.get("exclude")
    excl: list[object] = list(raw_excl) if isinstance(raw_excl, list) else []

    def _same(e: object) -> bool:
        return (isinstance(e, dict) and str(e.get("match_id")) == match_id
                and int(e.get("game_no", -1)) == game_no)

    if args.undo:
        excl = [e for e in excl if not _same(e)]
        verb = "re-allowed (removed from exclude list)"
    else:
        if not any(_same(e) for e in excl):
            excl.append({"match_id": match_id, "game_no": game_no})
        verb = "un-scouted (added to exclude list)"
    data["exclude"] = excl
    os.makedirs(args.dir, exist_ok=True)
    with open(ov_path, "w", encoding="utf-8") as fh:
        _json.dump(data, fh, indent=2)
    print(f"{match_id}:{game_no} {verb}")
    print(f"  wrote {ov_path} - commit + push (or let CI run) to apply on the site")
    return 0


def cmd_contribute_merge(args: argparse.Namespace) -> int:
    """Merge every contributor file into the published payload (first-wins)."""
    import json as _json
    from .contribute import (known_games, load_excludes, load_overrides,
                             merged_payload, resolve_contributions)
    from .faceit import connect_ro, hero_roles as load_roles, load_heroes

    contribs = resolve_contributions(args.dir, use_git_order=not args.name_order)
    overrides = load_overrides(args.dir)
    excludes = load_excludes(args.dir)
    if not contribs:
        print(f"no contribution files in {args.dir}", file=sys.stderr)
        return 2
    with connect_ro(_faceit_db_path(args)) as fdb:
        roles = load_roles(fdb)
        names = {h.guid: h.name for h in load_heroes(fdb)}
        pnames = {str(r["id"]): str(r["nickname"]) for r in fdb.execute(
            "SELECT id, nickname FROM players WHERE nickname IS NOT NULL")}
    # No owscout DB needed: contributions declare their own custom heroes, so a
    # build server can merge with nothing but the faceit roster and the files.
    # Validation against faceit.games is NOT optional here: this command is what
    # CI runs, and it is the only gate between a contributor file and the site.
    payload = merged_payload(contribs, roles, names, overrides=overrides,
                             known=known_games(_faceit_db_path(args)),
                             player_names=pnames, excludes=excludes)
    if args.captured_out:
        # A tiny public feed of which games are already scouted, so every
        # contributor's app can grey them out instead of two people scouting
        # the same replay on the same evening.
        os.makedirs(os.path.dirname(args.captured_out) or ".", exist_ok=True)
        with open(args.captured_out, "w", encoding="utf-8") as fh:
            _json.dump({"format": 1,
                        "generated_at": payload.get("built_at"),
                        "captured": payload.get("captured_games", [])}, fh)
        print(f"  wrote {args.captured_out} "
              f"({len(payload.get('captured_games') or [])} captured games)")
    with open(args.out, "w", encoding="utf-8") as fh:
        _json.dump(payload, fh, indent=2)
    teams = cast("dict[str, object]", payload["teams"])
    if overrides:
        print(f"  {len(overrides)} curator override(s) in effect")
    if excludes:
        print(f"  {len(excludes)} un-scouted map(s) excluded (freed up in the apps)")
    print(f"merged {payload['maps_merged']} map(s) from "
          f"{len(payload['contributors'])} contributor(s) -> {args.out} "
          f"({len(teams)} team(s))")
    for c in payload["contributors"]:
        print(f"    {c}")
    if payload["views_ignored"]:
        print(f"  {payload['views_ignored']} duplicate view(s) ignored "
              "(first submission owns the map; the data is kept)")
    if payload["maps_rejected"]:
        print(f"  !! {payload['maps_rejected']} map(s) REJECTED - they name games "
              "FACEIT has no record of, wrong teams, or wrong codes (see log)")
    return 0


def cmd_refs_export(args: argparse.Namespace) -> int:
    from .refs import export_ref_bundle
    try:
        with Database(_db_path(args)) as db:
            n = export_ref_bundle(db, args.out, hud_variant=args.hud_variant,
                                  faceit_db_path=_faceit_db_path(args),
                                  tool_version=__version__)
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {args.out}: {n['exported']} ref(s)"
          + (f", {n['skipped']} missing image(s) skipped" if n['skipped'] else "")
          + ". Ship this file; the recipient calibrates, then `refs import` it.")
    return 0


def cmd_refs_import(args: argparse.Namespace) -> int:
    from .refs import default_refs_dir, import_ref_bundle
    refs_dir = args.refs_dir or default_refs_dir(_db_path(args))
    try:
        with Database(_db_path(args)) as db:
            n = import_ref_bundle(db, args.bundle, refs_dir,
                                  hud_variant=args.hud_variant)
    except (CaptureError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"imported {n['added']} ref(s), {n['skipped']} already present.")
    print("Run `owscout doctor` to confirm coverage, then capture normally.")
    return 0


def cmd_refs_coverage(args: argparse.Namespace) -> int:
    """Which references have actually been tested by live captures, and which have
    been quietly wrong. Confidence finds shaky refs; corrections find confidently
    WRONG ones, which is the more dangerous kind."""
    with Database(_db_path(args)) as db:
        rows = db.hero_coverage(_faceit_db_path(args))
        unseen = db.unseen_heroes(_faceit_db_path(args))

    if not rows:
        print("no captures yet - coverage builds up as you capture maps.")
        return 0

    shown = rows if args.all else rows[:args.limit]
    print(f"{'hero':<22} {'team':<6} {'n':>4} {'worst':>7} {'mean':>7}  fixes")
    print("  " + "-" * 58)
    for r in shown:
        team = "blue" if r.variant == "a" else "red"
        # A correction means the matcher was confidently wrong - flag it loudly,
        # since a high mean confidence would otherwise make it look healthy.
        flag = "  <-- corrected" if r.corrections else ""
        print(f"  {r.hero_name:<22} {team:<6} {r.samples:>4} "
              f"{r.min_confidence:>7.3f} {r.avg_confidence:>7.3f}  "
              f"{r.corrections:>5}{flag}")
    if not args.all and len(rows) > len(shown):
        print(f"  ... {len(rows) - len(shown)} more (use --all)")

    seen_pairs = {(r.hero_guid, r.variant) for r in rows}
    print("")
    print(f"  tested: {len(seen_pairs)} hero+team refs across "
          f"{sum(r.samples for r in rows)} slots")
    if unseen:
        print(f"  NEVER seen in a capture: {len(unseen)} hero+team refs")
        for guid, name, variant in unseen[:12]:
            print(f"    {name} ({'blue' if variant == 'a' else 'red'})")
        if len(unseen) > 12:
            print(f"    ... and {len(unseen) - 12} more")
        print("  These are unvalidated - they may be fine, or silently wrong.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """One-glance health check: calibration, ref coverage per team, and drafts."""
    ok = True

    def line(mark: str, text: str) -> None:
        print(f"  [{mark}] {text}")

    with Database(_db_path(args)) as db:
        # Hero roster (faceit + custom).
        roster = 0
        faceit_path = _faceit_db_path(args)
        try:
            from .faceit import connect_ro, load_heroes
            with connect_ro(faceit_path) as fdb:
                roster = len(load_heroes(fdb))
            line("OK", f"faceit DB reachable - {roster} heroes in roster")
        except Exception as exc:  # noqa: BLE001
            ok = False
            line("!!", f"faceit DB not reachable: {exc}")
        customs = len(db.list_custom_heroes())
        if customs:
            line("OK", f"{customs} operator-added hero(es)")
        total = roster + customs

        prof = db.latest_active_profile(args.hud_variant)
        if prof is None or prof.id is None:
            ok = False
            line("!!", "no calibration profile - run calibrate")
        else:
            line("OK", f"calibrated: profile #{prof.id} "
                       f"{prof.resolution_w}x{prof.resolution_h} '{prof.hud_variant}'")
            cov = db.ref_variant_coverage(prof.id)
            for variant, team in (("a", "blue/left"), ("b", "red/right")):
                have = cov.get(variant, 0)
                mark = "OK" if total and have >= total else ".."
                if not (total and have >= total):
                    ok = False
                line(mark, f"{team} refs: {have}/{total or '?'} heroes learned")
            line("OK" if db.get_learn_slot(prof.id) else "..",
                 "single-portrait learn box calibrated"
                 if db.get_learn_slot(prof.id) else "no single learn box (scan mode)")

        counts = db.map_status_counts()
        line("..", f"{counts['draft']} draft map(s) awaiting review; "
                   f"{counts['finalized']} finalized (in exports)")

        # Learned refs are not the same as VALIDATED refs. A full library reads as
        # healthy above while most of it has never faced a live frame, so say so.
        try:
            seen = db.hero_coverage(faceit_path)
            unseen = db.unseen_heroes(faceit_path)
            if seen:
                weak = [c for c in seen if c.min_confidence < 0.70 or c.corrections]
                line("OK" if not weak else "..",
                     f"validated against live frames: {len(seen)} hero+team refs"
                     + (f"; {len(weak)} weak (see `owscout refs coverage`)" if weak else ""))
            if unseen:
                line("..", f"{len(unseen)} hero+team refs never seen in a capture "
                           "- unvalidated, not necessarily wrong")
        except Exception as exc:  # noqa: BLE001 - coverage is advisory, never fatal
            line("..", f"coverage unavailable ({exc})")
    print("\nreadiness: " + ("READY to capture." if ok else
                             "setup incomplete - address [!!]/[..] above."))
    return 0 if ok else 1


def cmd_heroes_add(args: argparse.Namespace) -> int:
    with Database(_db_path(args)) as db:
        guid = db.add_custom_hero(args.name, args.role)
    print(f"added hero {args.name!r} (role={args.role or 'unset'}) as {guid}.")
    print("Now learn its portrait:  open the app -> Learn heroes, or `owscout refs learn`.")
    return 0


def cmd_heroes_list(args: argparse.Namespace) -> int:
    with Database(_db_path(args)) as db:
        heroes = db.list_custom_heroes()
    if not heroes:
        print("no operator-added heroes.")
        return 0
    print(f"{len(heroes)} operator-added hero(es):")
    for h in heroes:
        print(f"  {h.guid:<28} {h.name:<18} role={h.role or 'unset'}")
    return 0


def cmd_heroes_remove(args: argparse.Namespace) -> int:
    with Database(_db_path(args)) as db:
        db.remove_custom_hero(args.guid)
    print(f"removed {args.guid}.")
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

    rx = rsub.add_parser("export", help="pack the learned hero library into a shareable zip")
    rx.add_argument("--out", default="owscout_refs.zip")
    rx.add_argument("--hud-variant", default="default")
    rx.set_defaults(func=cmd_refs_export)
    ri = rsub.add_parser("import", help="load a curator's hero library (calibrate first)")
    ri.add_argument("bundle", help="path to an owscout_refs.zip")
    ri.add_argument("--hud-variant", default="default")
    ri.add_argument("--refs-dir", default=None, help="where imported images are stored")
    ri.set_defaults(func=cmd_refs_import)

    rc = rsub.add_parser(
        "coverage",
        help="how each ref has performed against real frames (find the weak ones)")
    rc.add_argument("--limit", type=int, default=20,
                    help="how many of the weakest to show (default: 20)")
    rc.add_argument("--all", action="store_true", help="show every hero, not just the weakest")
    rc.set_defaults(func=cmd_refs_coverage)

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
    cl.add_argument("--region", choices=REGIONS, default=None,
                    help="only this region's championships (default: all)")
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

    dr = sub.add_parser("drafts", help="review captured DRAFT maps; finalize or discard")
    dr.add_argument("--finalize", type=int, default=None, metavar="MAP_ID",
                    help="finalize a draft (greenlight -> included in exports)")
    dr.add_argument("--discard", type=int, default=None, metavar="MAP_ID",
                    help="delete a draft map and its observations")
    dr.add_argument("--fix", nargs=4, default=None,
                    metavar=("MAP_ID", "SIDE", "WRONG", "RIGHT"),
                    help="fix a misread: replace hero WRONG with RIGHT on SIDE (a/b) "
                         "of MAP_ID (e.g. --fix 8 a Illari Mauga)")
    dr.set_defaults(func=cmd_drafts)

    doc = sub.add_parser("doctor", help="health check: calibration, ref coverage, drafts")
    doc.add_argument("--hud-variant", default="default", help="HUD variant to check")
    doc.set_defaults(func=cmd_doctor)

    her = sub.add_parser("heroes", help="add/list operator-added heroes (new OW2 releases)")
    hsub = her.add_subparsers(dest="heroes_command", required=True)
    ha = hsub.add_parser("add", help="register a hero not yet in faceit's roster")
    ha.add_argument("name", help="hero display name (e.g. 'Aqua')")
    ha.add_argument("--role", default=None, choices=("tank", "damage", "support"),
                    help="hero role (optional but recommended)")
    ha.set_defaults(func=cmd_heroes_add)
    hl = hsub.add_parser("list", help="list operator-added heroes")
    hl.set_defaults(func=cmd_heroes_list)
    hr = hsub.add_parser("remove", help="remove an operator-added hero by guid")
    hr.add_argument("guid", help="the custom:... guid (see 'heroes list')")
    hr.set_defaults(func=cmd_heroes_remove)

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

    con = sub.add_parser(
        "contribute", help="share captures / merge many contributors into one report")
    consub = con.add_subparsers(dest="contribute_command", required=True)
    ce = consub.add_parser("export", help="write this machine's captures for sharing")
    ce.add_argument("contributor", help="your contributor name (becomes the filename)")
    ce.add_argument("--out", default=None, help="output path (default: data/captures/<name>.json)")
    ce.add_argument("--include-drafts", action="store_true",
                    help="also share un-reviewed maps (not recommended)")
    ce.set_defaults(func=cmd_contribute_export)
    cp = consub.add_parser("push", help="export AND upload this machine's captures to the site")
    cp.add_argument("contributor", help="your contributor name")
    cp.add_argument("--endpoint", default=None, help="upload endpoint URL override")
    cp.add_argument("--repo", default=None, help="owner/name (default: sync settings)")
    cp.add_argument("--token", default=None, help="GitHub token (default: sync settings / env)")
    cp.set_defaults(func=cmd_contribute_push)
    cm = consub.add_parser("merge", help="merge all contributor files into the payload")
    cm.add_argument("--dir", default=CONTRIB_DIR, help="contributions directory")
    cm.add_argument("--out", default="owscout_comps.json", help="payload to write")
    cm.add_argument("--captured-out", default=None,
                    help="also write the public already-scouted feed here")
    cm.add_argument("--name-order", action="store_true",
                    help="order by filename instead of git commit date (testing)")
    cm.set_defaults(func=cmd_contribute_merge)

    cu = consub.add_parser(
        "unscout",
        help="mark a code NOT scouted (undo an accidental publish): drops it from "
             "the report + the already-scouted feed so it frees up in the apps")
    cu.add_argument("code", help="replay code (e.g. SXD9K6) or match_id:game_no")
    cu.add_argument("--dir", default=CONTRIB_DIR, help="contributions directory")
    cu.add_argument("--undo", action="store_true",
                    help="REMOVE the code from the exclude list (re-allow scouting it)")
    cu.set_defaults(func=cmd_contribute_unscout)

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
