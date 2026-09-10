"""Generate ``refs_trainer.opy`` from the current hero roster.

    python tools/scrim_code/gen_refs_trainer.py
    cd tools/scrim_code && npx overpy compile -i refs_trainer.opy -o refs_trainer.txt

Then paste ``refs_trainer.txt`` into an empty custom game and run
``owdb refs learn --auto`` while spectating. See ``README.md`` (Refs trainer).

The roster it bakes in must match what ``owdb refs learn --auto`` sees, so both
call ``owdb.refs_trainer.plan_sequence`` on the same
``faceit.heroes`` + ``custom_heroes`` list. Regenerate whenever the roster
changes (a new hero, an ``owdb heroes add``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from owdb.db import Database  # noqa: E402
from owdb.faceit import connect_ro, load_heroes  # noqa: E402
from owdb.refs_trainer import partition_roster, plan_sequence, render_opy  # noqa: E402


def _roster(faceit_db: str, owdb_db: str, only: str | None) -> list[str]:
    with connect_ro(faceit_db) as fdb:
        names = [h.name for h in load_heroes(fdb)]
    with Database(owdb_db) as db:
        names += [h.name for h in db.list_custom_heroes()]
    if only:
        wanted = {s.strip().lower() for s in only.split(",") if s.strip()}
        names = [n for n in names if n.lower() in wanted]
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--faceit-db", default=str(_REPO_ROOT / "faceit.sqlite3"))
    ap.add_argument("--db", default=str(_REPO_ROOT / "owdb.sqlite3"))
    ap.add_argument("--out", default=str(Path(__file__).with_name("refs_trainer.opy")))
    ap.add_argument("--only", help="comma-separated hero names (e.g. for one new hero)")
    ap.add_argument("--hold", type=float, default=6.0,
                    help="seconds each step is held after the bots settle (default 6)")
    ap.add_argument("--settle", type=float, default=2.0,
                    help="seconds to let freshly-spawned bots render (default 2)")
    args = ap.parse_args(argv)

    names = _roster(args.faceit_db, args.db, args.only)
    mappable, unmapped = partition_roster(names)
    rows = plan_sequence(names)
    if not rows:
        print("error: no heroes in the roster map to a workshop Hero constant.",
              file=sys.stderr)
        return 2

    src = render_opy(rows, hold=args.hold, settle=args.settle)
    Path(args.out).write_text(src, encoding="utf-8")

    est = len(rows) * (args.hold + args.settle + 0.5) + 5
    print(f"wrote {args.out}")
    print(f"  {len(mappable)} heroes, {len(rows)} steps, ~{est:.0f}s to run")
    if unmapped:
        print(f"  NOT covered (no workshop Hero constant): {', '.join(unmapped)}")
        print("  -> add them to owdb/refs_trainer.py _HERO_ENUM, or learn them "
              "manually with `owdb refs learn`.")
    print(f"\nnext: cd {Path(args.out).parent}  &&  "
          f"npx overpy compile -i {Path(args.out).name} -o {Path(args.out).stem}.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
