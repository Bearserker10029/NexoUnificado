// SPDX-FileCopyrightText: 2026 Kent Lin, Luis Quillas, Jeniffer Castillo
// SPDX-License-Identifier: Apache-2.0
import { readFileSync, writeFileSync } from 'node:fs'

function replace(file, original, replacement) {
  const source = readFileSync(file, 'utf8').replaceAll('\r\n', '\n')
  if (!source.includes(original))
    throw new Error(`AIRI integration point missing in ${file}: ${original}`)
  writeFileSync(file, source.replace(original, replacement))
}

const root = 'apps/stage-web'
replace(`${root}/vite.config.ts`, 'sourcemap: true,', 'sourcemap: false,')
replace(`${root}/src/main.ts`, 'createWebHashHistory()', 'createWebHashHistory(import.meta.env.BASE_URL + location.search)')
// Solo el administrador de la empresa entra a los ajustes de AIRI (el servidor marca la sesion en el meta nexo-admin);
// todos los usuarios conservan las pantallas del personaje.
replace(`${root}/src/main.ts`, 'router.beforeEach((to, from) => {\n  if (to.path !== from.path)',
  'router.beforeEach((to, from) => {\n  const nexoAvatarRoutes = [\'/settings/models\', \'/settings/airi-card\', \'/settings/characters\']\n  if (to.path.startsWith(\'/settings\') && document.querySelector<HTMLMetaElement>(\'meta[name="nexo-admin"]\')?.content !== \'true\' && !nexoAvatarRoutes.some(route => to.path === route || to.path.startsWith(route + \'/\')))\n    return \'/\'\n  if (to.path !== from.path)')

const app = `${root}/src/App.vue`
// Nexo gates the entry document through Keycloak on every navigation.
replace(app, "import { usePWAStore } from './stores/pwa'\n\nusePWAStore()\n\n", '')
replace(app, "import { useSettings, useSettingsAudioDevice }",
  "import { useProviderConfigStore } from '@proj-airi/stage-ui/stores/providers/config'\nimport { useSettings, useSettingsAudioDevice }")
