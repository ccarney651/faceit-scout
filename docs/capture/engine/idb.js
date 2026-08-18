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
// -> keyPath, e.g. {maps:'id', refs:'id', heroes:'g'}. Each page calls
// open() once with its own list; getAll/putIn/clear reuse that
// configuration on every call (matching the original per-call-fresh-open
// behaviour: every idbGetAll/idbPutIn/idbClear call opened its own fresh
// connection with the same version+stores, and IndexedDB only actually runs
// onupgradeneeded the first time a version is reached).
//
// The schema version (4) is owned by the capture app and is passed in by
// the caller too - this module does not hardcode it, precisely so a change
// to it is visible and deliberate at the call site, not buried here.
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

  // Set by the caller's open(version, stores) call; reused by
  // getAll/putIn/clear so every operation talks to the same schema.
  var _version = null, _stores = null;

  // open(version, stores) — the caller owns its store list. scrim.html adds
  // 'scrims' and 'scrim_maps' to the three the league page creates. The
  // schema version is owned by the capture app; docs/scrims.html opens
  // without a version and must never trigger an upgrade.
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
    open: open,
    getAll: getAll,
    putIn: putIn,
    clear: clear,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBIdb = Mod;
})(typeof self !== 'undefined' ? self : this);
