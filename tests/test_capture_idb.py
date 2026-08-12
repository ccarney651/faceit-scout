"""Browser capture app: docs/capture/engine/idb.js, the shared IndexedDB
wrapper extracted from index.html and scrim.html.

The database (`owscout-capture`) holds every contributor's hand-taught hero
reference templates (the `refs` store) plus their captured maps and scrims -
none of which can be regenerated. This module owns the one function that
calls `indexedDB.open` for both capture pages, so a bug here can silently
drop a store or trigger an unwanted schema upgrade for every contributor.

These tests run the actual module (not a re-implementation of its logic)
against a small in-memory fake of the IndexedDB API, plus pin the exact,
literal configuration each real page passes in.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

CAPTURE = Path(__file__).resolve().parents[1] / "docs" / "capture"
ENGINE_IDB = CAPTURE / "engine" / "idb.js"
INDEX_HTML = CAPTURE / "index.html"
SCRIM_HTML = CAPTURE / "scrim.html"
SCRIMS_HTML = Path(__file__).resolve().parents[1] / "docs" / "scrims.html"

# A minimal, faithful-enough fake of the browser's IndexedDB so the real
# module under test can run unmodified in Node. Mirrors the semantics
# idb.js actually relies on: onupgradeneeded fires only when the requested
# version is higher than what's stored, createObjectStore/getAll/put/clear
# behave like real object stores, and put/clear resolve via tx.oncomplete
# while getAll resolves via the request's own onsuccess.
_FAKE_IDB = r"""
function makeFakeIndexedDB(){
  var databases = {};
  return {
    _databases: databases,
    open: function(name, version){
      var req = { onupgradeneeded:null, onsuccess:null, onerror:null, result:null, error:null };
      setTimeout(function(){
        var rec = databases[name];
        var needUpgrade = !rec || (version != null && version > rec.version);
        if(!rec){ rec = databases[name] = { version: version || 1, stores: new Map() }; }
        else if(version != null){ rec.version = version; }
        var db = {
          objectStoreNames: { contains: function(n){ return rec.stores.has(n); } },
          createObjectStore: function(n, opts){ rec.stores.set(n, {keyPath: opts.keyPath, data: new Map()}); },
          transaction: function(storeName){
            var tx = { oncomplete: null, onerror: null };
            var storeObj = rec.stores.get(storeName);
            if(!storeObj){ throw new Error('NotFoundError: no object store named ' + storeName); }
            var api = {
              getAll: function(){
                var rq2 = { onsuccess: null, onerror: null, result: null };
                setTimeout(function(){ rq2.result = Array.from(storeObj.data.values()); if(rq2.onsuccess) rq2.onsuccess(); }, 0);
                return rq2;
              },
              put: function(rec2){ storeObj.data.set(rec2[storeObj.keyPath], rec2); setTimeout(function(){ if(tx.oncomplete) tx.oncomplete(); }, 0); },
              clear: function(){ storeObj.data.clear(); setTimeout(function(){ if(tx.oncomplete) tx.oncomplete(); }, 0); },
              delete: function(id){ storeObj.data.delete(id); setTimeout(function(){ if(tx.oncomplete) tx.oncomplete(); }, 0); },
            };
            tx.objectStore = function(){ return api; };
            return tx;
          },
        };
        req.result = db;
        if(needUpgrade && req.onupgradeneeded) req.onupgradeneeded();
        if(req.onsuccess) req.onsuccess();
      }, 0);
      return req;
    },
  };
}
global.indexedDB = makeFakeIndexedDB();
var module = { exports: {} };
"""


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    engine = ENGINE_IDB.read_text(encoding="utf-8")
    src = (
        _FAKE_IDB + "\n" + engine
        + "\nconst {open, getAll, putIn, clear} = module.exports;\n"
        + "(async () => {\ntry {\n" + body
        + "\n} catch (e) { console.log(JSON.stringify({ok:false, error: e.message})); }\n})();\n"
    )
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_open_creates_exactly_the_requested_stores() -> None:
    out = _run(
        "const db = await open(4, {maps:'id', refs:'id', heroes:'g'});\n"
        "console.log(JSON.stringify({ok:true, "
        "maps: db.objectStoreNames.contains('maps'), "
        "refs: db.objectStoreNames.contains('refs'), "
        "heroes: db.objectStoreNames.contains('heroes'), "
        "scrims: db.objectStoreNames.contains('scrims')}));"
    )
    assert out == {"ok": True, "maps": True, "refs": True, "heroes": True, "scrims": False}


def test_open_with_a_different_store_list_creates_that_list_instead() -> None:
    # This is the scrim.html shape: no 'maps' store, plus scrims/scrim_maps.
    out = _run(
        "const db = await open(4, {refs:'id', heroes:'g', scrims:'id', scrim_maps:'id'});\n"
        "console.log(JSON.stringify({ok:true, "
        "maps: db.objectStoreNames.contains('maps'), "
        "scrims: db.objectStoreNames.contains('scrims'), "
        "scrim_maps: db.objectStoreNames.contains('scrim_maps')}));"
    )
    assert out == {"ok": True, "maps": False, "scrims": True, "scrim_maps": True}


def test_getall_putin_clear_roundtrip_through_the_real_module_functions() -> None:
    out = _run(
        "await open(4, {refs:'id'});\n"
        "await putIn('refs', {id:'a', taught:1});\n"
        "const before = await getAll('refs');\n"
        "await clear('refs');\n"
        "const after = await getAll('refs');\n"
        "console.log(JSON.stringify({ok:true, before, after}));"
    )
    assert out == {"ok": True, "before": [{"id": "a", "taught": 1}], "after": []}


def test_reopening_at_the_same_version_does_not_wipe_existing_data() -> None:
    # A contributor's learned refs must survive every ordinary page load,
    # not just the first one - idb() is called fresh on every operation.
    out = _run(
        "await open(4, {refs:'id'});\n"
        "await putIn('refs', {id:'learned-hero', v:[1,2,3]});\n"
        "await open(4, {refs:'id'});\n"  # simulates the next call re-opening
        "const rows = await getAll('refs');\n"
        "console.log(JSON.stringify({ok:true, rows}));"
    )
    assert out == {"ok": True, "rows": [{"id": "learned-hero", "v": [1, 2, 3]}]}


# ---------------------------------------------------------------------------
# Literal pins on the real pages - the highest-consequence part of this task.
# These don't execute anything; they just make sure nobody quietly bumps the
# schema version or drops a store name from either page's wiring.
# ---------------------------------------------------------------------------


def test_both_capture_pages_request_schema_version_4() -> None:
    for page in (INDEX_HTML, SCRIM_HTML):
        html = page.read_text(encoding="utf-8")
        m = re.search(r"OWDBIdb\.open\(\s*(\d+)\s*,", html)
        assert m, f"{page.name}: no OWDBIdb.open(version, stores) call found"
        assert m.group(1) == "4", (
            f"{page.name}: schema version changed to {m.group(1)} - this must "
            "stay 4 or every contributor's learned refs/maps/scrims need a "
            "real, deliberate migration, not an incidental one from this task"
        )


def test_index_html_still_owns_maps_refs_heroes() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    m = re.search(r"IDB_STORES\s*=\s*\{([^}]*)\}", html)
    assert m, "index.html: IDB_STORES declaration not found"
    stores = m.group(1)
    for name in ("maps", "refs", "heroes"):
        assert name in stores, f"index.html: IDB_STORES is missing '{name}'"
    assert "scrims" not in stores and "scrim_maps" not in stores, (
        "index.html: IDB_STORES gained a scrim.html-only store - "
        "index.html never touches scrims/scrim_maps"
    )


def test_scrim_html_still_owns_refs_heroes_scrims_scrim_maps() -> None:
    html = SCRIM_HTML.read_text(encoding="utf-8")
    m = re.search(r"IDB_STORES\s*=\s*\{([^}]*)\}", html)
    assert m, "scrim.html: IDB_STORES declaration not found"
    stores = m.group(1)
    for name in ("refs", "heroes", "scrims", "scrim_maps"):
        assert name in stores, f"scrim.html: IDB_STORES is missing '{name}'"
    # scrim.html never reads/writes the 'maps' store (that's index.html's),
    # so it must not create it either.
    assert not re.search(r"\bmaps\s*:", stores), (
        "scrim.html: IDB_STORES gained the 'maps' store - scrim.html has no "
        "code path that uses it, so creating it here would be new, untested "
        "surface, not a faithful port"
    )


def test_scrims_html_still_opens_without_a_version_and_does_not_use_the_module() -> None:
    # docs/scrims.html is a read-only consumer. Opening indexedDB.open(name)
    # with no version argument is exactly how it avoids ever triggering an
    # upgrade transaction. It must stay standalone.
    html = SCRIMS_HTML.read_text(encoding="utf-8")
    assert "OWDBIdb" not in html, (
        "docs/scrims.html must not be wired to engine/idb.js: any call "
        "through OWDBIdb.open() requires a version argument, which would "
        "risk this read-only page triggering a schema upgrade"
    )
    m = re.search(r"indexedDB\.open\(\s*(['\"])owscout-capture\1\s*(,[^)]*)?\)", html)
    assert m, "docs/scrims.html: could not find its indexedDB.open call"
    assert not m.group(2), (
        "docs/scrims.html now passes a version to indexedDB.open - this "
        "will trigger onupgradeneeded (and block on the capture pages) the "
        "moment it doesn't match every open capture tab's version"
    )
