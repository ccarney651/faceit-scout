// docs/capture/engine/idb.js
// IndexedDB helpers shared by index.html and scrim.html for the
// 'owscout-capture' database. Extracted from the two hand-maintained forks
// (see tools/capture_divergence.py): idbGetAll/idbPutIn/idbClear were
// byte-identical between the pages. `idb` itself (the function that actually
// calls indexedDB.open and creates object stores in onupgradeneeded) had
// diverged - not by drift, but by design: the two pages own different
// stores. index.html creates maps/refs/heroes; scrim.html additionally
// creates scrims/scrim_maps (it never touches the 'maps' store, so it never
// created it - see the module's open() contract below).
//
// This module must never know which page is running it, so open() takes the
// store list from its caller: `stores` is a plain object mapping store name
// -> keyPath. getAll/putIn/clear reuse that configuration on every call
// (matching the original per-call-fresh-open behaviour: every call opened its
// own fresh connection with the same version+stores, and IndexedDB only
// actually runs onupgradeneeded the first time a version is reached).
//
// BOTH PAGES MUST PASS ALL_STORES, NOT THEIR OWN SUBSET. Each page passing
// only the stores it uses is the obvious design and it is broken, because
// onupgradeneeded fires once per version: whichever page opens the database
// first at a given version creates its own stores and *fixes the version*, so
// the other page's stores are never created and every transaction on them
// throws "One of the specified object stores was not found". It is symmetric -
// open the league page first and scrim capture is dead; open the scrim page
// first and league capture is dead.
//
// This predates the engine extraction (verified against main @ 7e7bde2, which
// fails identically) and was survivable only because scrim capture was paused,
// so nobody reached the scrim stores. Un-pausing scrims made the normal path -
// a new contributor opening the league page first - a broken one.
//
// Creating a store a page never touches costs nothing: an empty object store
// has no storage or performance impact. Divergent store lists cost a
// completely broken page.
//
// The schema version is owned by the capture app and is passed in by the
// caller too, so a change to it is visible and deliberate at the call site
// rather than buried here.
//
// docs/scrims.html is a read-only consumer with its own, separate
// indexedDB.open('owscout-capture') call *without* a version argument -
// exactly how it reads data without ever triggering an upgrade transaction.
// It does not use this module and must not be wired to it.
//
// Works as a browser global (`window.OWDBIdb`) and as a CommonJS module for
// node:test / pytest.

(function (global) {
  'use strict';

  var DB_NAME = 'owscout-capture';

  // Every store any capture page uses, with its keyPath. Both pages pass this
  // whole object to open() - see the header for why a per-page subset breaks
  // the other page. Adding a store here requires a SCHEMA_VERSION bump, or
  // existing databases never gain it.
  var ALL_STORES = {
    maps: 'id',          // league captures        (index.html)
    refs: 'id',          // learned hero portraits (both)
    heroes: 'g',         // custom heroes          (both)
    scrims: 'id',        // scrim sessions         (scrim.html)
    scrim_maps: 'id',    // scrim maps             (scrim.html)
  };

  // Bumped 4 -> 5 to heal databases created before ALL_STORES: a browser that
  // opened only one capture page is sitting at v4 with half the stores, and
  // without a version change onupgradeneeded would never fire to add the rest.
  // onupgradeneeded only ever ADDS stores, so no existing data is touched -
  // learned hero refs in particular are irreplaceable and must survive this.
  var SCHEMA_VERSION = 5;

  // Set by the caller's open(version, stores) call; reused by
  // getAll/putIn/clear so every operation talks to the same schema.
  var _version = null, _stores = null;

  // open(version, stores) — pass SCHEMA_VERSION and ALL_STORES. docs/scrims.html
  // opens without a version and must never trigger an upgrade.
  function open(version, stores) {
    _version = version; _stores = stores;
    return new Promise(function (res, rej) {
      var r = indexedDB.open(DB_NAME, version);
      r.onupgradeneeded = function () {
        var db = r.result;
        Object.keys(stores).forEach(function (name) {
          if (!db.objectStoreNames.contains(name)) db.createObjectStore(name, { keyPath: stores[name] });
        });
      };
      r.onsuccess = function () { res(r.result); };
      r.onerror = function () { rej(r.error); };
    });
  }

  function _reopen() {
    if (_version == null) throw new Error('OWDBIdb.open(version, stores) must be called before getAll/putIn/clear');
    return open(_version, _stores);
  }

  function getAll(store) {
    return _reopen().then(function (db) {
      return new Promise(function (res) {
        var rq = db.transaction(store, 'readonly').objectStore(store).getAll();
        rq.onsuccess = function () { res(rq.result || []); };
        rq.onerror = function () { res([]); };
      });
    });
  }

  function putIn(store, rec) {
    return _reopen().then(function (db) {
      return new Promise(function (res, rej) {
        var tx = db.transaction(store, 'readwrite');
        tx.objectStore(store).put(rec);
        tx.oncomplete = res;
        tx.onerror = function () { rej(tx.error); };
      });
    });
  }

  function clear(store) {
    return _reopen().then(function (db) {
      return new Promise(function (res) {
        var tx = db.transaction(store, 'readwrite');
        tx.objectStore(store).clear();
        tx.oncomplete = res;
      });
    });
  }

  var Mod = {
    ALL_STORES: ALL_STORES,
    SCHEMA_VERSION: SCHEMA_VERSION,
    open: open,
    getAll: getAll,
    putIn: putIn,
    clear: clear,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBIdb = Mod;
})(typeof self !== 'undefined' ? self : this);
