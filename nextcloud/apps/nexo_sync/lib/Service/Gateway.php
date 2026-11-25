<?php
declare(strict_types=1);

namespace OCA\NexoSync\Service;

use OCP\Http\Client\IClientService;
use Psr\Log\LoggerInterface;

/** Cliente del endpoint interno /internal/sync de voip-gateway. */
class Gateway {
    /** Contraseñas recién creadas, válidas solo durante la petición actual. */
    private static array $pending = [];

    /** true mientras la app fija la clave local aleatoria: ese cambio no debe viajar a Keycloak. */
    public static bool $suppress = false;

    public function __construct(private IClientService $clients, private LoggerInterface $logger) {
    }

    public static function remember(string $uid, string $password): void {
        self::$pending[$uid] = $password;
    }

    public static function pending(string $uid): ?string {
        return self::$pending[$uid] ?? null;
    }

    public static function forget(string $uid): void {
        unset(self::$pending[$uid]);
    }

    /** Empresas de un usuario que se va a borrar (los grupos desaparecen antes del evento final). */
    private static array $tenants = [];

    public static function rememberTenants(string $uid, array $tenants): void {
        self::$tenants[$uid] = $tenants;
    }

    /** @return string[] */
    public static function forgetTenants(string $uid): array {
        $tenants = self::$tenants[$uid] ?? [];
        unset(self::$tenants[$uid]);
        return $tenants;
    }

    /** @return string|null empresa si el grupo es empresa-area-*, empresa-servicio-* o empresa-administradores. */
    public static function tenantOfGroup(string $gid): ?string {
        return preg_match('/^([a-z][a-z0-9-]*?)-(?:area-.+|servicio-[a-z0-9-]+|administradores)$/', $gid, $m) ? $m[1] : null;
    }

    /** UID compatible con Keycloak y aislado por tenant para el login OIDC de Nextcloud. */
    public static function validTenantUsername(string $tenant, string $uid): bool {
        return preg_match('/^' . preg_quote($tenant, '/') . '[._-][a-z0-9][a-z0-9._-]{0,58}$/D', $uid) === 1;
    }

    public function call(string $tenant, string $action, array $fields = []): bool {
        $secret = (string)getenv('NEXO_SYNC_SECRET');
        $url = (string)(getenv('NEXO_SYNC_URL') ?: 'http://voip-gateway:5000/internal/sync');
        if ($secret === '') {
            $this->logger->error('nexo_sync: NEXO_SYNC_SECRET no está definido');
            return false;
        }
        try {
            $this->clients->newClient()->post($url, [
                'headers' => ['X-Nexo-Sync-Secret' => $secret],
                'json' => ['tenant' => $tenant, 'action' => $action] + $fields,
                'timeout' => 20,
                'nextcloud' => ['allow_local_address' => true],
            ]);
            return true;
        } catch (\Throwable $e) {
            $this->logger->error('nexo_sync: fallo al sincronizar ' . $action . ' con Keycloak: ' . $e->getMessage());
            return false;
        }
    }
}
