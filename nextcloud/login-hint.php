<?php
declare(strict_types=1);

// Nexo: user_oidc no reenvía login_hint; lo añade sin sustituir el controlador completo.
$path = '/var/www/html/custom_apps/user_oidc/lib/Controller/LoginController.php';
$source = file_get_contents($path);
if ($source === false) {
    fwrite(STDERR, "No se pudo leer $path\n");
    exit(1);
}
if (str_contains($source, "Nexo: reenviar login_hint")) {
    echo "El reenvío de login_hint ya estaba configurado.\n";
    exit(0);
}
$needle = "\t\$authorizationUrl = \$this->discoveryService->buildAuthorizationUrl(\$discovery['authorization_endpoint'], \$data);";
$patch = <<<'PHP'
	// Nexo: reenviar login_hint para que Keycloak precargue el usuario o correo introducido.
	$loginHint = $this->request->getParam('login_hint', '');
	if (is_string($loginHint) && $loginHint !== '' && strlen($loginHint) <= 254) {
		$data['login_hint'] = $loginHint;
	}

PHP;
$updated = str_replace($needle, $patch . $needle, $source, $count);
if ($count !== 1) {
    fwrite(STDERR, "No se encontró el punto esperado de user_oidc; no se modificó el archivo.\n");
    exit(1);
}
$temporary = $path . '.nexo-tmp';
if (file_put_contents($temporary, $updated) === false || !rename($temporary, $path)) {
    fwrite(STDERR, "No se pudo actualizar $path\n");
    @unlink($path . '.nexo-tmp');
    exit(1);
}
chmod($path, 0644);
echo "Reenvío de login_hint configurado.\n";
