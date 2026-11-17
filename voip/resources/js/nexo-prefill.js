// Nexo Unificado: precarga la red fija del softphone (WebSocket WSS detras
// del proxy, registrar y realm) la primera vez que se abre el cliente, para
// que el formulario de ajustes ya traiga esos campos llenos. No toca el
// usuario ni la contrasena: esos los elige la persona (100/101, 1100/1101).
(function () {
  try {
    if (localStorage.getItem('settings')) return;
    var defaults = {
      sockets: 'wss://' + window.location.host + '/asterisk/ws',
      registrar_server: 'sip:nexo.local',
      realm: 'nexo.local',
      register: true,
      register_expires: 600
    };
    localStorage.setItem('settings', JSON.stringify(defaults));
  } catch (e) {
    // localStorage no disponible (modo privado); el formulario queda vacio.
  }
})();
