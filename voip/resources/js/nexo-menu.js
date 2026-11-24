(function () {
  // Quita "Exit" del menú del softphone: la sesión la controla el SSO de la plataforma,
  // no el softphone (salir desde aquí dejaba la telefonía sin registrar).
  function quitarExit(root) {
    var items = root.querySelectorAll('div');
    for (var i = 0; i < items.length; i++) {
      var el = items[i];
      if (el.children.length === 0 && el.textContent.trim() === 'Exit') {
        var entrada = el.closest('span[role="menuitem"]');
        (entrada && entrada.parentElement ? entrada.parentElement : el).remove();
      }
    }
  }
  new MutationObserver(function () { quitarExit(document.body); })
    .observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', function () { quitarExit(document.body); });
})();
