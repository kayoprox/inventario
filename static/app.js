(function () {
  var m = document.getElementById('menu'), bs = document.querySelectorAll('[data-menu]');
  function set(o) { if (!m) return; m.hidden = !o; bs.forEach(function (b) { b.setAttribute('aria-expanded', o); }); }
  bs.forEach(function (b) { b.addEventListener('click', function (e) { e.stopPropagation(); set(m.hidden); }); });

  function bloco(w) { var x = w; while (x.parentElement && !x.parentElement.classList.contains('dlg')) x = x.parentElement; return x; }
  function fechaListas(exceto) {
    document.querySelectorAll('[data-sel]').forEach(function (w) {
      if (w === exceto) return;
      w.querySelector('.selm').hidden = true; w.querySelector('.selb').setAttribute('aria-expanded', 'false'); bloco(w).classList.remove('elev');
    });
  }
  document.querySelectorAll('[data-sel]').forEach(function (w) {
    var b = w.querySelector('.selb'), l = w.querySelector('.selm'), h = w.querySelector('input'), v = w.querySelector('.sv');
    var itens = Array.prototype.slice.call(l.querySelectorAll('li'));
    function abre(o) {
      l.hidden = !o; b.setAttribute('aria-expanded', o); bloco(w).classList.toggle('elev', o);
      if (o) (l.querySelector('[aria-selected=true]') || itens[0]).focus();
    }
    function escolhe(li) {
      h.value = li.dataset.v;
      itens.forEach(function (x) { x.setAttribute('aria-selected', x === li); });
      v.innerHTML = li.innerHTML; abre(false); b.focus();
    }
    b.addEventListener('click', function (e) { e.stopPropagation(); fechaListas(w); abre(l.hidden); });
    b.addEventListener('keydown', function (e) { if (e.key === 'ArrowDown') { e.preventDefault(); fechaListas(w); abre(true); } });
    l.addEventListener('click', function (e) { var li = e.target.closest('li'); if (li) escolhe(li); });
    l.addEventListener('keydown', function (e) {
      var i = itens.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { e.preventDefault(); itens[Math.min(i + 1, itens.length - 1)].focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); itens[Math.max(i - 1, 0)].focus(); }
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (i >= 0) escolhe(itens[i]); }
      else if (e.key === 'Escape') { e.preventDefault(); abre(false); b.focus(); }
    });
  });

  document.addEventListener('click', function (e) {
    if (m && !m.contains(e.target)) set(false);
    fechaListas(null);
    document.querySelectorAll('details.kb[open]').forEach(function (d) { if (!d.contains(e.target)) d.open = false; });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') set(false); });
})();
