// Data delivery: an inlined blob when present (offline / single-file builds),
// otherwise fetch the sibling data.json (the shell build). Next season this fetch
// is the single place gating hooks in.
(function(){
  if(typeof __OWDB_DATA__!=='undefined' && __OWDB_DATA__) return bootApp(__OWDB_DATA__);
  fetch('data.json',{cache:'no-store'})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(bootApp)
    .catch(function(err){ var c=document.getElementById('content');
      if(c) c.innerHTML='<p class="note" style="padding:24px">Could not load scouting data ('+err+'). Refresh to retry.</p>'; });
})();
</script>
</body>
</html>
