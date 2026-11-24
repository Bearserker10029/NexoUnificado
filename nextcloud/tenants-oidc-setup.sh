#!/bin/sh
set -eu
cd /var/www/html
: "${KC_NEXTCLOUD_CLIENT_SECRET:?}" "${NEXO_URL:?}"

occ() {
  su -s /bin/sh www-data -c 'exec php occ "$@"' -- occ "$@"
}

i=0
until occ status --output=json 2>/dev/null | grep -q '"installed":true'; do
  i=$((i + 1)); [ "$i" -le 60 ] || exit 1
  sleep 5
done

php -r '
    $tenants = json_decode(file_get_contents("/tenants/registry.json"), true, 512, JSON_THROW_ON_ERROR)["tenants"];
    foreach ($tenants as $tenant) {
        echo $tenant["name"], PHP_EOL;
    }
' > /tmp/nexo-tenants.txt

while IFS= read -r tenant; do
  [ -n "$tenant" ] || continue
  echo "Configurando proveedor Nextcloud keycloak-${tenant}..."
  occ user_oidc:provider "keycloak-${tenant}" \
    --clientid='nextcloud' \
    --clientsecret="${KC_NEXTCLOUD_CLIENT_SECRET}" \
    --discoveryuri="http://keycloak:8080/realms/nexo-${tenant}/.well-known/openid-configuration"     --endsessionendpointuri="${NEXO_URL}/keycloak/realms/nexo-${tenant}/protocol/openid-connect/logout"     --postlogouturi="${NEXO_URL}/voip-sso/entrar?salir=1"     --send-id-token-hint=1 \
    --unique-uid=0 \
    --check-bearer=1 \
    --mapping-uid='preferred_username' \
    --mapping-display-name='name' \
    --mapping-email='email' \
    --mapping-groups='groups' \
    --group-provisioning=1 \
    --group-whitelist-regex="/^${tenant}-(servicio-|area-|administradores\$)/"
done < /tmp/nexo-tenants.txt

occ user_oidc:provider --output=json

# App que permite al administrador de empresa crear sectores y usuarios desde Nextcloud.
occ app:enable nexo_sync

# Grupos base de cada empresa (servicios y administradores) para poder delegarlos.
while IFS= read -r tenant; do
  [ -n "$tenant" ] || continue
  occ group:add "${tenant}-administradores" >/dev/null 2>&1 || true
done < /tmp/nexo-tenants.txt
php -r '
    foreach (json_decode(file_get_contents("/tenants/registry.json"), true)["tenants"] as $t) {
        foreach ($t["services"] ?? [] as $s) { echo $t["name"], "-servicio-", $s, PHP_EOL; }
    }
' | while IFS= read -r group; do occ group:add "$group" >/dev/null 2>&1 || true; done

# Cada empresa recibe entradas propias, visibles solo para sus grupos sincronizados.
php <<'PHP' > /tmp/nexo-tenant-sites.json
<?php
$tenants = json_decode(file_get_contents('/tenants/registry.json'), true, 512, JSON_THROW_ON_ERROR)['tenants'];
$sites = [];
$addSite = static function ($name, $url, $groups, $redirect, $icon) use (&$sites) {
    $id = count($sites) + 1;
    $sites[$id] = [
        'id' => $id, 'name' => $name, 'url' => $url, 'lang' => '', 'type' => 'link',
        'device' => '', 'icon' => $icon, 'groups' => $groups, 'redirect' => $redirect,
    ];
};
foreach ($tenants as $tenant) {
    $name = $tenant['name'];
    foreach ([
        'telefonia' => ['Telefonía', "/$name/voip/embed.html"],
        'videoconferencia' => ['Videoconferencia', "/$name/jitsi/"],
        'chat' => ['Chat', "/$name/element/"],
    ] as $service => [$label, $path]) {
        if (in_array($service, $tenant['services'] ?? [], true)) {
            $addSite($label . ' · ' . strtoupper($name), $path, ["$name-servicio-$service"], false, "nexo-$service.svg");
        }
    }
}
foreach ($tenants as $tenant) {
    $name = $tenant['name'];
    $groups = array_map(static fn ($service) => "$name-servicio-$service", $tenant['services'] ?? []);
    if ($groups) {
        $addSite('Asistente IA · ' . $tenant['display_name'], '/airi/?tenant=' . rawurlencode($name), $groups, false, 'nexo-asistente.svg');
    }
}
echo json_encode((object) $sites, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
PHP
# Iconos del menu: se copian al almacenamiento de External Sites (blanco y variante -dark para tema claro).
cat > /tmp/nexo-icons.php <<'PHP'
<?php
define('OC_CONSOLE', 1);
require_once '/var/www/html/lib/base.php';
$appData = \OCP\Server::get(\OCP\Files\IAppDataFactory::class)->get('external');
try {
    $folder = $appData->getFolder('icons');
} catch (\OCP\Files\NotFoundException $e) {
    $folder = $appData->newFolder('icons');
}
foreach (glob('/nexo-icons/nexo-*.svg') as $file) {
    $name = basename($file);
    $content = file_get_contents($file);
    try {
        $folder->getFile($name)->putContent($content);
    } catch (\OCP\Files\NotFoundException $e) {
        $folder->newFile($name)->putContent($content);
    }
}
PHP
chmod 644 /tmp/nexo-icons.php
su -s /bin/sh www-data -c 'php /tmp/nexo-icons.php'
occ config:app:set external sites --value="$(cat /tmp/nexo-tenant-sites.json)"
occ config:app:set external max_site --value="$(php -r 'echo count(json_decode(file_get_contents("/tmp/nexo-tenant-sites.json"), true, 512, JSON_THROW_ON_ERROR));')"
