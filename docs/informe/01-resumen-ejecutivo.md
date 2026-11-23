# 1. Resumen ejecutivo

> Máximo una página. Escribir al final, cuando los hitos estén cerrados.

## Problema y cliente
[COMPLETAR: MYPE, necesidad, contexto.]

## Solución entregada
Plataforma de comunicaciones unificadas ejecutada con Docker Compose:
telefonía (Asterisk), mensajería (Synapse + Element), videoconferencia
(Jitsi), archivos y edición compartida (Nextcloud + Collabora), tras proxy
Nginx con TLS en 8443 y acceso único (SSO) con Keycloak.

## Resultados por hito
| Hito | Tema | Estado (cumplido / parcial / pendiente) | Evidencia |
|------|------|------------------------------------------|-----------|
| H5 | Edición simultánea | [COMPLETAR] | `evidencias/h5/` |
| H7 | MFA (TOTP) con SSO | [COMPLETAR] | `evidencias/h7/` |
| H14 | Antivirus (ClamAV) | [COMPLETAR] | `evidencias/h14/` |
| [COMPLETAR] | [COMPLETAR] | [COMPLETAR] | [COMPLETAR] |

## Límites generales
Ver [04-limites-y-pendientes.md](04-limites-y-pendientes.md).
