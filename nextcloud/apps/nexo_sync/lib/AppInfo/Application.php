<?php
declare(strict_types=1);

namespace OCA\NexoSync\AppInfo;

use OCA\NexoSync\Listener\LoginListener;
use OCA\NexoSync\Listener\UserSyncListener;
use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;
use OCP\Group\Events\UserAddedEvent;
use OCP\Group\Events\UserRemovedEvent;
use OCP\IGroupManager;
use OCP\INavigationManager;
use OCP\IURLGenerator;
use OCP\IUserSession;
use OCP\User\Events\PasswordUpdatedEvent;
use OCP\User\Events\PostLoginEvent;
use OCP\User\Events\UserChangedEvent;
use OCP\User\Events\UserCreatedEvent;
use OCP\User\Events\UserDeletedEvent;

class Application extends App implements IBootstrap {
    public const APP_ID = 'nexo_sync';

    public function __construct() {
        parent::__construct(self::APP_ID);
    }

    public function register(IRegistrationContext $context): void {
        foreach ([UserCreatedEvent::class, UserAddedEvent::class, UserRemovedEvent::class,
                  PasswordUpdatedEvent::class, UserDeletedEvent::class, UserChangedEvent::class] as $event) {
            $context->registerEventListener($event, UserSyncListener::class);
        }
        $context->registerEventListener(PostLoginEvent::class, LoginListener::class);
    }

    public function boot(IBootContext $context): void {
        $server = $context->getServerContainer();
        $server->get(INavigationManager::class)->add(function () use ($server) {
            $user = $server->get(IUserSession::class)->getUser();
            if ($user === null || self::tenantOf($server->get(IGroupManager::class), $user) === null) {
                return null;
            }
            $urls = $server->get(IURLGenerator::class);
            return [
                'id' => self::APP_ID, 'order' => 5,
                'href' => $urls->linkToRoute('nexo_sync.page.index'),
                'icon' => $urls->imagePath('core', 'places/contacts.svg'),
                'name' => 'Sectores y usuarios',
            ];
        });
    }

    public static function tenantOf(IGroupManager $groups, $user): ?string {
        foreach ($groups->getUserGroupIds($user) as $gid) {
            if (preg_match('/^([a-z][a-z0-9-]*?)-administradores$/', $gid, $m)) {
                return $m[1];
            }
        }
        return null;
    }
}
