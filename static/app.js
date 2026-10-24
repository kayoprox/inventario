(function () {
  var m = document.getElementById('menu'), bs = document.querySelectorAll('[data-menu]');
  function set(o) { if (!m) return; m.hidden = !o; bs.forEach(function (b) { b.setAttribute('aria-expanded', o); }); }
  bs.forEach(function (b) { b.addEventListener('click', function (e) { e.stopPropagation(); set(m.hidden); }); });
  document.addEventListener('click', function (e) {
    if (m && !m.contains(e.target)) set(false);
    document.querySelectorAll('details.kb[open]').forEach(function (d) { if (!d.contains(e.target)) d.open = false; });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') set(false); });
})();
