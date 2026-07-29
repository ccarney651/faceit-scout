"""Player-name capture and the self-contained HTML dashboard."""

from __future__ import annotations

import io
import json
import re

import responses

from faceit_sync.client import MATCH_URL
from faceit_sync.db import Database
from faceit_sync.export import _dashboard_data, export_html
from faceit_sync.sync import SyncEngine
from conftest import RESTART_DC_ID, make_client, register_match


def _ingest(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    SyncEngine(make_client()[0], db).ingest_match(RESTART_DC_ID, force_refresh=True)


def _register_scheduled(responses_mock, match_id: str, cid: str, *,
                        f1=("tA", "Alpha"), f2=("tB", "Bravo"),
                        schedule="2026-08-01T18:00:00Z", rnd=15) -> None:
    """A pre-finish fixture: status SCHEDULED, teams assigned, no results. Only the
    match endpoint is hit (no veto/stats for an unplayed match)."""
    payload = {
        "id": match_id, "status": "SCHEDULED", "schedule": schedule,
        "game": "ow2", "region": "EMEA",
        "entity": {"id": cid, "name": "S9 EMEA Master Central - Regular Season"},
        "entityCustom": {"round": rnd, "group": 1},
        "teams": {
            "faction1": {"id": f1[0], "name": f1[1], "roster": [{"id": f1[0] + "p", "nickname": "n1"}]},
            "faction2": {"id": f2[0], "name": f2[1], "roster": [{"id": f2[0] + "p", "nickname": "n2"}]},
        },
        "results": [], "voting": {}, "demoURLs": [],
    }
    responses_mock.add(responses_mock.GET, MATCH_URL.format(id=match_id),
                       json={"payload": payload}, status=200)


@responses.activate
def test_scheduled_excluded_from_stats_and_listed_in_upcoming(db: Database) -> None:
    """Scheduled fixtures must not inflate match counts / standings, but must
    appear in the `upcoming` payload the Matches tab reads."""
    _ingest(db)                                    # one FINISHED match
    cid = db.conn.execute("SELECT championship_id FROM matches LIMIT 1").fetchone()[0]
    mid = "1-22222222-2222-2222-2222-222222222222"
    _register_scheduled(responses, mid, cid, f1=("s1", "Sched One"), f2=("s2", "Sched Two"))
    SyncEngine(make_client()[0], db).ingest_match(mid)

    d = _dashboard_data(db, cid)
    assert d["summary"]["matches"] == 1            # the scheduled one is NOT counted
    # No phantom standings row from a winner-less scheduled match.
    assert all(t["matches"] >= 1 for t in d["teams"])
    assert "Sched One" not in {t["name"] for t in d["teams"]}
    # …but it IS in upcoming, with its matchup and time.
    up = d["upcoming"]
    assert len(up) == 1
    assert {up[0]["f1"], up[0]["f2"]} == {"Sched One", "Sched Two"}
    assert up[0]["scheduled_at"] == "2026-08-01T18:00:00Z" and up[0]["round"] == 15


@responses.activate
def test_players_table_gets_nicknames(db: Database) -> None:
    _ingest(db)
    n = db.conn.execute("SELECT COUNT(*) FROM players WHERE nickname IS NOT NULL").fetchone()[0]
    assert n >= 10
    # A known roster nickname from the fixture resolves.
    row = db.conn.execute("SELECT id FROM players WHERE nickname = 'NENONX'").fetchone()
    assert row is not None


@responses.activate
def test_export_html_is_self_contained_and_valid(db: Database) -> None:
    _ingest(db)
    buf = io.StringIO()
    count = export_html(db, buf)          # all divisions (just the one ingested)
    doc = buf.getvalue()

    assert count == 1
    assert doc.startswith("<!doctype html>")
    # No external resource LOADS: the page must render completely offline, with
    # every asset inlined. Tested precisely rather than by banning the string
    # "https://" outright, because the refresh button legitimately holds an
    # endpoint URL - a user-initiated fetch, not a resource the page loads.
    assert "<script src" not in doc and "<link" not in doc
    assert 'src="http' not in doc and "src='http" not in doc
    assert "url(http" not in doc and "@import" not in doc
    # ...and the only outbound URLs are the ones we intend.
    urls = {u.rstrip('",;)') for u in re.findall(r"https?://[^\s\"'<>]+", doc)}
    allowed_hosts = {"owscout-upload.owscout.workers.dev"}
    external = {u for u in urls
                if u.split("/")[2] not in allowed_hosts} if urls else set()
    assert not external, f"unexpected external URLs in the dashboard: {external}"

    # Embedded data parses back to JSON and reflects the ingest. The default build
    # inlines it as `var __OWSCOUT_DATA__={...};` (single line, so no DOTALL).
    m = re.search(r"var __OWSCOUT_DATA__=(\{.*\});", doc)
    assert m is not None
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert len(data["divisions"]) == 1
    assert data["views"] and data["views"][0]["divisions"]
    div = next(iter(data["divisions"].values()))
    assert div["summary"]["matches"] == 1
    assert div["summary"]["dc_games"] == 1          # hazard A game present
    assert div["summary"]["matches_with_attribution"] == 1  # restart_dc has live democracy


@responses.activate
def test_external_data_build_is_a_shell_plus_datajson(db: Database, tmp_path) -> None:
    """--external-data: the page becomes a shell that fetches data.json (the seam
    for future gating), instead of inlining the payload."""
    _ingest(db)
    dp = tmp_path / "data.json"
    buf = io.StringIO()
    count = export_html(db, buf, data_path=str(dp))
    doc = buf.getvalue()
    assert count == 1
    # Shell: NO inline blob, but the fetch bootstrap is present.
    assert "var __OWSCOUT_DATA__=" not in doc
    assert "fetch('data.json'" in doc
    # data.json is written and parses back to the same payload shape.
    assert dp.is_file()
    data = json.loads(dp.read_text(encoding="utf-8").replace("<\\/", "</"))
    assert len(data["divisions"]) == 1 and data["views"]


def _insert_match(db, cid, mid, status, f1, f2, winner, sched, fin, rnd, games) -> None:
    db.conn.execute(
        "INSERT OR REPLACE INTO matches(id,championship_id,round,group_no,status,best_of,"
        "scheduled_at,started_at,finished_at,faction1_team_id,faction2_team_id,winner_faction,"
        "forfeit,fetched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
        (mid, cid, rnd, 1, status, 5, sched, None, fin, f1, f2, winner, "2026-07-29T00:00:00Z"))
    for i, wf in enumerate(games, 1):
        db.conn.execute(
            "INSERT OR REPLACE INTO games(match_id,game_no,map_guid,map_category,winner_faction,"
            "was_restarted) VALUES(?,?,?,?,?,0)", (mid, i, "m1", "Control", wf))


def test_playoff_bracket_attaches_finished_and_scheduled(db: Database) -> None:
    """A "… - Playoffs" championship's matches — played AND upcoming — attach to
    the matching region+tier division as its bracket, without a 4th view."""
    c = db.conn
    c.execute("INSERT INTO maps(guid,name,category) VALUES('m1','Ilios','Control')")
    for tid, nm in [("t1", "Alpha"), ("t2", "Bravo"), ("t3", "Cabra"), ("t4", "Delta")]:
        c.execute("INSERT INTO teams(id,name) VALUES(?,?)", (tid, nm))
    reg, po = "reg-emea-master", "po-emea-master"
    c.execute("INSERT INTO championships(id,name,game,region) VALUES(?,?,?,?)",
              (reg, "S9 EMEA Master Central - Regular Season", "ow2", "EMEA"))
    c.execute("INSERT INTO championships(id,name,game,region) VALUES(?,?,?,?)",
              (po, "S9 EMEA Master Central - Playoffs", "ow2", "EMEA"))
    _insert_match(db, reg, "r1", "FINISHED", "t1", "t2", "faction1", None,
                  "2026-07-20T20:00:00Z", 1, ["faction1", "faction1"])
    _insert_match(db, po, "p1", "FINISHED", "t1", "t4", "faction1", None,
                  "2026-07-29T20:00:00Z", 1, ["faction1", "faction2", "faction1"])   # 2-1
    _insert_match(db, po, "p2", "SCHEDULED", "t1", "t3", None,
                  "2026-08-02T18:00:00Z", None, 2, [])
    db.conn.commit()

    buf = io.StringIO()
    export_html(db, buf, only_region="emea")
    data = json.loads(re.search(r"var __OWSCOUT_DATA__=(\{.*\});", buf.getvalue())
                      .group(1).replace("<\\/", "</"))
    # The playoff championship is NOT its own view — only the regular division.
    assert not any("Playoffs" in v["label"] for v in data["views"])
    div = next(d for d in data["divisions"].values()
               if "Master" in d["summary"]["championship"] and "Playoffs" not in d["summary"]["championship"])
    po_list = div.get("playoffs") or []
    assert sorted(x["status"] for x in po_list) == ["FINISHED", "SCHEDULED"]
    fin = next(x for x in po_list if x["status"] == "FINISHED")
    assert fin["series"] == "2-1" and fin["winner_team"] == "Alpha"
    sch = next(x for x in po_list if x["status"] == "SCHEDULED")
    assert sch["scheduled_at"] == "2026-08-02T18:00:00Z" and sch["round"] == 2 and sch["f2"] == "Cabra"


def test_is_playoff_classifies_championships() -> None:
    """Playoff championships are split out of the tier views/standings and attached
    to their division as results; regular-season ones are not."""
    from faceit_sync.export import _is_playoff

    assert _is_playoff("S9 EMEA Master Central - Playoffs")
    assert _is_playoff("S9 NA Expert Central - Knockout Stage")
    assert not _is_playoff("S9 EMEA Master Central - Regular Season")
    assert not _is_playoff(None)


def test_tier_and_region_classify_championship_names() -> None:
    """The EMEA-Master-only site filter keys off these. Names carry both words."""
    from faceit_sync.export import _region_of, _tier_of

    assert _tier_of("S9 EMEA Master Central - Regular Season") == "Master"
    assert _tier_of("S9 NA Expert Central - Regular Season") == "Expert"
    assert _tier_of("S9 EMEA Advanced Central - Regular Season") == "Advanced"
    assert _tier_of("S9 EMEA Open - Regular Season") == "Open"
    assert _tier_of("Regular Season Group A") is None
    assert _tier_of(None) is None
    assert _region_of("S9 EMEA Master Central - Regular Season") == "EMEA"
    assert _region_of("S9 NA Expert Central - Regular Season") == "NA"
    assert _region_of("Some Open Qualifier") is None
    assert _region_of(None) is None


def test_dashboard_javascript_is_syntactically_valid(tmp_path):
    """The dashboard renders its whole body in JS, so ONE syntax error (e.g. a
    duplicate `const`) yields a completely blank page — which balanced-bracket
    checks do not catch. Run the real parser over the generated script."""
    import re
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to parse the dashboard JS")

    from faceit_sync._dashboard import HTML_TEMPLATE

    html = HTML_TEMPLATE.replace("__TITLE__", "t").replace(
        "// __DATA_INLINE__",
        'var __OWSCOUT_DATA__={"divisions":{},"views":[],"heroes":[],"roster":{},'
        '"maps":[],"owscout_comps":{},"hero_icons":{}};')
    js = re.search(r"<script>(.*)</script>", html, re.S)
    assert js, "no <script> block found in the dashboard template"
    script = tmp_path / "dash.js"
    script.write_text(js.group(1), encoding="utf-8")
    proc = subprocess.run([node, "--check", str(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"dashboard JS is invalid:\n{proc.stderr}"


def test_hero_icon_cache_is_committed_and_usable() -> None:
    """CI has no access to the 22 MB of source art, so the dashboard's portraits
    come from this committed cache. If it goes missing the page still builds -
    silently, with text chips instead of portraits - so assert it explicitly."""
    from faceit_sync.hero_icons import ICON_CACHE, load_hero_icons

    assert ICON_CACHE.is_file(), f"icon cache missing at {ICON_CACHE}"
    icons = load_hero_icons()
    assert len(icons) >= 40, f"only {len(icons)} icons cached"
    assert all(v.startswith("data:image/") for v in icons.values())
    # A few well-known slugs, incl. the punctuation-stripped ones.
    for hero in ("dva", "wreckingball", "kiriko"):
        assert hero in icons, f"{hero} missing from the icon cache"
