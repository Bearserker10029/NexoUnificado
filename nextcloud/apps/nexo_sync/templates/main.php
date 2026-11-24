<?php
/** @var array $_ */
style('nexo_sync', 'main');
?>
<div id="nexo-sync">
<?php if ($_['tenant'] === null): ?>
    <h2>Acceso restringido</h2>
    <p>Esta sección es solo para administradores de empresa.</p>
<?php else: ?>
    <h2>Sectores y usuarios · <?php p(strtoupper($_['tenant'])) ?></h2>
    <?php if ($_['message'] !== ''): ?><p class="ok" role="status"><?php p($_['message']) ?></p><?php endif; ?>
    <?php if ($_['error'] !== ''): ?><p class="err" role="alert"><?php p($_['error']) ?></p><?php endif; ?>

    <h3>Crear sector</h3>
    <form method="post" action="<?php p($_['action']) ?>">
        <input type="hidden" name="requesttoken" value="<?php p($_['requesttoken']) ?>">
        <label>Nombre del sector (psicología, administración, asuntos generales…)
            <input name="name" maxlength="50" required>
        </label>
        <button class="primary">Crear sector</button>
    </form>

    <h3>Sectores existentes</h3>
    <?php if (!$_['sectors']): ?><p>Todavía no hay sectores.</p><?php else: ?>
    <table><thead><tr><th>Sector</th><th>Usuarios</th></tr></thead><tbody>
        <?php foreach ($_['sectors'] as $s): ?>
        <tr><td><?php p($s['name']) ?></td><td><?php p($s['members']) ?></td></tr>
        <?php endforeach; ?>
    </tbody></table>
    <?php endif; ?>

    <h3>Crear usuarios</h3>
    <p>Abre <a href="<?php p($_['usersUrl']) ?>">Cuentas</a>, pulsa «Cuenta nueva», elige el sector en
       «Grupos» y define una contraseña temporal. La persona entra con SSO y debe cambiarla en el primer acceso.</p>
<?php endif; ?>
</div>
