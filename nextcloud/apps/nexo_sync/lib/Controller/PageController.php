<?php
declare(strict_types=1);

namespace OCA\NexoSync\Controller;

use OCA\NexoSync\AppInfo\Application;
use OCA\NexoSync\Listener\LoginListener;
use OCA\NexoSync\Service\Gateway;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\NoAdminRequired;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\AppFramework\Http\RedirectResponse;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\IAppConfig;
use OCP\IGroupManager;
use OCP\IRequest;
use OCP\IURLGenerator;
use OCP\IUserManager;
use OCP\IUserSession;

class PageController extends Controller {
    public function __construct(
        IRequest $request,
        private IUserSession $session,
        private IGroupManager $groups,
        private IUserManager $ncUsers,
        private Gateway $gateway,
        private IURLGenerator $urls,
        private IAppConfig $config,
    ) {
        parent::__construct(Application::APP_ID, $request);
    }

    #[NoAdminRequired]
    #[NoCSRFRequired]
    public function index(string $message = '', string $error = ''): TemplateResponse {
        $user = $this->session->getUser();
        $tenant = $user ? Application::tenantOf($this->groups, $user) : null;
        $sectors = [];
        if ($tenant !== null) {
            foreach ($this->groups->search($tenant . '-area-') as $group) {
                if (str_starts_with($group->getGID(), $tenant . '-area-')) {
                    $sectors[] = [
                        'name' => substr($group->getGID(), strlen($tenant . '-area-')),
                        'members' => $group->count(),
                    ];
                }
            }
        }
        $assistantUsers = [];
        $assistantMode = 'none';
        if ($tenant !== null) {
            $assistantGroup = $this->groups->get($tenant . '-servicio-asistente-ia');
            $adminGroup = $this->groups->get($tenant . '-administradores');
            foreach ($this->tenantUsers($tenant) as $member) {
                $isAdmin = $adminGroup !== null && $adminGroup->inGroup($member);
                if ($isAdmin) {
                    continue; // Los administradores tienen acceso siempre y no son seleccionables.
                }
                $assistantUsers[] = [
                    'uid' => (string)$member->getUID(),
                    'name' => $member->getDisplayName(),
                    'selected' => $assistantGroup !== null && $assistantGroup->inGroup($member),
                ];
            }
            // El modo elegido no depende de que la lista esté vacía ni de una sincronización posterior.
            $savedMode = $this->config->getValueString(Application::APP_ID, 'assistant_mode_' . $tenant, '');
            if (in_array($savedMode, ['all', 'none', 'custom'], true)) {
                $assistantMode = $savedMode;
            } elseif ($this->assistantAutoOn($tenant)) {
                $assistantMode = 'all';
            } elseif (array_filter($assistantUsers, fn ($member) => $member['selected'])) {
                $assistantMode = 'custom';
            }
        }
        return new TemplateResponse(Application::APP_ID, 'main', [
            'tenant' => $tenant, 'sectors' => $sectors, 'message' => $message, 'error' => $error,
            'assistantAvailable' => $tenant !== null && $this->assistantAvailable($tenant),
            'assistantMode' => $assistantMode,
            'assistantUsers' => $assistantUsers,
            'usersUrl' => $this->urls->linkTo('', 'index.php/settings/users'),
            'action' => $this->urls->linkToRoute('nexo_sync.page.create'),
            'toggleAssistantUrl' => $this->urls->linkToRoute('nexo_sync.page.toggleAssistant'),
        ]);
    }

    #[NoAdminRequired]
    public function create(string $name = ''): RedirectResponse {
        $user = $this->session->getUser();
        $tenant = $user ? Application::tenantOf($this->groups, $user) : null;
        $back = fn (array $q) => new RedirectResponse($this->urls->linkToRoute('nexo_sync.page.index', $q));
        if ($tenant === null) {
            return $back(['error' => 'Solo el administrador de la empresa puede crear sectores.']);
        }
        $slug = $this->slug($name);
        if ($slug === '') {
            return $back(['error' => 'Usa un nombre de 2 a 50 letras o números (ej. Psicología).']);
        }
        $gid = $tenant . '-area-' . $slug;
        if ($this->groups->groupExists($gid)) {
            return $back(['error' => 'El sector ya existe.']);
        }
        if (!$this->gateway->call($tenant, 'ensure_group', ['group' => $gid])) {
            return $back(['error' => 'No se pudo crear el sector en Keycloak.']);
        }
        $this->groups->createGroup($gid);
        $admins = $this->groups->get($tenant . '-administradores');
        foreach ($admins ? $admins->getUsers() : [] as $admin) {
            LoginListener::grantTenant($this->groups, $admin, $tenant);
        }
        return $back(['message' => "Sector «{$slug}» creado. Ya puedes elegirlo al crear usuarios en Cuentas."]);
    }

