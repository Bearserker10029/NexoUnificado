import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "nextcloud/apps/nexo_sync"


class NexoSyncTest(unittest.TestCase):
    def test_teams_bloquean_miembros_locales_de_otras_empresas(self):
        listener = (APP / "lib/Listener/TeamsListener.php").read_text(encoding="utf-8")
        controller = (APP / "lib/Controller/PageController.php").read_text(encoding="utf-8")
        template = (APP / "templates/main.php").read_text(encoding="utf-8")
        routes = (APP / "appinfo/routes.php").read_text(encoding="utf-8")
        setup = (ROOT / "nextcloud/tenants-oidc-setup.sh").read_text(encoding="utf-8")
        self.assertIn("$memberTenant === $ownerTenant", listener)
        self.assertIn("if (!$member->isLocal())", listener)
        self.assertIn("$this->memberRequest->delete($member)", listener)
        self.assertNotIn("intercompanyAllowed", listener)
        self.assertNotIn("toggleIntercompany", controller)
        self.assertNotIn("toggleIntercompany", routes)
        self.assertNotIn("Colaboración entre empresas", template)
        self.assertNotIn("config:app:set nexo_sync allow_intercompany", setup)

    def test_busqueda_de_teams_filtra_usuarios_y_grupos_de_otras_empresas(self):
        listener = (APP / "lib/Listener/MemberSearchListener.php").read_text(encoding="utf-8")
        application = (APP / "lib/AppInfo/Application.php").read_text(encoding="utf-8")
        self.assertIn("AutoCompleteFilterEvent", application)
        self.assertIn("MemberSearchListener::class", application)
        self.assertIn("IShare::TYPE_USER", listener)
        self.assertIn("IShare::TYPE_GROUP", listener)
        self.assertIn("$this->tenantOf($id) === $tenant", listener)
        self.assertIn("$this->tenantOfGroup($id) === $tenant", listener)
        self.assertIn("$event->setResults($results)", listener)

    def test_modo_seleccionado_se_conserva_y_normaliza_ids_numericos(self):
        controller = (APP / "lib/Controller/PageController.php").read_text(encoding="utf-8")
        self.assertIn("'assistant_mode_' . $tenant, $mode", controller)
        self.assertIn("$savedMode = $this->config->getValueString", controller)
        self.assertIn("array_map('strval', $users)", controller)
        self.assertIn("isset($selected[(string)$uid])", controller)

    def test_administrador_conserva_acceso_y_entrada_del_menu(self):
        controller = (APP / "lib/Controller/PageController.php").read_text(encoding="utf-8")
        template = (APP / "templates/main.php").read_text(encoding="utf-8")
        menu = (ROOT / "nextcloud/tenants-oidc-setup.sh").read_text(encoding="utf-8")
        self.assertIn("$selected[$uid] = true;", controller)
        self.assertIn("if ($isAdmin)", controller)
        self.assertIn("continue; // Los administradores tienen acceso siempre", controller)
        self.assertNotIn("$member['admin']", template)
        self.assertIn('"$name-administradores"', menu)

    def test_selector_es_un_modal_nativo_y_accesible(self):
        template = (APP / "templates/main.php").read_text(encoding="utf-8")
        script = (APP / "js/main.js").read_text(encoding="utf-8")
        css = (APP / "css/main.css").read_text(encoding="utf-8")
        self.assertIn("#nexo-sync .nx-dialog:not([open])", css)
        self.assertIn("script('nexo_sync', 'main')", template)
        self.assertIn('<dialog id="nx-assistant-users"', template)
        self.assertIn('aria-labelledby="nx-dialog-title"', template)
        self.assertIn("dialog.showModal()", script)
        self.assertIn("dialog.close()", script)
        self.assertNotIn("customMode.addEventListener('change'", script)
        self.assertIn('id="nx-open-assistant-users"', template)
        self.assertIn('Solo usuarios seleccionados</button>', template)

    def test_tabla_de_sectores_abre_en_un_modal_con_desplazamiento(self):
        template = (APP / "templates/main.php").read_text(encoding="utf-8")
        script = (APP / "js/main.js").read_text(encoding="utf-8")
        css = (APP / "css/main.css").read_text(encoding="utf-8")
        self.assertIn('<dialog id="nx-sectors"', template)
        self.assertIn('id="nx-open-sectors"', template)
        self.assertIn("bindDialog('nx-sectors', 'nx-open-sectors')", script)
        self.assertIn("position: fixed", css)
        self.assertIn("inset: 0", css)
        self.assertIn("margin: auto", css)
        self.assertIn("#nexo-sync .nx-sector-table", css)
        self.assertIn("overflow: auto", css)

    def test_tarjetas_y_acciones_comparten_una_rejilla_adaptable(self):
        template = (APP / "templates/main.php").read_text(encoding="utf-8")
        css = (APP / "css/main.css").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)
        self.assertIn("@media (max-width: 55rem)", css)
        self.assertIn("max-height: 9rem", css)
        self.assertIn("#nexo-sync .nx-assistant {\n    grid-column: 1 / -1;", css)
        self.assertEqual(template.count('<div class="nx-grid">'), 1)
        self.assertEqual(template.count('<section class="nx-card'), 4)
        self.assertEqual(template.count('id="nx-open-sectors"'), 1)
        create_sector = template.split('<h3>Crear sector</h3>', 1)[1].split('</section>', 1)[0]
        self.assertIn('id="nx-open-sectors"', create_sector)
        self.assertIn("flex-wrap: nowrap;", css)
        for title in ("Asistente IA", "Crear sector", "Crear usuarios"):
            self.assertIn(title, template.split('<div class="nx-grid">', 1)[1])


if __name__ == "__main__":
    unittest.main()
