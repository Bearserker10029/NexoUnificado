<?php
declare(strict_types=1);

namespace OCA\NexoSync\Listener;

use OCA\Circles\Db\MemberRequest;
use OCA\Circles\Events\AddingCircleMemberEvent;
use OCA\Circles\Model\Member;
use OCP\EventDispatcher\Event;
use OCP\EventDispatcher\IEventListener;
use OCP\IGroupManager;
use OCP\IUserManager;
use Psr\Log\LoggerInterface;

/**
 * Aislamiento multiempresa en Teams (circles).
 *
 * Los usuarios y grupos solo pueden añadirse a Teams de su empresa. La
 * colaboración externa se gestiona con invitaciones explícitas de Circles a
 * usuarios concretos, autorizadas por el administrador de ese Team.
 *
 * Valida usuarios y GRUPOS. Los miembros de tipo Team anidado, contacto o
 * correo quedan fuera del alcance.
 *
 * AddingCircleMemberEvent se dispara DESPUÉS de insertar la membresía, entonces
 * ante una violación el miembro se revoca en lugar de abortarse el alta. La
 * revocación usa MemberRequest::delete directo porque removeMember() de
 * circles re-fetchea el miembro sin su círculo y falla con getCircle() null.
 */
class TeamsListener implements IEventListener {
    public function __construct(
        private IGroupManager $groups,
        private IUserManager $users,
        private LoggerInterface $logger,
        private MemberRequest $memberRequest,
    ) {
    }

    public function handle(Event $event): void {
        if (!($event instanceof AddingCircleMemberEvent)) {
            return;
        }
        $member = $event->getMember();
        $this->logger->info('nexo_sync: TeamsListener disparado, tipo de miembro ' . $member->getUserType());

        if (!in_array($member->getUserType(), [Member::TYPE_USER, Member::TYPE_GROUP], true)) {
            return; // teams anidados, contactos y correos: fuera del alcance
        }

        $ownerTenant = $this->tenantOf($event->getCircle()->getOwner()->getUserId());
        if ($ownerTenant === null) {
            return; // Team de la plataforma (nexo): sin restricción
        }

        $memberTenant = $member->getUserType() === Member::TYPE_GROUP
            ? $this->tenantOfGroup($member->getUserId())
            : $this->tenantOf($member->getUserId());

        if ($memberTenant === $ownerTenant) {
            return; // mismo tenant, siempre permitido
        }

        // Una invitación federada puede llegar a esta instancia desde el
        // flujo explícito de colaboración de Circles. Usuarios/grupos locales
        // de otro tenant se bloquean; nunca se habilitan por una política global.
        if (!$member->isLocal()) {
            return;
        }

        $this->memberRequest->delete($member);
        $this->logger->info('nexo_sync: bloqueado miembro local de otra empresa en un Team: ' . $member->getUserId());
    }

    /** Tenant de un uid según sus grupos nexo, o null si no pertenece a ninguna empresa. */
    private function tenantOf(string $uid): ?string {
        $user = $this->users->get($uid);
        if ($user === null) {
            return null;
        }
        foreach ($this->groups->getUserGroupIds($user) as $gid) {
            if (preg_match('/^([a-z][a-z0-9-]*?)-(?:area-.+|servicio-[a-z0-9-]+|administradores)$/', $gid, $m)) {
                return $m[1];
            }
        }
        return null;
    }

    /** Tenant de un gid de grupo nexo (empresa-area-*, empresa-servicio-*, empresa-administradores). */
    private function tenantOfGroup(string $gid): ?string {
        return preg_match('/^([a-z][a-z0-9-]*?)-(?:area-.+|servicio-[a-z0-9-]+|administradores)$/', $gid, $m)
            ? $m[1]
            : null;
    }

}
