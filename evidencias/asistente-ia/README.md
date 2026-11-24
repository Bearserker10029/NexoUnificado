<!-- SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
     SPDX-License-Identifier: Apache-2.0 -->
# Asistente IA

El [registro de empresas](../../tenants/registry.json) configura `ai_provider: "gemini"` para ACME y `ai_provider: null` para BETA. En una empresa registrada, omitir el campo elige Gemini con la clave que el proveedor del servicio define en `GEMINI_API_KEYS`. El acceso desde un realm sin empresa registrada sigue deshabilitado.

## Evidencias

- [Chat de ACME con una respuesta real de Gemini 3.5 Flash-Lite](chat-gemini.png).
- [Reproductor de la respuesta](audio-pocket-tts.png) y [grabación WAV en español, generada por Pocket TTS](respuesta-pocket-tts.wav).
- [Entrada Asistente IA · ACME en el menú de Nextcloud](menu-nextcloud.png). Al pulsarla, Keycloak reutilizó la sesión y abrió el chat sin pedir credenciales de nuevo.

Copyright 2026 Kent Lin, Luis Quillas, Jeniffer Castillo. Las evidencias del grupo se entregan bajo Apache-2.0.

## Despliegue y comprobación

Arranca con `docker compose up -d --build`. El proveedor del servicio define la clave de Gemini de cada empresa en `GEMINI_API_KEYS` (un objeto JSON en el `.env` del servidor) o una clave única en `GEMINI_API_KEY`; sin clave el asistente avisa de que el proveedor de IA todavía no está configurado. Pocket TTS conserva su modelo de español y la voz Lola. El acceso al asistente sigue por `/airi/` en el proxy HTTPS.

1. Entra en Nextcloud con el proveedor `keycloak-acme` y un usuario del realm `nexo-acme` que pertenezca a uno de los grupos de servicio de ACME.
2. Abre **Asistente IA · ACME**. Keycloak reutiliza la sesión del navegador. Envía «¿Qué es una central telefónica IP? Responde en dos frases». La respuesta la genera Gemini con la clave de la empresa.
3. Reproduce el audio. Si el navegador bloquea el inicio automático, pulsa el control de reproducción. Guarda la grabación o el WAV de la respuesta y una captura de la entrada del menú.
4. Repite el acceso con `keycloak-beta` y comprueba que BETA muestre el asistente deshabilitado.

Para desactivar el asistente de una empresa, usa `"ai_provider": null`. Para elegir Gemini, usa `"ai_provider": "gemini"` y registra la clave de esa empresa en `GEMINI_API_KEYS`, un objeto JSON en el `.env` del servidor. Ejemplo con un valor de muestra: `GEMINI_API_KEYS='{"acme":"CLAVE_DE_ACME"}'`. Si defines ese mapa, cada empresa con Gemini requiere su propia entrada. `GEMINI_API_KEY` sigue disponible para despliegues que usan una sola clave y omiten el mapa. `GEMINI_MODEL` conserva el valor predeterminado `gemini-3.5-flash-lite`.

## Quién configura el asistente

- **Valores predeterminados:** modelo Gemini con la clave que define el proveedor del servicio, voz Pocket TTS ejecutada por el proveedor (compartida por todas las empresas) y personaje 3D (Avatar Sample A).
- **Usuarios de la empresa:** los ajustes de AIRI no se abren (`#/settings` vuelve al inicio) y la API de ajustes responde 403.
- **Administrador de la empresa** (grupo `<empresa>-administradores` en Keycloak, que llega en el `id_token` del cliente `nexo-assistant`): usa los ajustes originales de AIRI. En el proveedor «Compatible con OpenAI» (y en la voz) indica su URL HTTPS, clave y modelo; AIRI guarda el cambio en el servidor (`PUT /airi/api/<empresa>/settings`) con el aviso «Configuración guardada para toda la empresa». Desde entonces todos los usuarios de la empresa usan ese modelo. El personaje que elija entre los incluidos también se aplica a toda la empresa.
- **Dónde se guarda:** `/data/tenant-config.json` (volumen `assistant_data`, permisos 600). Las claves nunca vuelven al navegador: las llamadas del administrador al servicio externo pasan por el servidor de la empresa.
- **Límites:** las URLs deben ser HTTPS hacia direcciones públicas (se rechaza la red interna). Para volver a los valores predeterminados, el administrador deja la URL base de «Compatible con OpenAI» en la del propio Nexo o la vacía.

## Modelo y licencias

La ruta de IA predeterminada usa Gemini (servicio propietario con la clave del proveedor), Pocket TTS (MIT) y AIRI (MIT). Los pesos de Pocket TTS son CC BY 4.0. Cada empresa puede sustituir Gemini por cualquier servicio compatible con OpenAI desde los ajustes de AIRI.


## AIRI Stage Web

La imagen del backend compila [Project AIRI / Stage Web v0.15.4](https://github.com/moeru-ai/airi/tree/v0.15.4/apps/stage-web) con su interfaz y avatar originales. El acceso desde Nextcloud sigue pasando por `/airi/`. Tras verificar el realm de Keycloak y la habilitación de la empresa, Nexo abre Stage Web en `/airi/stage/` y preconfigura los proveedores de chat y voz. La configuración del navegador contiene la URL de Nexo y un identificador público. El backend usa la sesión de Keycloak para autorizar cada operación y conserva la clave de Gemini en el servidor.

Para actualizar solo la parte de IA, ejecuta `docker compose up -d --build assistant pocket-tts`. La primera compilación descarga las dependencias y los recursos oficiales de AIRI. Las capturas de Gemini corresponden a la interfaz inicial del proyecto. AIRI se distribuye con su aviso MIT en `/airi/stage/AIRI-LICENSE.txt`.

El código de [Pocket TTS](https://github.com/kyutai-labs/pocket-tts/tree/v3.3.0) tiene licencia MIT. Los [pesos públicos de Kyutai](https://huggingface.co/kyutai/pocket-tts-without-voice-cloning) tienen licencia CC BY 4.0.
