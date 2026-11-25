<?php
declare(strict_types=1);

namespace OCA\NexoSync\Listener;

use OCA\NexoSync\AppInfo\Application;
use OCA\NexoSync\Service\Gateway;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\IGroupManager;
use OCP\IUserSession;
use OCP\User\Events\BeforeUserCreatedEvent;

/** Rejects company user IDs that cannot be provisioned as matching Keycloak identities. */
class UserCreationPolicyListener implements IEventListener {
	public function __construct(
		private IUserSession $session,
		private IGroupManager $groups,
	) {
	}

	public function handle(Event $event): void {
		if (!$event instanceof BeforeUserCreatedEvent) {
			return;
		}

		$creator = $this->session->getUser();
		$tenant = $creator === null ? null : Application::tenantOf($this->groups, $creator);
		if ($tenant === null) {
			return;
		}

		if (!Gateway::validTenantUsername($tenant, $event->getUid())) {
			throw new \InvalidArgumentException(
				'No se creó la cuenta. El identificador debe empezar por "' . $tenant
				. '.", ir en minúsculas y usar solo letras, números, punto, guion o guion bajo '
				. '(por ejemplo, "' . $tenant . '.quillas"). El nombre mostrado sí puede llevar espacios.'
			);
		}
	}
}
