<?php
declare(strict_types=1);

namespace OCA\NexoSync\Listener;

use OCP\Collaboration\AutoComplete\AutoCompleteFilterEvent;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\IGroupManager;
use OCP\IUserManager;
use OCP\IUserSession;
use OCP\Share\IShare;

/** Limits local people and groups returned by Nextcloud's collaborator search to the current tenant. */
class MemberSearchListener implements IEventListener {
	public function __construct(
		private IUserSession $session,
		private IGroupManager $groups,
		private IUserManager $users,
	) {
	}

	public function handle(Event $event): void {
		if (!$event instanceof AutoCompleteFilterEvent) {
			return;
		}

		$user = $this->session->getUser();
		$tenant = $user === null ? null : $this->tenantOf($user->getUID());
		if ($tenant === null) {
			return;
		}

		$results = $event->getResults();
		foreach ($results as $section => $matches) {
			if (!is_array($matches)) {
				continue;
			}
			$results[$section] = array_values(array_filter($matches, function ($match) use ($tenant): bool {
				$value = $match['value'] ?? null;
				if (!is_array($value)) {
					return true;
				}
				$id = (string)($value['shareWith'] ?? '');
				switch ((int)($value['shareType'] ?? -1)) {
					case IShare::TYPE_USER:
						return $this->tenantOf($id) === $tenant;
					case IShare::TYPE_GROUP:
						return $this->tenantOfGroup($id) === $tenant;
					default:
						return true;
				}
			}));
		}
		$event->setResults($results);
	}

	private function tenantOf(string $uid): ?string {
		$user = $this->users->get($uid);
		if ($user === null) {
			return null;
		}
		foreach ($this->groups->getUserGroupIds($user) as $gid) {
			$tenant = $this->tenantOfGroup($gid);
			if ($tenant !== null) {
				return $tenant;
			}
		}
		return null;
	}

	private function tenantOfGroup(string $gid): ?string {
		return preg_match('/^([a-z][a-z0-9-]*?)-(?:area-.+|servicio-[a-z0-9-]+|administradores)$/', $gid, $m)
			? $m[1]
			: null;
	}
}
