// Nexo Unificado: obtiene una extension SIP individual mediante la sesion
// OIDC de Keycloak. La persona no introduce usuario ni clave SIP.
(function () {
  function showError(message) {
    var container = document.getElementById('tryit-jssip-container');
    if (container) {
      container.textContent = message;
      container.style.cssText = 'padding:24px;color:#fff;font:16px sans-serif;background:#1b1b1b;min-height:100vh;box-sizing:border-box';
    }
  }

  var tenantMatch = window.location.pathname.match(/^\/([a-z][a-z0-9-]{1,30})\/voip\//);
  var configUrl = tenantMatch ? '/voip-sso/' + tenantMatch[1] + '/config.json' : '/voip-sso/config.json';
  fetch(configUrl, { credentials: 'same-origin' })
    .then(function (response) {
      if (response.status === 401) {
        return response.json().then(function (data) {
          window.location.replace(data.login_url || '/voip-sso/login');
          return null;
        });
      }
      if (!response.ok) throw new Error('No se pudo aprovisionar la extension');
      return response.json();
    })
    .then(function (settings) {
      if (!settings) return;
      localStorage.setItem('settings', JSON.stringify(settings));
      var script = document.createElement('script');
      script.src = '/voip/tryit-jssip.js';
      script.onerror = function () { showError('No se pudo cargar el softphone.'); };
      document.head.appendChild(script);
    })
    .catch(function () {
      showError('Telefonía no está disponible temporalmente. Vuelve a intentarlo en unos segundos.');
    });
})();
