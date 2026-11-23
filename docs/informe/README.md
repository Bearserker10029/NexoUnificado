# Informe consolidado – Nexo Unificado (TEL139, PUCP)

Estructura del informe final. Cada archivo se completa por su responsable;
los campos marcados `[COMPLETAR]` no se inventan: se llenan con el reparto
real de la TA3 y con lo que cada integrante efectivamente probó.

| Orden | Archivo | Contenido | Responsable |
|-------|---------|-----------|-------------|
| 1 | [01-resumen-ejecutivo.md](01-resumen-ejecutivo.md) | Qué se entrega, para quién y con qué alcance real | [COMPLETAR] |
| 2 | [02-sla-mype.md](02-sla-mype.md) | SLA acordado con la MYPE y cómo se mide | [COMPLETAR] |
| 3 | [03-reparto-ta3.md](03-reparto-ta3.md) | Tabla integrante ↔ hitos (según TA3) | [COMPLETAR] |
| 4 | [integrantes/](integrantes/) | Una sección por integrante (memoria + comentario personal) | cada integrante |
| 5 | [04-limites-y-pendientes.md](04-limites-y-pendientes.md) | Límites reales de las pruebas, consolidados | [COMPLETAR] |

## Reglas de redacción

1. Memoria técnica en tercera persona o impersonal; comentario personal en
   **primera persona**.
2. Toda afirmación apunta a una evidencia (`evidencias/<hito>/…`). Sin
   evidencia, se escribe "no verificado".
3. Declarar los límites: entorno local con Docker Compose, sin laboratorio
   físico, tráfico simulado, certificado autofirmado, rendimiento medido en
   una sola máquina.
4. No pegar secretos, claves ni tokens. Usar `<PLACEHOLDER>`.
5. Una prueba que falló o quedó pendiente se informa como tal.

## Cómo agregar un integrante

Copiar [integrantes/_plantilla.md](integrantes/_plantilla.md) a
`integrantes/<nombre-apellido>.md` y completarla.
