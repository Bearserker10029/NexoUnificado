(function () {
  var match = window.location.pathname.match(/^\/([a-z][a-z0-9-]{1,30})\/voip\/embed\.html$/);
  var base = match ? '/' + match[1] + '/voip/' : '/voip/';
  document.getElementById('softphone').src = base;
  document.getElementById('abrir-voip').href = base;
})();