    /** El administrador da acceso a todos, a nadie o solo a usuarios seleccionados de su empresa. */
    #[NoAdminRequired]
    public function toggleAssistant(string $mode = '', array $users = []): RedirectResponse {
        $user = $this->session->getUser();
        $tenant = $user ? Application::tenantOf($this->groups, $user) : null;
        $back = fn (array $q) => new RedirectResponse($this->urls->linkToRoute('nexo_sync.page.index', $q));
        if ($tenant === null) {
            return $back(['error' => 'Solo el administrador de la empresa puede cambiar esta política.']);
        }
        if (!$this->assistantAvailable($tenant)) {
            return $back(['error' => 'El proveedor no ha habilitado el Asistente IA para esta empresa.']);
        }
        if (!in_array($mode, ['all', 'none', 'custom'], true)) {
            return $back(['error' => 'Selecciona un alcance de acceso válido.']);
        }

        $gid = $tenant . '-servicio-asistente-ia';
        if (!$this->ensureServiceGroup($gid)) {
            return $back(['error' => 'No se pudo preparar el grupo del Asistente IA en Keycloak.']);
        }
        $group = $this->groups->get($gid);
        if ($group === null) {
            return $back(['error' => 'No se pudo preparar el grupo del Asistente IA en Nextcloud.']);
        }

        $companyUsers = [];
        foreach ($this->tenantUsers($tenant) as $member) {
            $companyUsers[(string)$member->getUID()] = $member;
        }
        $requested = $mode === 'all' ? array_keys($companyUsers)
            : ($mode === 'custom' ? array_values(array_intersect(array_map('strval', $users), array_map('strval', array_keys($companyUsers)))) : []);
        $selected = array_fill_keys(array_map('strval', $requested), true);
        // El administrador conserva siempre el asistente, aunque elija «Nadie» para el resto.
        $adminGroup = $this->groups->get($tenant . '-administradores');
        foreach ($adminGroup ? $adminGroup->getUsers() : [] as $admin) {
            $uid = (string)$admin->getUID();
            $companyUsers[$uid] = $admin;
            $selected[$uid] = true;
        }

        // Incluye miembros antiguos del grupo para que «Nadie» también retire accesos residuales.
        foreach ($group->getUsers() as $member) {
            $companyUsers[(string)$member->getUID()] = $member;
        }
        foreach ($companyUsers as $uid => $member) {
            $allowed = isset($selected[(string)$uid]);
            if ($allowed && !$group->inGroup($member)) {
                $group->addUser($member);
            } elseif (!$allowed && $group->inGroup($member)) {
                $group->removeUser($member);
            }
        }

        $auto = array_values(array_diff(array_filter(array_map('trim', explode(',',
            $this->config->getValueString(Application::APP_ID, 'assistant_auto', '')))), [$tenant]));
        if ($mode === 'all') {
            $auto[] = $tenant; // Los usuarios nuevos heredan el acceso solamente en modo Todos.
        }
        $this->config->setValueString(Application::APP_ID, 'assistant_auto', implode(',', $auto));
        $this->config->setValueString(Application::APP_ID, 'assistant_mode_' . $tenant, $mode);
        return $back(['message' => 'Acceso al Asistente IA actualizado: ' . count($selected)
            . ' usuarios de ' . strtoupper($tenant) . ' tienen acceso.']);
    }

    private function ensureServiceGroup(string $gid): bool {
        if ($this->groups->groupExists($gid)) {
            return true;
        }
        $tenant = Gateway::tenantOfGroup($gid);
        if ($tenant === null || !$this->gateway->call($tenant, 'ensure_group', ['group' => $gid])) {
            return false;
        }
        return $this->groups->createGroup($gid) !== null;
    }

    /** Todos los usuarios de la empresa: administradores y sectores area-. */
    private function tenantUsers(string $tenant): array {
        $users = [];
        $adminGroup = $this->groups->get($tenant . '-administradores');
        if ($adminGroup !== null) {
            foreach ($adminGroup->getUsers() as $u) {
                $users[$u->getUID()] = $u;
            }
        }
        foreach ($this->groups->search($tenant . '-area-') as $group) {
            if (str_starts_with($group->getGID(), $tenant . '-area-')) {
                foreach ($group->getUsers() as $u) {
                    $users[$u->getUID()] = $u;
                }
            }
        }
        return array_values($users);
    }

    private function assistantAvailable(string $tenant): bool {
        $raw = $this->config->getValueString(Application::APP_ID, 'assistant_available', '');
        return in_array($tenant, array_filter(array_map('trim', explode(',', $raw))), true);
    }

    private function assistantAutoOn(string $tenant): bool {
        $raw = $this->config->getValueString(Application::APP_ID, 'assistant_auto', '');
        return in_array($tenant, array_filter(array_map('trim', explode(',', $raw))), true);
    }

    private function slug(string $name): string {
        $name = mb_strtolower(trim($name));
        $name = strtr($name, ['á' => 'a', 'é' => 'e', 'í' => 'i', 'ó' => 'o', 'ú' => 'u', 'ü' => 'u', 'ñ' => 'n']);
        $name = trim((string)preg_replace('/[^a-z0-9]+/', '-', $name), '-');
        return (strlen($name) >= 2 && strlen($name) <= 50) ? $name : '';
    }
}
