// docs/capture/engine/refs.js
// Hero recognition shared by index.html and scrim.html: matching a portrait
// crop against the learned+baked reference library (bestMatch), teaching new
// refs (addRef/learnCrop/refTemplate), the hero picker's name/slug/portrait
// helpers, and export/import/clear of the operator's learned library.
//
// Extracted from the two hand-maintained forks (see tools/capture_divergence.py):
// addRef, matchCrop, learnCrop, refTemplate, exportRefs, clearLearnedRefs,
// heroCatalog, heroName, heroSlug, heroPortrait and onlyLostKnown were
// byte-identical between the pages - moved verbatim.
//
// bestMatch and importRefs both showed up as "diverged" by character count,
// but neither is a real behavioural difference - read in full (see
// tools/capture_divergence.py's brace-balanced bodies, diffed with
// difflib.SequenceMatcher to be sure a character-count delta wasn't hiding a
// real change, per this plan's own lesson that it can):
//   - bestMatch: index.html carried one trailing comment
//     ("// fast = centre only: ...") that scrim.html didn't. That comment is
//     kept below since it documents real behaviour (the `fast` flag). No
//     other byte differs - the matcher itself was NEVER divergent between
//     the pages, despite this task's brief flagging it as "the serious one."
//   - importRefs: scrim.html spelled the em dash as a `—` escape,
//     index.html as a literal '—' character - identical string either way.
//     Moved using the literal-character form, same convention as
//     engine/calibration.js's calMsg.
//
// ocrWorker is the one REAL divergence, and the two pages don't just differ
// in size - they differ in what they need the shared worker to do:
//   - index.html's copy raced a 30s timeout, cleared its own cache on ANY
//     failure (so a later Snapshot actually retries instead of replaying a
//     dead rejected promise), and recorded the failure reason - all fixes
//     for a real hang bug. scrim.html's copy had none of that: a stalled
//     Tesseract.createWorker() call hangs it forever with no escape but a
//     page reload, the exact bug index.html already fixed. index.html's
//     robustness is a strict improvement with no downside for scrim.html, so
//     it's what's below.
//   - index.html's copy ALSO set tessedit_char_whitelist to the HUD-gamertag
//     charset (letters/digits/_-.'~, no space) at worker creation. That is
//     NOT a strict improvement for scrim.html: scrim.html reuses this same
//     cached worker for readScoreboard() and ocrTextFromImage() (scrim.html
//     lines ~938-957, ~1256+), which read full scoreboard rows and
//     replay-history screenshots - map names with spaces, "VICTORY"/"DEFEAT",
//     score dashes with spaces around them. None of those characters survive
//     the gamertag whitelist. Baking it into the shared ocrWorker() would
//     silently break scrim.html's scoreboard/screenshot OCR the first time
//     the cached worker got reused for anything but a HUD-name crop. So the
//     whitelist stays OUT of this module and is applied by index.html's own
//     ocrNames() instead (one extra setParameters() call, scoped to that
//     page's own use of the worker) - see index.html's ocrNames for why.
//     ocrWorker() below only sets tessedit_pageseg_mode:'7', which is what
//     BOTH pages already used as the worker's resting configuration (scrim's
//     readScoreboard/ocrTextFromImage both reset back to mode '7' when done
//     with their own temporary mode).
//
// fixReads, onFixPick and remapHero are NOT part of this module despite
// showing up in the same divergence-tool run (fixReads/onFixPick diverge by
// comments only, same as bestMatch; remapHero's difference is real but
// correctly page-scoped - index.html resets rec.published=false and
// re-enables the #publish button after an edit, because index.html has a
// publish step and scrim.html deliberately does not, see scrim.html's own
// "no replay-code or publish step" comment). All three stay page-side,
// calling this module's addRef/bestMatch/heroCatalog/learnCrop/matchCrop as
// free variables through the destructure each page already does for
// engine/frames.js and engine/calibration.js.
//
// REF_W/REF_H/PAD/LF/TF/boxes/REFS/LOCAL_REFS/CUSTOM_HEROES/HERO_ICON are
// deliberately NOT part of ctx, for the same reason engine/frames.js gives
// for REF_W/REF_H/PAD/LF/TF/boxes: they're page-level globals shared with
// frames.js, calibration.js and each page's own code (loadFeeds/loadRefs
// seed REFS/LOCAL_REFS/CUSTOM_HEROES/HERO_ICON before this module's
// functions are ever called), so they're resolved as free variables at call
// time through the shared global lexical scope classic <script> tags get.
//
// _ocrWorker/_ocrLoading/_ocrLoadFailed/_ocrLoadError are the same story,
// NOT ctx and NOT module-private state, even though only ocrWorker() (this
// module) sets them: index.html's own ensureSideResolved() and warmOcr()
// read/clear them directly (surfacing "OCR failed before (...) - retrying..."
// and deciding whether to warm the worker early), and its ocrNames() resets
// _ocrWorker/_ocrLoading to null on a wedged read to force a fresh worker
// next time. Making them instance-private here would silently break that -
// the exact "shared browser state" trap this plan's lessons warn about, just
// inside one page's own script instead of across the two pages via
// localStorage/IndexedDB. scrim.html didn't declare _ocrLoadFailed/
// _ocrLoadError before this change (it had no retry logic of its own); it
// now does, purely so the shared ocrWorker() has somewhere to write - dead
// state there today, same as scrim.html carrying calibration.js's boxKeys
// for boxes it doesn't set.
//
// ctx = {doc, ocrLoadTimeoutMs} - doc is the DOM handle (document.
// getElementById/createElement) this module can't reach any other way, same
// convention as frames.js/calibration.js. ocrLoadTimeoutMs replaces
// index.html's page-level `const OCR_LOAD_TIMEOUT_MS` (scrim.html had no
// equivalent) - it's only read inside ocrWorker(), so it moved to ctx
// instead of staying a free variable both pages would have to declare
// identically; defaults to 30000 (index.html's original value) when omitted.
//
// Works as a browser global (`window.OWDBRefs`) and as a CommonJS module for
// node:test / pytest.

