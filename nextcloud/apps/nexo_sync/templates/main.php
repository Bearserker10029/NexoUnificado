<?php
/** @var array $_ */
style('nexo_sync', 'main');
script('nexo_sync', 'main');
?>
<div id="nexo-sync">
<?php if ($_['tenant'] === null): ?>
    <div class="nx-card nx-empty">
        <h3>Acceso restringido</h3>
        <p class="nx-hint">Esta sección es solo para administradores de empresa.</p>
    </div>
<?php else: ?>
    <header class="nx-header">
        <h2>Sectores y usuarios</h2>
        <span class="nx-tenant"><?php p(strtoupper($_['tenant'])) ?></span>
    </header>

    <?php if ($_['message'] !== ''): ?><p class="nx-banner ok" role="status"><?php p($_['message']) ?></p><?php endif; ?>
    <?php if ($_['error'] !== ''): ?><p class="nx-banner err" role="alert"><?php p($_['error']) ?></p><?php endif; ?>

    <div class="nx-grid">
        <section class="nx-card nx-assistant">
            <h3>Asistente IA</h3>
            <?php if (!$_['assistantAvailable']): ?>
                <span class="nx-pill off">No habilitado por el proveedor</span>
                <p class="nx-hint nx-provider-note">El proveedor del servicio debe habilitar esta función para <?php p(strtoupper($_['tenant'])) ?>.</p>
            <?php else: ?>
                <p class="nx-hint">El proveedor habilitó la función. Elige qué usuarios de <?php p(strtoupper($_['tenant'])) ?> pueden utilizarla.</p>
                <form method="post" action="<?php p($_['toggleAssistantUrl']) ?>" class="nx-access-form">
                    <input type="hidden" name="requesttoken" value="<?php p($_['requesttoken']) ?>">
                    <label><input type="radio" name="mode" value="all" <?php p($_['assistantMode'] === 'all' ? 'checked' : '') ?>> Todos</label>
                    <?php if ($_['assistantUsers']): ?>
                        <button id="nx-open-assistant-users" type="button" class="nx-select-users">Solo usuarios seleccionados</button>
                    <?php else: ?>
                        <span class="nx-no-users">Solo usuarios seleccionados</span>
                    <?php endif; ?>
                    <label><input type="radio" name="mode" value="none" <?php p($_['assistantMode'] === 'none' ? 'checked' : '') ?>> Nadie</label>
                    <?php if ($_['assistantUsers']): ?>
                        <dialog id="nx-assistant-users" class="nx-dialog" aria-labelledby="nx-dialog-title">
                            <h3 id="nx-dialog-title">Usuarios con acceso al Asistente IA</h3>
                            <p class="nx-hint">Los administradores no aparecen porque siempre tienen acceso.</p>
                            <fieldset class="nx-user-list">
                                <legend class="nx-visually-hidden">Usuarios disponibles</legend>
                                <?php foreach ($_['assistantUsers'] as $member): ?>
                                    <label>
                                        <input type="checkbox" name="users[]" value="<?php p($member['uid']) ?>" <?php p($member['selected'] ? 'checked' : '') ?>>
                                        <?php p($member['name']) ?> (<?php p($member['uid']) ?>)
                                    </label>
                                <?php endforeach; ?>
                            </fieldset>
                            <button type="button" class="primary" data-close-dialog>Listo</button>
                        </dialog>
                    <?php else: ?>
                        <p class="nx-hint nx-no-users">Todavía no hay usuarios no administradores para asignar.</p>
                    <?php endif; ?>
                    <button class="primary">Guardar acceso</button>
                </form>
            <?php endif; ?>
        </section>

        <section class="nx-card">
            <h3>Crear sector</h3>
            <form method="post" action="<?php p($_['action']) ?>" class="nx-form">
                <input type="hidden" name="requesttoken" value="<?php p($_['requesttoken']) ?>">
                <label for="nx-sector">Nombre del sector (psicología, administración, asuntos generales…)</label>
                <div class="nx-row">
                    <input id="nx-sector" type="text" name="name" maxlength="50" required>
                    <button class="primary">Crear sector</button>
                    <button id="nx-open-sectors" type="button">Ver sectores</button>
                </div>
                <p class="nx-hint nx-sector-count"><?php p(count($_['sectors'])) ?> sectores creados en <?php p(strtoupper($_['tenant'])) ?>.</p>
                <dialog id="nx-sectors" class="nx-dialog" aria-labelledby="nx-sectors-title">
                    <h3 id="nx-sectors-title">Sectores existentes</h3>
                    <?php if (!$_['sectors']): ?>
                        <p class="nx-hint">Todavía no hay sectores. Crea el primero desde la tarjeta «Crear sector».</p>
                    <?php else: ?>
                        <div class="nx-sector-table">
                            <table class="nx-table">
                                <thead><tr><th>Sector</th><th>Usuarios</th></tr></thead>
                                <tbody>
                                    <?php foreach ($_['sectors'] as $s): ?>
                                    <tr>
                                        <td><span class="nx-sector"><?php p($s['name']) ?></span></td>
                                        <td><?php p($s['members']) ?></td>
                                    </tr>
                                    <?php endforeach; ?>
                                </tbody>
                            </table>
                        </div>
                    <?php endif; ?>
                    <button type="button" class="primary" data-close-dialog>Cerrar</button>
                </dialog>
            </form>
        </section>

        <section class="nx-card">
            <h3>Crear usuarios</h3>
            <p class="nx-hint">En Cuentas, el identificador debe empezar por <?php p($_['tenant']) ?>. y usar minúsculas sin espacios (por ejemplo, <?php p($_['tenant']) ?>.nombre). Nextcloud rechazará el alta si no cumple el formato de acceso de la empresa. El nombre mostrado sí puede tener espacios, como «Quillas ACME». Después elige el sector en «Grupos» y define una contraseña temporal; la persona la cambiará al entrar con SSO.</p>
            <a class="button primary" href="<?php p($_['usersUrl']) ?>">Abrir Cuentas</a>
        </section>
    </div>
<?php endif; ?>
</div>
