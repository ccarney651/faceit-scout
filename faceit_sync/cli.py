"""Command-line interface: ``faceit-sync {fetch,export,stats}``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional, Sequence, TextIO

from dotenv import load_dotenv

from . import __version__
from .client import FaceitClient
from .db import Database
from .export import export_csv, export_html, export_json, team_stats
from .sync import EnumerationError, SyncEngine

log = logging.getLogger("faceit_sync")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else os.getenv("FACEIT_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _build_client() -> FaceitClient:
    return FaceitClient(
        api_key=os.getenv("FACEIT_API_KEY") or None,
        rate_limit=float(os.getenv("FACEIT_RATE_LIMIT", "4")),
    )


def _db_path(args: argparse.Namespace) -> str:
    return args.db or os.getenv("FACEIT_DB", "faceit.sqlite3")


def _collect_match_refs(args: argparse.Namespace) -> list[str]:
    refs: list[str] = list(args.matches or [])
    if args.matches_file:
        with open(args.matches_file, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    refs.append(line)
    return refs


def cmd_fetch(args: argparse.Namespace) -> int:
    refs = _collect_match_refs(args)
    client = _build_client()
    with Database(_db_path(args)) as db:
        engine = SyncEngine(client, db)
        if refs:
            # Mass import (keyless): explicit match ids/URLs win over enumeration.
            result = engine.run_matches(
                refs, force_refresh=args.force_refresh, dry_run=args.dry_run,
            )
            label = f"{len(refs)} match refs"
        elif args.championship:
            try:
                result = engine.run(
                    args.championship, force_refresh=args.force_refresh, dry_run=args.dry_run,
                )
            except EnumerationError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            label = f"championship {args.championship}"
        else:
            # Update every division already stored (transitive keyless discovery).
            n = db.conn.execute("SELECT COUNT(*) FROM championships").fetchone()[0]
            if not n:
                print("no divisions stored yet — seed first with:  "
                      "faceit-sync fetch --matches <room-url> ...", file=sys.stderr)
                return 2
            result = engine.run_all(
                force_refresh=args.force_refresh, dry_run=args.dry_run,
            )
            label = f"{n} division(s)"
    counts = result.as_dict()
    log.info(
        "done: seen=%(matches_seen)d inserted=%(inserted)d updated=%(updated)d "
        "skipped=%(skipped)d errors=%(errors)d", counts,
    )
    print(
        f"{label}: "
        f"{counts['matches_seen']} seen, {counts['inserted']} inserted, "
        f"{counts['updated']} updated, {counts['skipped']} skipped, "
        f"{counts['errors']} errors"
    )
    return 1 if counts["errors"] else 0


def _resolve_championship(db: Database, requested: Optional[str]) -> Optional[str]:
    """Use the requested id, or auto-pick when the DB holds exactly one."""
    if requested:
        return requested
    rows = db.conn.execute("SELECT id, name FROM championships ORDER BY name").fetchall()
    if len(rows) == 1:
        return str(rows[0]["id"])
    if not rows:
        print("no championships in the database yet — run `fetch` first", file=sys.stderr)
    else:
        print("multiple championships stored; pass --championship <id>:", file=sys.stderr)
        for r in rows:
            print(f"  {r['id']}  {r['name']}", file=sys.stderr)
    return None


def cmd_export(args: argparse.Namespace) -> int:
    with Database(_db_path(args)) as db:
        # HTML is the multi-division dashboard (all divisions unless one is named).
        if args.format == "html":
            out_path = args.out or "dashboard.html"
            with open(out_path, "w", newline="", encoding="utf-8") as out:
                n = export_html(db, out, championship_id=args.championship)
            if n == 0:
                print("no data to export yet", file=sys.stderr)
                return 1
            log.info("exported %d division(s) to %s", n, out_path)
            print(f"wrote {out_path} ({n} division(s))")
            return 0

        # csv/json: a single championship (auto-detected when only one is stored).
        cid = _resolve_championship(db, args.championship)
        if cid is None:
            return 2
        stream: TextIO = (
            open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
        )
        try:
            n = export_csv(db, cid, stream) if args.format == "csv" else export_json(db, cid, stream)
        finally:
            if stream is not sys.stdout:
                stream.close()
    if n == 0:
        print(f"no data for championship {cid}", file=sys.stderr)
        return 1
    if args.out:
        print(f"wrote {args.out}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with Database(_db_path(args)) as db:
        stats = team_stats(db, args.team)
    if stats is None:
        print(f"team not found: {args.team!r}", file=sys.stderr)
        return 1
    print(f"== {stats['team']} ==")
    print(
        f"matches: {stats['matches']}  wins: {stats['match_wins']}  "
        f"win rate: {stats['match_win_rate']}"
    )
    print(
        f"games:   {stats['games']}  wins: {stats['game_wins']}  "
        f"win rate: {stats['game_win_rate']}"
    )
    print("\ntop hero bans (attributed):")
    for b in stats["ban_tendencies"][:10]:
        print(f"  {b['hero']:<20} {b['count']}")
    if not stats["ban_tendencies"]:
        print("  (none attributed — democracy data absent/expired for these matches)")
    print("\nmap picks (attributed):")
    for p in stats["map_picks"][:10]:
        print(f"  {p['map']:<20} {p['count']}")
    if stats["bans_with_unknown_attribution"]:
        print(
            f"\nnote: {stats['bans_with_unknown_attribution']} of this team's games "
            "had bans with unknown attribution (restart or expired veto)."
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="faceit-sync",
        description="Incremental, idempotent ingest of FACEIT League (OW2) data.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--db", default=None, help="SQLite path (default: $FACEIT_DB or faceit.sqlite3)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser(
        "fetch",
        help="ingest a championship (needs API key) OR a list of match ids/URLs (keyless)",
    )
    f.add_argument("--championship", default=None,
                   help="championship id to enumerate via the Data API (needs FACEIT_API_KEY)")
    f.add_argument("--matches", nargs="+", metavar="ID_OR_URL",
                   help="one or more match ids or room URLs to mass-import (keyless)")
    f.add_argument("--matches-file", default=None,
                   help="file with one match id/URL per line (# comments allowed)")
    f.add_argument("--force-refresh", action="store_true",
                   help="re-fetch even matches already stored as FINISHED")
    f.add_argument("--dry-run", action="store_true", help="fetch and parse but do not write")
    f.set_defaults(func=cmd_fetch)

    e = sub.add_parser("export", help="export a championship to csv/json/html")
    e.add_argument("--championship", default=None,
                   help="championship id (optional; auto-detected when only one is stored)")
    e.add_argument("--format", choices=("csv", "json", "html"), required=True)
    e.add_argument("--out", default=None,
                   help="output file (csv/json default: stdout; html default: dashboard-<id>.html)")
    e.set_defaults(func=cmd_export)

    s = sub.add_parser("stats", help="team ban tendencies, map picks, win rates")
    s.add_argument("--team", required=True, help="team name")
    s.set_defaults(func=cmd_stats)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    func = args.func
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
