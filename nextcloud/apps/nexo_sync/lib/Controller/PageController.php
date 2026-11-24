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
use OCP\IGroupManager;
use OCP\IRequest;
use OCP\IURLGenerator;
use OCP\IUserSession;

class PageController extends Controller {
    public function __construct(
        IRequest $request,
        private IUserSession $session,
        private IGroupManager $groups,
        private Gateway $gateway,
        private IURLGenerator $urls,
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
        return new TemplateResponse(Application::APP_ID, 'main', [
            'tenant' => $tenant, 'sectors' => $sectors, 'message' => $message, 'error' => $error,
            'usersUrl' => $this->urls->linkTo('', 'index.php/settings/users'),
            'action' => $this->urls->linkToRoute('nexo_sync.page.create'),
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

    private function slug(string $name): string {
        $name = mb_strtolower(trim($name));
        $name = strtr($name, ['á' => 'a', 'é' => 'e', 'í' => 'i', 'ó' => 'o', 'ú' => 'u', 'ü' => 'u', 'ñ' => 'n']);
        $name = trim((string)preg_replace('/[^a-z0-9]+/', '-', $name), '-');
        return (strlen($name) >= 2 && strlen($name) <= 50) ? $name : '';
    }
}
