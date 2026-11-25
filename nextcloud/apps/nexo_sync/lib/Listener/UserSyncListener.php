<?php
declare(strict_types=1);

namespace OCA\NexoSync\Listener;

use OCA\NexoSync\Service\Gateway;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Group\Events\UserAddedEvent;
use OCP\Group\Events\UserRemovedEvent;
use OCP\IAppConfig;
use OCP\IGroupManager;
use OCP\User\Events\PasswordUpdatedEvent;
use OCP\User\Events\UserChangedEvent;
use OCP\User\Events\BeforeUserDeletedEvent;
use OCP\User\Events\UserCreatedEvent;
use OCP\User\Events\UserDeletedEvent;
use Psr\Log\LoggerInterface;

/** Replica a Keycloak las altas, bajas y cambios de sector hechos desde Cuentas de Nextcloud. */
class UserSyncListener implements IEventListener {
    public function __construct(
        private Gateway $gateway,
        private IGroupManager $groups,
        private IAppConfig $config,
        private LoggerInterface $logger,
    ) {
    }

    public function handle(Event $event): void {
        if ($event instanceof UserCreatedEvent) {
            // Los grupos se añaden justo después; se espera a conocer la empresa.
            Gateway::remember($event->getUser()->getUID(), $event->getPassword());
        } elseif ($event instanceof UserAddedEvent) {
            $this->membership($event->getUser(), $event->getGroup()->getGID(), true);
        } elseif ($event instanceof UserRemovedEvent) {
            $this->membership($event->getUser(), $event->getGroup()->getGID(), false);
        } elseif ($event instanceof PasswordUpdatedEvent) {
            if (Gateway::$suppress) {
                return;
            }
            $synced = false;
            foreach ($this->tenantsOf($event->getUser()) as $tenant) {
                $synced = $this->gateway->call($tenant, 'set_password', [
                    'username' => $event->getUser()->getUID(), 'password' => $event->getPassword(),
                ]) || $synced;
            }
            if ($synced) {
                $this->lockLocalPassword($event->getUser());
            }
        } elseif ($event instanceof UserChangedEvent) {
            // Nextcloud fija nombre y correo después de añadir los grupos.
            if (in_array($event->getFeature(), ['displayName', 'eMailAddress'], true)) {
                foreach ($this->tenantsOf($event->getUser()) as $tenant) {
                    $this->gateway->call($tenant, 'update_user', [
                        'username' => $event->getUser()->getUID(),
                        'display_name' => $event->getUser()->getDisplayName(),
                        'email' => $event->getUser()->getEMailAddress() ?: null,
                    ]);
                }
            }
        } elseif ($event instanceof BeforeUserDeletedEvent) {
            // Al borrar, los grupos ya no existen: se guardan las empresas antes.
            Gateway::rememberTenants($event->getUser()->getUID(), $this->tenantsOf($event->getUser()));
        } elseif ($event instanceof UserDeletedEvent) {
            foreach (Gateway::forgetTenants($event->getUser()->getUID()) as $tenant) {
                $this->gateway->call($tenant, 'delete_user', ['username' => $event->getUser()->getUID()]);
            }
        }
    }

    private function membership($user, string $gid, bool $member): void {
        $tenant = Gateway::tenantOfGroup($gid);
        if ($tenant === null) {
            return;
        }
        $uid = $user->getUID();
        $password = Gateway::pending($uid);
        if ($member && $password !== null) {
            if (!Gateway::validTenantUsername($tenant, $uid)) {
                $this->logger->error('nexo_sync: alta detenida; el UID ' . $uid . ' no cumple el formato de usuario de ' . $tenant);
                return;
            }
            $created = $this->gateway->call($tenant, 'ensure_user', [
                'username' => $uid,
                'display_name' => $user->getDisplayName(),
                'email' => $user->getEMailAddress() ?: null,
                'password' => $password,
            ]);
            if (!$created) {
                $this->logger->error('nexo_sync: no se pudo aprovisionar ' . $uid . ' en Keycloak; no se sincronizaron sus grupos');
                return;
            }
            Gateway::forget($uid);
            $this->lockLocalPassword($user);
        }
        if (!$this->gateway->call($tenant, 'set_membership', ['username' => $uid, 'group' => $gid, 'member' => $member])) {
            $this->logger->error('nexo_sync: no se pudo sincronizar el grupo ' . $gid . ' para ' . $uid);
        }
        if ($member && preg_match('/-(?:area-.+|administradores)$/', $gid)) {
            $this->inheritAssistant($user, $tenant);
        }
    }

    /** En modo Todos, cada usuario nuevo de la empresa hereda el acceso al asistente. */
    private function inheritAssistant($user, string $tenant): void {
        $raw = $this->config->getValueString('nexo_sync', 'assistant_auto', '');
        if (!in_array($tenant, array_filter(array_map('trim', explode(',', $raw))), true)) {
            return;
        }
        $group = $this->groups->get($tenant . '-servicio-asistente-ia');
        if ($group !== null && !$group->inGroup($user)) {
            $group->addUser($user);
        }
    }

    /**
     * La identidad vive en Keycloak. Tras sincronizar, la clave local de Nextcloud pasa a un valor
     * aleatorio que nadie conoce: así no se puede entrar por el formulario local (/docs/admin-login)
     * con la clave inicial y saltarse el SSO, el cambio de clave obligatorio ni el segundo factor.
     */
    private function lockLocalPassword($user): void {
        Gateway::$suppress = true;
        try {
            $user->setPassword(bin2hex(random_bytes(32)));
        } finally {
            Gateway::$suppress = false;
        }
    }

    /** @return string[] */
    private function tenantsOf($user): array {
        $tenants = [];
        foreach ($this->groups->getUserGroupIds($user) as $gid) {
            if ($tenant = Gateway::tenantOfGroup($gid)) {
                $tenants[$tenant] = true;
            }
        }
        return array_keys($tenants);
    }
}
