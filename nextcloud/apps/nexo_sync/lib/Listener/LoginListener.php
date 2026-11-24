<?php
declare(strict_types=1);

namespace OCA\NexoSync\Listener;

use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\IGroupManager;
use OCP\User\Events\PostLoginEvent;

/** El administrador de una empresa es subadministrador de todos los grupos de su empresa. */
class LoginListener implements IEventListener {
    public function __construct(private IGroupManager $groups) {
    }

    public function handle(Event $event): void {
        if (!($event instanceof PostLoginEvent)) {
            return;
        }
        $user = $event->getUser();
        foreach ($this->groups->getUserGroupIds($user) as $gid) {
            if (preg_match('/^([a-z][a-z0-9-]*?)-administradores$/', $gid, $m)) {
                self::grantTenant($this->groups, $user, $m[1]);
            }
        }
    }

    public static function grantTenant(IGroupManager $groups, $user, string $tenant): void {
        $subAdmin = $groups->getSubAdmin();
        foreach ($groups->search($tenant . '-') as $group) {
            $gid = $group->getGID();
            if (!preg_match('/^' . preg_quote($tenant, '/') . '-(area|servicio)-/', $gid)) {
                continue;
            }
            if (!$subAdmin->isSubAdminOfGroup($user, $group)) {
                $subAdmin->createSubAdmin($user, $group);
            }
        }
    }
}