(function (global) {
  'use strict';

  function make(ctx) {
    var ocrLoadTimeoutMs = ctx.ocrLoadTimeoutMs || 30000;

    // ---------- matcher ----------
    // Offset search radius, in px, for a candidate buffer that carries a REAL
    // edge-clamped border (matchCrop below).
    //
    // The ref library and the live crop can disagree by a few px: the refs are
    // baked from one capture geometry, while the replay path re-derives the
    // HUD's own tile pitch per map, so no fixed library can sit exactly where
    // every frame's crop lands. Measured on retained strips (2026-09-15): a
    // clean -4px horizontal shift takes Lucio 0.31 -> 0.84 and Bastion 0.42 ->
    // 0.86, with 0.4-0.5 margins over the runner-up. The damage is not
    // random - it lands on the HIGH-SPATIAL-FREQUENCY portraits (Lucio,
    // Bastion, Ana), whose correlation peak is sharp, while smooth ones
    // (Baptiste, D.Mon, Reinhardt) have a broad peak and never noticed. The
    // old +/-2px window could not reach -4, so those portraits read
    // low-but-correct forever and every one of them needed a human review.
    //
    // The asymmetry is why side b looked worse than side a across the whole
    // corpus (mean 0.756 against 0.850): the b-side geometry disagreement
    // between the baked refs and the replay crop is larger (up to ~4.3px at
    // slot 0) than side a's (~1.3px). One global offset, filtered by portrait
    // detail, is the whole effect.
    //
    // 14 is measured, not guessed. Over 10455 retained slots (2026-09-15),
    // widening from the old +/-2 to 6/10/14 took low-score (<0.6) reads from
    // 24.7% to 9.0%/4.5%/2.9%, and the confident-flip hazard (slots the old
    // path read >=0.6 that changed hero) stayed flat at 0.5-0.8% throughout -
    // nearly every flip is the SAME repair signature (Brigitte/Vendetta read
    // 0.6x, the true hero 0.8-0.98). 6 truncates real peaks: 17.4% of its
    // winners sit exactly on the +/-6 edge, and 10 still truncates (Winston
    // 0.857 and Ramattra 0.862 at 10 become 0.917/0.913 at 14). 14 does NOT:
    // re-searching r14's 344 boundary winners at r20 and r28 leaves 199 of
    // them clamped at the r20 edge and moves the rest onto physically
    // impossible offsets ((20,20), (22,27)) - i.e. those crops are not
    // portraits (a badly calibrated session), so no real peak lies beyond 14.
    // The cost is bounded: ~55ms/slot, about 4s on an ~88s map, and the bot
    // is matchCrop's only production caller. Re-run
    // tools/replay_bot/match_search_sweep.js if this number is ever revisited.
    var MATCH_SEARCH = ctx.search || 14;

    function bestMatch(gp, variant, fast, pad, radius){
      if(pad==null) pad=PAD;
      const W=REF_W+2*pad; let best={score:-2,name:'?',guid:null,dx:0,dy:0};
      const cand=new Float32Array(REF_W*REF_H);
      function probe(dx,dy){
        let m=0;
        for(let y=0;y<REF_H;y++){ const s=(y+pad+dy)*W+(pad+dx); for(let x=0;x<REF_W;x++){ const v=gp[s+x]; cand[y*REF_W+x]=v; m+=v; } }
        m/=cand.length; let ss=0; for(let i=0;i<cand.length;i++){cand[i]-=m;ss+=cand[i]*cand[i];} const cn=Math.sqrt(ss)||1;
        let win=null;
        for(const r of REFS){ if(r.v!==variant) continue; let dot=0; const rc=r.c; for(let i=0;i<cand.length;i++) dot+=rc[i]*cand[i]; const s=dot/(r.norm*cn); if(!win||s>win.score) win={score:s,name:r.n,guid:r.g}; }
        if(win && win.score>best.score) best={score:win.score,name:win.name,guid:win.guid,dx:dx,dy:dy};
      }
      // Two search shapes, on purpose:
      //  - radius == null: the legacy three-step window (-PAD, 0, +PAD) over a
      //    PAD-padded buffer, byte-for-byte the behaviour the two capture pages
      //    have always had. Their cellGrayPadded buffer pads with a SCALED copy
      //    of the crop rather than a border, so a wider window there would
      //    change the candidate's SCALE, not its offset - and the calibrate
      //    sweep (fast=true) needs the box's own offset to stay visible in the
      //    score, so fast is centre-only.
      //  - radius given: a coarse 2px sweep of +/-min(radius, pad) for a buffer
      //    whose border is real pixels (matchCrop), then a 1px refinement
      //    around that winner. Coarse-to-fine rather than a full 1px grid
      //    because the finer grid is quadratic in the radius - the alignment
      //    correction is worth having on every map, and not worth a second of
      //    CPU per frame.
      if(radius==null){
        const span = fast ? 0 : PAD;
        for(let dy=-span; dy<=span; dy+=PAD) for(let dx=-span; dx<=span; dx+=PAD) probe(dx,dy);
      } else {
        const span = Math.min(radius, pad);
        for(let dy=-span; dy<=span; dy+=2) for(let dx=-span; dx<=span; dx+=2) probe(dx,dy);
        const cx=best.dx, cy=best.dy;
        for(let dy=cy-2; dy<=cy+2; dy++) for(let dx=cx-2; dx<=cx+2; dx++)
          if(dx>=-span && dx<=span && dy>=-span && dy<=span) probe(dx,dy);
      }
      return best; }

    function heroSlug(n){ return String(n).toLowerCase().replace(/[^a-z0-9]/g,''); }

    function heroPortrait(n){ const src=HERO_ICON[heroSlug(n)]; return src?`<img class="hp" src="${src}" alt="${esc(n)}" title="${esc(n)}">`:''; }

    // ---------- hero recognition: learn a miss / add a new hero ----------
    // A ref = a 64x36 grayscale portrait template. The built-in library is
    // refs.json (curator-baked); operators can LEARN more from the live frame
    // here - a fix when a portrait reads wrong, or a brand-new hero the
    // library has never seen. Learned refs persist in IndexedDB, merge into
    // REFS on load, and export as JSON so the curator can fold the good ones
    // back into refs.json.
    // Mirror of loadFeeds' refs.json decode: center + L2-normalise so
    // bestMatch's cosine similarity is comparable to the baked refs. Tagged
    // local for Clear.
    function refTemplate(rec){ const px=b64bytes(rec.d); if(px.length!==REF_W*REF_H) return null;
      let m=0; for(let i=0;i<px.length;i++) m+=px[i]; m/=px.length;
      const c=new Float32Array(px.length); let ss=0; for(let i=0;i<px.length;i++){ c[i]=px[i]-m; ss+=c[i]*c[i]; }
      return {n:rec.n, g:rec.g, v:rec.v, c, norm:Math.sqrt(ss)||1, local:true}; }

    async function addRef(rec){ if(!rec.id) rec.id=(crypto.randomUUID?crypto.randomUUID():String(Date.now())+Math.random());
      const t=refTemplate(rec); if(!t) return false;
      LOCAL_REFS.push(rec); REFS.push(t); try{ await idbPutIn('refs',rec); }catch(e){}
      const rc=ctx.doc.getElementById('refcount'); if(rc) rc.textContent=LOCAL_REFS.length+' learned'; return true; }

    // The 64x36 grayscale icon crop for slot i on a side — the SAME icon region the
    // matcher reads (right 1-LF width, top TF height of the cell), so a learned ref
    // lines up with future reads.
    function learnCrop(side,i){ const b=boxes[side]; const cell={x:b.x+i*b.w/5,y:b.y,w:b.w/5,h:b.h};
      const fx=cell.x+cell.w*LF, fy=cell.y, fw=cell.w*(1-LF), fh=cell.h*TF;
      const cv=ctx.doc.createElement('canvas'); cv.width=REF_W; cv.height=REF_H;
      const cx=cv.getContext('2d',{willReadFrequently:true}); cx.imageSmoothingEnabled=true; cx.imageSmoothingQuality='high';
      cx.drawImage(grabFrame(), fx,fy,fw,fh, 0,0,REF_W,REF_H);
      const d=cx.getImageData(0,0,REF_W,REF_H).data, px=new Uint8Array(REF_W*REF_H);
      for(let j=0,k=0;j<d.length;j+=4,k++) px[k]=Math.round(0.299*d[j]+0.587*d[j+1]+0.114*d[j+2]);
      return bytesToB64(px); }

    // Every hero the picker offers = unique guids in REFS (built-in + learned) plus
    // operator-added heroes, by name.
    function heroCatalog(){ const m={}; for(const r of REFS) if(r.g) m[r.g]=r.n;
      for(const g in CUSTOM_HEROES) m[g]=CUSTOM_HEROES[g].name;
      return Object.keys(m).map(g=>({g, n:m[g]})).sort((a,b)=>a.n.localeCompare(b.n)); }

    // ---------- review & correct a captured map ----------
    function heroName(g){ if(CUSTOM_HEROES[g]) return CUSTOM_HEROES[g].name; const r=REFS.find(x=>x.g===g); return r?r.n:g; }

    // Re-run the matcher on a stored 64x36 grayscale crop: centre it in a
    // buffer padded by MATCH_SEARCH and sweep that window for the best
    // alignment - see MATCH_SEARCH for why the range is what it is.
    //
    // The border REPEATS the edge pixel rather than holding zeros. The old
    // zero-filled buffer was the second half of the bug: the search's own
    // extremes read into the black band, so the two window positions that
    // pointed furthest away were also the two that correlated worst, and the
    // ±PAD window could never usefully reach even its own limit.
    function matchCrop(b64, side){ const px=b64bytes(b64), pad=Math.max(PAD, MATCH_SEARCH), W=REF_W+2*pad;
      const gp=new Float32Array(W*(REF_H+2*pad));
      for(let y=0;y<REF_H+2*pad;y++){ const sy=y<pad?0:(y>=pad+REF_H?REF_H-1:y-pad);
        for(let x=0;x<REF_W+2*pad;x++){ const sx=x<pad?0:(x>=pad+REF_W?REF_W-1:x-pad);
          gp[y*W+x]=px[sy*REF_W+sx]; } }
      return bestMatch(gp, side, false, pad, MATCH_SEARCH); }

    function exportRefs(){ if(!LOCAL_REFS.length && !Object.keys(CUSTOM_HEROES).length){ refMsg('nothing learned to export yet.','warn'); return; }
      const payload={format:'owdb-refs', w:REF_W, h:REF_H, left_fraction:LF, top_fraction:TF,
        refs:LOCAL_REFS.map(r=>({n:r.n, g:r.g, v:r.v, d:r.d})), heroes:CUSTOM_HEROES};
      const blob=new Blob([JSON.stringify(payload)],{type:'application/json'}); const a=ctx.doc.createElement('a');
      a.href=URL.createObjectURL(blob); a.download='owdb-learned-refs.json'; a.click(); }

    async function importRefs(file){ try{ const j=JSON.parse(await file.text());
      if(j.w && (j.w!==REF_W || j.h!==REF_H)){ refMsg('those refs are a different size — skipped.','warn'); return; }
      for(const g in (j.heroes||{})){ CUSTOM_HEROES[g]={name:j.heroes[g].name, role:j.heroes[g].role||'Damage'}; try{ await idbPutIn('heroes',{g, ...CUSTOM_HEROES[g]}); }catch(e){} }
      let n=0; for(const r of (j.refs||[])){ if(r.d && r.g && r.v){ await addRef({n:r.n, g:r.g, v:r.v, d:r.d, added_at:Date.now()}); n++; } }
      refMsg('imported '+n+' refs.','ok');
     }catch(e){ refMsg('import failed: '+(e.message||e),'warn'); } }

    async function clearLearnedRefs(){ if(!(await uiConfirm('Remove all learned refs? The built-in library stays; operator-added heroes are kept.','Clear learned refs'))) return;
      REFS=REFS.filter(t=>!t.local); LOCAL_REFS=[]; try{ await idbClear('refs'); }catch(e){}
      const rc=ctx.doc.getElementById('refcount'); if(rc) rc.textContent='0 learned'; refMsg('cleared learned refs.','ok'); }

    function onlyLostKnown(prev,cur){ if(!prev) return false; if(prev.length!==cur.length) return false;
      for(let i=0;i<prev.length;i++){ if(prev[i]===cur[i]||cur[i]==null) continue; return false; } return true; }

    // ---------- tesseract.js loader ----------
    // Loaded lazily from CDN on first use (this page isn't an artifact, so no
    // CSP block - see the CSP <meta> tag, which already allows script-src
    // https://cdn.jsdelivr.net and worker-src blob: https://cdn.jsdelivr.net;
    // moving this function doesn't change what it fetches or how, only where
    // its definition lives, so it doesn't touch the CSP contract).
    // The script tag + Tesseract.createWorker() both pull more assets (core wasm,
    // eng.traineddata) from CDNs with no built-in deadline, so a stalled (not
    // failed - a genuine network *error* already rejects via onload/onerror)
    // connection hangs forever with no way to notice. Race a timeout alongside it,
    // and - unlike a plain memoized promise - clear _ocrLoading on ANY failure so
    // a later call actually retries instead of replaying the same dead
    // promise for the rest of the session.
    // Deliberately does NOT set tessedit_char_whitelist here - see this
    // file's header comment for why that has to stay page-specific.
    function ocrWorker(){ if(_ocrWorker) return Promise.resolve(_ocrWorker);
      if(_ocrLoading) return _ocrLoading;
      const attempt=(async()=>{
        if(!window.Tesseract){ await new Promise((res,rej)=>{ const s=ctx.doc.createElement('script');
          s.src='https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
          s.integrity='sha384-GJqSu7vueQ9qN0E9yLPb3Wtpd7OrgK8KmYzC8T1IysG1bcvxvIO4qtYR/D3A991F';
          s.crossOrigin='anonymous';
          s.onload=res; s.onerror=()=>rej(new Error('could not load the OCR library (offline?)')); ctx.doc.head.appendChild(s); }); }
        const w=await Tesseract.createWorker('eng');
        await w.setParameters({ tessedit_pageseg_mode:'7' });
        _ocrWorker=w; _ocrLoadFailed=false; return w; })();
      _ocrLoading=Promise.race([attempt,
        new Promise((_,rej)=>setTimeout(()=>rej(new Error('OCR is taking too long to load - try again')),ocrLoadTimeoutMs))]
      ).catch(e=>{ _ocrLoading=null; _ocrLoadFailed=true;
        _ocrLoadError=(e&&e.message)?e.message:String(e); console.error('[owdb] OCR load failed:',e);
        throw e; });
      return _ocrLoading; }

    return {
      addRef: addRef,
      bestMatch: bestMatch,
      matchCrop: matchCrop,
      learnCrop: learnCrop,
      refTemplate: refTemplate,
      exportRefs: exportRefs,
      importRefs: importRefs,
      clearLearnedRefs: clearLearnedRefs,
      heroCatalog: heroCatalog,
      heroName: heroName,
      heroSlug: heroSlug,
      heroPortrait: heroPortrait,
      onlyLostKnown: onlyLostKnown,
      ocrWorker: ocrWorker,
    };
  }

  var Mod = { make: make };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBRefs = Mod;
})(typeof self !== 'undefined' ? self : this);