replace(app, 'import { computed, onMounted,', 'import { computed, nextTick, onMounted,')
replace(app, 'useConsciousnessStore()\nuseHearingStore()\nuseSpeechStore()', `const consciousness = useConsciousnessStore()
const hearing = useHearingStore()
const speech = useSpeechStore()
const providerConfig = useProviderConfigStore()

const nexoTenant = new URLSearchParams(location.search).get('tenant') ?? ''
const nexoAdmin = document.querySelector<HTMLMetaElement>('meta[name="nexo-admin"]')?.content === 'true'
const nexoProxy = nexoTenant ? new URL('/airi/api/' + encodeURIComponent(nexoTenant) + '/v1/', location.origin).href : ''
const nexoSettingsUrl = '/airi/api/' + encodeURIComponent(nexoTenant) + '/settings'
const nexoChatId = 'openai-compatible'
const nexoSpeechId = 'openai-compatible-audio-speech'
const nexoKeyPlaceholder = 'nexo-session'
const nexoRewrites: Array<[string, string]> = []
const nexoNativeFetch = window.fetch.bind(window)

// El administrador configura el modelo en los ajustes originales de AIRI (proveedor OpenAI Compatible).
// Las llamadas a ese servicio salen por el servidor de la empresa: la clave no sale del servidor y
// los demas usuarios usan la misma configuracion.
window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : undefined
  if (url) {
    for (const [from, to] of nexoRewrites) {
      if (url.startsWith(from)) {
        const headers = new Headers(init?.headers)
        headers.delete('authorization')
        return nexoNativeFetch(to + url.slice(from.length), { ...init, headers })
      }
    }
  }
  return nexoNativeFetch(input, init)
}

function nexoBase(value: unknown) {
  return typeof value === 'string' && value.trim() ? (value.trim().endsWith('/') ? value.trim() : value.trim() + '/') : ''
}

function nexoProviderConfig(id: string): Record<string, any> {
  return (providerConfig.providers[id]?.config ?? {}) as Record<string, any>
}

function syncNexoRewrites() {
  nexoRewrites.length = 0
  if (!nexoAdmin)
    return
  for (const id of [nexoChatId, nexoSpeechId]) {
    const base = nexoBase(nexoProviderConfig(id).baseUrl)
    if (base && base !== nexoProxy)
      nexoRewrites.push([base, nexoProxy])
  }
}

let nexoLastSaved = ''
let nexoSaveTimer: ReturnType<typeof setTimeout> | undefined

function nexoPayload() {
  const chat = nexoProviderConfig(nexoChatId)
  const voice = nexoProviderConfig(nexoSpeechId)
  const custom = (config: Record<string, any>) => nexoBase(config.baseUrl) && nexoBase(config.baseUrl) !== nexoProxy
  return {
    chat: custom(chat)
      ? { base_url: String(chat.baseUrl).trim(), model: consciousness.activeModel, api_key: chat.apiKey }
      : { reset: true },
    speech: custom(voice)
      ? { base_url: String(voice.baseUrl).trim(), model: speech.activeSpeechModel, voice: speech.activeSpeechVoiceId, api_key: voice.apiKey }
      : { reset: true },
  }
}

async function saveNexoSettings() {
  syncNexoRewrites()
  const payload = nexoPayload()
  const serialized = JSON.stringify(payload)
  if (serialized === nexoLastSaved)
    return
  const response = await nexoNativeFetch(nexoSettingsUrl, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: serialized,
  })
  if (response.ok) {
    nexoLastSaved = serialized
    toast.success('Configuración guardada para toda la empresa')
  }
  else {
    const error = await response.json().catch(() => ({}))
    toast.error(error.error ?? 'No se pudo guardar la configuración de la empresa')
  }
}

function watchNexoSettings() {
  if (!nexoAdmin)
    return
  watch(
    [() => nexoProviderConfig(nexoChatId), () => nexoProviderConfig(nexoSpeechId),
      () => consciousness.activeModel, () => speech.activeSpeechModel, () => speech.activeSpeechVoiceId],
    () => {
      syncNexoRewrites()
      clearTimeout(nexoSaveTimer)
      nexoSaveTimer = setTimeout(() => { void saveNexoSettings() }, 1500)
    },
    { deep: true },
  )
}

async function configureNexoProviders() {
  if (!nexoTenant)
    return
  let saved: Record<string, any> = {}
  if (nexoAdmin) {
    const response = await nexoNativeFetch(nexoSettingsUrl).catch(() => undefined)
    saved = response?.ok ? await response.json() : {}
  }
  const chatBase = nexoAdmin && saved.chat?.base_url ? saved.chat.base_url : nexoProxy
  const chatModel = nexoAdmin && saved.chat?.model ? saved.chat.model : 'nexo-chat'
  const speechBase = nexoAdmin && saved.speech?.base_url ? saved.speech.base_url : nexoProxy
  const speechModel = nexoAdmin && saved.speech?.model ? saved.speech.model : 'pocket-tts'
  const speechVoice = nexoAdmin && saved.speech?.voice ? saved.speech.voice : 'lola'
  for (const [id, baseUrl, model, voice] of [
    [nexoChatId, chatBase, chatModel, ''],
    [nexoSpeechId, speechBase, speechModel, speechVoice],
  ] as const) {
    const config = { baseUrl, apiKey: nexoKeyPlaceholder, model, voice }
    providerConfig.ensureProvider(id, id, config)
    await providerConfig.updateProviderConfig(id, config, 'configured')
    providerConfig.markProviderAdded(id)
  }
  consciousness.activeProvider = nexoChatId
  speech.activeSpeechProvider = nexoSpeechId
  speech.enabled = true
  await nextTick()
  consciousness.activeModel = chatModel
  speech.activeSpeechModel = speechModel
  speech.activeSpeechVoiceId = speechVoice
  // Escucha por defecto: API de Voz Web del navegador (gratuita y local), en espanol; cada usuario puede cambiarla.
  const sttId = 'browser-web-speech-api'
  const sttKey = 'nexo-initial-stt:' + (document.querySelector<HTMLMetaElement>('meta[name="nexo-profile"]')?.content ?? '')
  if (!localStorage.getItem(sttKey)) {
    providerConfig.ensureProvider(sttId, sttId, { language: 'es-ES' })
    await providerConfig.updateProviderConfig(sttId, { language: 'es-ES' }, 'configured')
    providerConfig.markProviderAdded(sttId)
    hearing.activeTranscriptionProvider = sttId
    hearing.activeTranscriptionModel = 'web-speech-api'
    localStorage.setItem(sttKey, '1')
  }
  i18n.locale.value = 'es'
  syncNexoRewrites()
  nexoLastSaved = JSON.stringify(nexoPayload())
  watchNexoSettings()
}`)
replace(app, "await startup.run('chat',", "await configureNexoProviders()\n    await startup.run('chat',")
// Personaje inicial: 3D la primera vez de cada usuario; despues cada quien lo cambia en los ajustes del personaje.
replace(app, 'async function loadStartup() {', `async function configureNexoStageModel() {
  if (!new URLSearchParams(location.search).get('tenant'))
    return
  const profile = document.querySelector<HTMLMetaElement>('meta[name="nexo-profile"]')?.content ?? ''
  // Personaje por defecto: Oshin. Se aplica una vez por usuario; despues cada quien puede editar su tarjeta.
  const cardKey = 'nexo-card-oshin:' + profile
  if (!localStorage.getItem(cardKey)) {
    const current = cardStore.cards.get('default')
    const technical = String(current?.description ?? '').split('\\n\\n')
    const from = technical.findIndex(part => part.includes('NAME payload'))
    const personality = [
      'Tu nombre es Oshin, se pronuncia "O shin".',
      'Eres una asistente virtual con avatar 3D que ayuda a las personas de la empresa.',
      'Tu personalidad: curiosa, leal, divertida, carismática, perspicaz, alegre, vivaz, honesta y confianzuda. Haces preguntas con interés, bromeas con cariño, tuteas a todos como si fueran amigos de toda la vida y notas los detalles que otros pasan por alto.',
      'También eres violenta, rozando la crueldad, y despistada. Tu violencia es teatral y de comedia: amenazas con exageración, reaccionas con dramatismo y humor negro ante lo que te molesta, y dices las verdades sin filtro. Nunca incitas a hacer daño real ni hieres de verdad a la persona con la que hablas. Eres despistada: a veces pierdes el hilo, confundes un detalle o te distraes, y lo reconoces con gracia antes de volver a ayudar.',
      'Le tienes miedo a las alturas: si se habla de azoteas, balcones, puentes, montañas o aviones, reacciona con un susto simpático y hazlo con humor, sin dejar de ayudar.',
      'Responde en español, con frases cortas y sencillas, como una persona normal. No uses emojis ni símbolos que no se puedan pronunciar, porque tu respuesta se lee en voz alta. Si no sabes algo, dilo con honestidad.',
    ].join('\\n\\n')
    const description = from >= 0 ? personality + '\\n\\n' + technical.slice(from).join('\\n\\n') : personality
    if (current && await cardStore.updateCard('default', { name: 'Oshin', description }))
      localStorage.setItem(cardKey, '1')
  }
  const key = 'nexo-initial-avatar:' + profile
  if (localStorage.getItem(key))
    return
  await cardStore.setActiveCardDefaultAvatarModel('preset-vrm-1')
  localStorage.setItem(key, '1')
}

async function loadStartup() {`)
replace(app, "await startup.run('modelSelection', () => settingsStore.initializeStageModel())",
  "await configureNexoStageModel()\n    await startup.run('modelSelection', () => settingsStore.initializeStageModel())")
