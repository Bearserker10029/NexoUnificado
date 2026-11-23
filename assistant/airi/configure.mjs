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

const app = `${root}/src/App.vue`
// Nexo gates the entry document through Keycloak on every navigation.
replace(app, "import { usePWAStore } from './stores/pwa'\n\nusePWAStore()\n\n", '')
replace(app, "import { useSettings, useSettingsAudioDevice }",
  "import { useProviderConfigStore } from '@proj-airi/stage-ui/stores/providers/config'\nimport { useSettings, useSettingsAudioDevice }")
replace(app, 'import { computed, onMounted,', 'import { computed, nextTick, onMounted,')
replace(app, 'useConsciousnessStore()\nuseHearingStore()\nuseSpeechStore()', `const consciousness = useConsciousnessStore()
useHearingStore()
const speech = useSpeechStore()
const providerConfig = useProviderConfigStore()

async function configureNexoProviders() {
  const tenant = new URLSearchParams(location.search).get('tenant')
  if (!tenant)
    return
  const baseUrl = new URL('/airi/api/' + encodeURIComponent(tenant) + '/v1/', location.origin).href
  for (const [id, model, voice] of [
    ['openai-compatible', 'nexo-chat', ''],
    ['openai-compatible-audio-speech', 'pocket-tts', 'lola'],
  ] as const) {
    const config = { baseUrl, apiKey: 'nexo-session', model, voice }
    providerConfig.ensureProvider(id, id, config)
    await providerConfig.updateProviderConfig(id, config, 'configured')
    providerConfig.markProviderAdded(id)
  }
  consciousness.activeProvider = 'openai-compatible'
  speech.activeSpeechProvider = 'openai-compatible-audio-speech'
  speech.enabled = true
  await nextTick()
  consciousness.activeModel = 'nexo-chat'
  speech.activeSpeechModel = 'pocket-tts'
  speech.activeSpeechVoiceId = 'lola'
  i18n.locale.value = 'es'
}`)
replace(app, "await startup.run('chat',", "await configureNexoProviders()\n    await startup.run('chat',")
replace(app, 'if (onboardingStore.needsOnboarding)', 'if (!new URLSearchParams(location.search).has(\'tenant\') && onboardingStore.needsOnboarding)')
replace(app, 'logo-src="/favicon.svg"', 'logo-src="/airi/stage/favicon.svg"')

// Scope conversation storage and cross-tab synchronization to the Keycloak identity.
const stageUI = 'packages/stage-ui/src'
const profile = 'document.querySelector<HTMLMetaElement>(\'meta[name="nexo-profile"]\')?.content'
const storage = `${stageUI}/database/storage.ts`
replace(storage, 'export const storage', `const nexoProfile = typeof document === 'undefined' ? undefined : ${profile}
const profileDatabase = (name: string) => nexoProfile ? name + '-' + nexoProfile : name

export const storage`)
replace(storage, "base: 'airi-local'", "dbName: profileDatabase('airi-device'), base: 'airi-local'")
replace(storage, "base: 'airi-sync-queue'", "dbName: profileDatabase('airi-device'), base: 'airi-sync-queue'")
for (const name of ['localforage', 'airi-chat-assets', 'airi-memory', 'airi-recipes', 'airi-sticker-library'])
  replace(storage, `dbName: '${name}'`, `dbName: profileDatabase('${name}')`)
replace(`${stageUI}/libs/pinia/setup-synced.ts`, "namespace: 'airi:stage:pinia',",
  `namespace: 'airi:stage:pinia:' + (typeof document === 'undefined' ? '' : ${profile} ?? ''),`)
