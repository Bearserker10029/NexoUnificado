<?php
declare(strict_types=1);

namespace OCA\NexoSync\Listener;

use OCA\NexoSync\Service\Gateway;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\Group\Events\UserAddedEvent;
use OCP\Group\Events\UserRemovedEvent;
use OCP\IGroupManager;
use OCP\User\Events\PasswordUpdatedEvent;
use OCP\User\Events\UserChangedEvent;
use OCP\User\Events\UserCreatedEvent;
use OCP\User\Events\UserDeletedEvent;

/** Replica a Keycloak las altas, bajas y cambios de sector hechos desde Cuentas de Nextcloud. */
class UserSyncListener implements IEventListener {
    public function __construct(private Gateway $gateway, private IGroupManager $groups) {
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
            foreach ($this->tenantsOf($event->getUser()) as $tenant) {
                $this->gateway->call($tenant, 'set_password', [
                    'username' => $event->getUser()->getUID(), 'password' => $event->getPassword(),
                ]);
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
        } elseif ($event instanceof UserDeletedEvent) {
            foreach ($this->tenantsOf($event->getUser()) as $tenant) {
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
            $this->gateway->call($tenant, 'ensure_user', [
                'username' => $uid,
                'display_name' => $user->getDisplayName(),
                'email' => $user->getEMailAddress() ?: null,
                'password' => $password,
            ]);
            Gateway::forget($uid);
        }
        $this->gateway->call($tenant, 'set_membership', ['username' => $uid, 'group' => $gid, 'member' => $member]);
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