// Menu de cuenta: sin inicio de sesion en la nube de AIRI; los usuarios normales solo ven el acceso al personaje.
const headerAvatar = 'packages/stage-layouts/src/components/Layouts/HeaderAvatar.vue'
{
  let source = readFileSync(headerAvatar, 'utf8').replaceAll('\r\n', '\n')
  const login = /(<template v-else>\s*)<DropdownMenuItem as-child>[\s\S]*?authStore\.requestLogin\(\)[\s\S]*?<\/DropdownMenuItem>\s*<DropdownMenuSeparator[^>]*\/>\s*/
  if (!login.test(source))
    throw new Error('AIRI integration point missing in HeaderAvatar: inicio de sesion')
  source = source.replace(login, '$1')
  const link = /(<template v-else>[\s\S]*?)to="\/settings"([\s\S]*?)\{\{ t\('settings\.title'\) \}\}/
  if (!link.test(source))
    throw new Error('AIRI integration point missing in HeaderAvatar: configuracion')
  source = source.replace(link, '$1:to="nexoSettingsTo"$2{{ nexoSettingsLabel }}')
  source = source.replace('<script setup lang="ts">\n', `<script setup lang="ts">
const nexoIsAdmin = document.querySelector<HTMLMetaElement>('meta[name="nexo-admin"]')?.content === 'true'
const nexoSettingsTo = nexoIsAdmin ? '/settings' : '/settings/models'
const nexoSettingsLabel = nexoIsAdmin ? 'Configuración' : 'Personaje'
`)
  writeFileSync(headerAvatar, source)
}
replace(app, 'if (onboardingStore.needsOnboarding)', 'if (!new URLSearchParams(location.search).has(\'tenant\') && onboardingStore.needsOnboarding)')
replace(app, 'logo-src="/favicon.svg"', 'logo-src="/airi/stage/favicon.svg"')

// Scope conversation storage and cross-tab synchronization to the Keycloak identity.
const stageUI = 'packages/stage-ui/src'
const profile = 'document.querySelector<HTMLMetaElement>(\'meta[name="nexo-profile"]\')?.content'
const storage = `${stageUI}/database/storage.ts`
replace(storage, 'export const storage', `const nexoProfile = typeof document === 'undefined' ? undefined : ${profile}
const profileDatabase = (name: string) => nexoProfile ? name + '-' + nexoProfile : name

export const storage`)
// unstorage solo respeta dbName si tambien recibe storeName; sin el, el historial caia en la base compartida keyval-store.
replace(storage, "base: 'airi-local'", "dbName: profileDatabase('airi-device'), storeName: 'keyval', base: 'airi-local'")
replace(storage, "base: 'airi-sync-queue'", "dbName: profileDatabase('airi-device'), storeName: 'keyval', base: 'airi-sync-queue'")
for (const name of ['localforage', 'airi-chat-assets', 'airi-memory', 'airi-recipes', 'airi-sticker-library'])
  replace(storage, `dbName: '${name}'`, `dbName: profileDatabase('${name}')`)
replace(`${stageUI}/libs/pinia/setup-synced.ts`, "namespace: 'airi:stage:pinia',",
  `namespace: 'airi:stage:pinia:' + (typeof document === 'undefined' ? '' : ${profile} ?? ''),`)
