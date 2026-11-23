<!-- SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
     SPDX-License-Identifier: Apache-2.0 -->
# Asistente IA

El [registro de empresas](../../tenants/registry.json) configura `ai_provider: "ollama"` para ACME y `ai_provider: null` para BETA. En una empresa registrada, omitir el campo elige Ollama. El acceso desde un realm sin empresa registrada sigue deshabilitado.

## Evidencias

- [Chat de ACME con una respuesta real de Gemini 3.5 Flash-Lite](chat-gemini.png).
- [Reproductor de la respuesta](audio-pocket-tts.png) y [grabación WAV en español, generada por Pocket TTS](respuesta-pocket-tts.wav).
- [Entrada Asistente IA · ACME en el menú de Nextcloud](menu-nextcloud.png). Al pulsarla, Keycloak reutilizó la sesión y abrió el chat sin pedir credenciales de nuevo.

Copyright 2026 Kent Lin, Luis Quillas, Jeniffer Castillo. Las evidencias del grupo se entregan bajo Apache-2.0.

## Despliegue y comprobación

Arranca con `docker compose up -d --build` y consulta `docker compose logs -f ollama-init` para seguir la descarga inicial. Ollama guarda los pesos en un volumen persistente y escucha en la red interna. La primera respuesta en CPU puede tardar más porque carga el modelo en memoria. Puedes seleccionar otro modelo con `OLLAMA_MODEL` en `.env` y volver a levantar Compose. Pocket TTS conserva su modelo de español y la voz Lola. El acceso al asistente sigue por `/airi/` en el proxy HTTPS.

1. Entra en Nextcloud con el proveedor `keycloak-acme` y un usuario del realm `nexo-acme` que pertenezca a uno de los grupos de servicio de ACME.
2. Abre **Asistente IA · ACME**. Keycloak reutiliza la sesión del navegador. Envía «¿Qué es una central telefónica IP? Responde en dos frases». La respuesta se genera en el Ollama local.
3. Reproduce el audio. Si el navegador bloquea el inicio automático, pulsa el control de reproducción. Guarda la grabación o el WAV de la respuesta y una captura de la entrada del menú.
4. Repite el acceso con `keycloak-beta` y comprueba que BETA muestre el asistente deshabilitado.

Para desactivar el asistente de una empresa, usa `"ai_provider": null`. Para elegir Gemini, usa `"ai_provider": "gemini"` y registra la clave de esa empresa en `GEMINI_API_KEYS`, un objeto JSON en el `.env` del servidor. Ejemplo con un valor de muestra: `GEMINI_API_KEYS='{"acme":"CLAVE_DE_ACME"}'`. Si defines ese mapa, cada empresa con Gemini requiere su propia entrada. `GEMINI_API_KEY` sigue disponible para despliegues que usan una sola clave y omiten el mapa. `GEMINI_MODEL` conserva el valor predeterminado `gemini-3.5-flash-lite`.

## Modelo y licencias

La ruta de IA predeterminada funciona localmente con Ollama (MIT), Pocket TTS (MIT) y AIRI (MIT), sin depender de una API propietaria. Los pesos de Qwen2.5 1.5B son Apache-2.0 y los de Pocket TTS son CC BY 4.0. Gemini queda como opción propietaria por empresa.

Elegimos [`qwen2.5:1.5b`](https://ollama.com/library/qwen2.5:1.5b), de 986 MB en Q4_K_M, para CPU. La [ficha de 3B](https://ollama.com/library/qwen2.5:3b) declara la licencia de investigación de Qwen, por lo que esa variante queda fuera de la configuración predeterminada.

## AIRI Stage Web

La imagen del backend compila [Project AIRI / Stage Web v0.15.4](https://github.com/moeru-ai/airi/tree/v0.15.4/apps/stage-web) con su interfaz y avatar originales. El acceso desde Nextcloud sigue pasando por `/airi/`. Tras verificar el realm de Keycloak y la habilitación de la empresa, Nexo abre Stage Web en `/airi/stage/` y preconfigura los proveedores de chat y voz. La configuración del navegador contiene la URL de Nexo y un identificador público. El backend usa la sesión de Keycloak para autorizar cada operación y conserva la clave de Gemini en el servidor.

Para actualizar solo la parte de IA, ejecuta `docker compose up -d --build assistant ollama-init pocket-tts`. La primera compilación descarga las dependencias y los recursos oficiales de AIRI. Las capturas de Gemini corresponden a la interfaz inicial del proyecto. AIRI se distribuye con su aviso MIT en `/airi/stage/AIRI-LICENSE.txt`.

El código de [Pocket TTS](https://github.com/kyutai-labs/pocket-tts/tree/v3.3.0) tiene licencia MIT. Los [pesos públicos de Kyutai](https://huggingface.co/kyutai/pocket-tts-without-voice-cloning) tienen licencia CC BY 4.0.
