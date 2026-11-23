<!-- SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
     SPDX-License-Identifier: Apache-2.0 -->
# Asistente IA

El [registro de empresas](../../tenants/registry.json) habilita `ai_provider: "gemini"` para ACME. BETA sirve para comprobar el estado deshabilitado.

## Evidencias

- [Chat de ACME con una respuesta real de Gemini 3.5 Flash-Lite](chat-gemini.png).
- [Reproductor de la respuesta](audio-pocket-tts.png) y [grabación WAV en español, generada por Pocket TTS](respuesta-pocket-tts.wav).
- [Entrada Asistente IA · ACME en el menú de Nextcloud](menu-nextcloud.png). Al pulsarla, Keycloak reutilizó la sesión y abrió el chat sin pedir credenciales de nuevo.

Copyright 2026 Kent Lin, Luis Quillas, Jeniffer Castillo. Las evidencias del grupo se entregan bajo Apache-2.0.

## Despliegue y comprobación

Define `GEMINI_API_KEY` en el `.env` del servidor. `GEMINI_MODEL` usa `gemini-3.5-flash-lite` por defecto. Genera un valor aleatorio para `AI_SESSION_SECRET` si quieres conservar las sesiones al recrear el backend. Arranca el despliegue con `docker compose up -d --build`. La primera vez Pocket TTS descarga los pesos de español y la voz Lola de Kyutai a un volumen persistente. Compose expone los servicios del asistente por la ruta HTTPS `/airi/` del proxy.

1. Entra en Nextcloud con el proveedor `keycloak-acme` y un usuario del realm `nexo-acme` que pertenezca a uno de los grupos de servicio de ACME.
2. Abre **Asistente IA · ACME**. Keycloak reutiliza la sesión del navegador. Envía «¿Qué es una central telefónica IP?». Cuando llegue la respuesta de Gemini, guarda una captura con la pregunta y el texto.
3. Reproduce el audio. Si el navegador bloquea el inicio automático, pulsa el control de reproducción. Guarda la grabación o el WAV de la respuesta y una captura de la entrada del menú.
4. Repite el acceso con `keycloak-beta` y comprueba que BETA muestre el asistente deshabilitado.

Para habilitar otra empresa, agrega el campo `ai_provider` a su entrada en el registro. Para deshabilitarla, elimina el campo o usa `null`. Si das de alta una empresa nueva, puedes usar `python scripts/nexo-tenant.py add nombre --range-prefix 3 --ai-provider gemini`, con un prefijo libre, y volver a levantar Compose.

## Decisión de interfaz

Se evaluó [Project AIRI / Stage Web](https://github.com/moeru-ai/airi/tree/v0.15.4/apps/stage-web). Sus proveedores compatibles con OpenAI cubren chat y voz, pero su selección se guarda en stores locales de AIRI. La versión evaluada no publica un artefacto web ni documenta cómo fijar esos proveedores por despliegue. Para conservar el acceso de un clic desde Nextcloud sin pedir ajustes al usuario, este hito usa un chat propio en `/airi/`. El backend mantiene la selección de proveedor, el acceso por realm y la síntesis como interfaces independientes del navegador.

El código de [Pocket TTS](https://github.com/kyutai-labs/pocket-tts/tree/v3.3.0) tiene licencia MIT. Los [pesos públicos de Kyutai](https://huggingface.co/kyutai/pocket-tts-without-voice-cloning) tienen licencia CC BY 4.0.
