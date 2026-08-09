<script setup lang="ts">
import { NButton, NCard, NProgress, NSelect, NSlider, NSpin, NSpace, NTag } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  isNativeAvailable,
  nativeBridge,
  playEpisode,
  pause,
  resume,
  seek,
  selectAudioTrack,
  selectSubtitleTrack,
  setPlayerRect,
  setVolume,
  stop,
  subscribeNativeEvents,
  toggleFullscreen,
  type NativeTrack,
} from '../bridge/nativeBridge'

const props = defineProps<{ episodeId: number; fromStart: boolean; requestKey: number }>()
const emit = defineEmits<{ ended: [nextEpisodeId: number] }>()
const loading = ref(false)
const error = ref('')
const available = ref(isNativeAvailable())
const paused = ref(false)
const position = ref(0)
const duration = ref(0)
const volume = ref(100)
const tracks = ref<NativeTrack[]>([])
const audioTracks = computed(() => tracks.value.filter(track => track.type === 'audio'))
const subtitleTracks = computed(() => tracks.value.filter(track => track.type === 'sub'))
const selectedAudioTrack = computed(() => audioTracks.value.find(track => track.selected)?.id ?? null)
const selectedSubtitleTrack = computed(() => subtitleTracks.value.find(track => track.selected)?.id ?? -1)
const audioOptions = computed(() => audioTracks.value.map(track => ({
  label: track.title || track.language || track.codec || `音轨 ${track.id}`,
  value: track.id,
})))
const subtitleOptions = computed(() => [
  { label: '关闭字幕', value: -1 },
  ...subtitleTracks.value.map(track => ({
    label: track.title || track.language || track.codec || `字幕 ${track.id}`,
    value: track.id,
  })),
])
const playerSlot = ref<HTMLElement | null>(null)
let unsubscribe: () => void = () => undefined
let resizeObserver: ResizeObserver | null = null
let geometryFrame = 0
let scrollEndTimer: ReturnType<typeof window.setTimeout> | undefined
let scrolling = false
let started = false

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return '--:--'
  const whole = Math.floor(seconds)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const remainder = whole % 60
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}` : `${minutes}:${String(remainder).padStart(2, '0')}`
}

async function start() {
  loading.value = true
  error.value = ''
  paused.value = false
  available.value = isNativeAvailable() || Boolean(await nativeBridge())
  if (!available.value) {
    error.value = '本地播放需要使用 AutoAnime Desktop；浏览器模式仍可管理媒体库和观看状态。'
    loading.value = false
    return
  }
  // QWebChannel preserves message order. Publish a visible rect first so Qt can
  // initialize QOpenGLWidget before the following play command reaches libmpv.
  started = true
  await publishPlayerRect(true)
  started = await playEpisode(props.episodeId, props.fromStart)
  if (!started) await publishPlayerRect(false)
  if (!started) error.value = '无法连接桌面播放器'
  loading.value = false
}

async function togglePause() {
  if (paused.value) await resume()
  else await pause()
}

async function commitSeek(value: number) {
  position.value = value
  await seek(value)
}

async function publishPlayerRect(forceVisible?: boolean) {
  const slot = playerSlot.value
  if (!slot) return
  const rect = slot.getBoundingClientRect()
  const requestedVisible = forceVisible ?? started
  const visible = requestedVisible && available.value
    && rect.width > 0
    && rect.height > 0
    && rect.bottom > 0
    && rect.right > 0
    && rect.top < window.innerHeight
    && rect.left < window.innerWidth
  await setPlayerRect(
    rect.left,
    rect.top,
    rect.width,
    rect.height,
    window.devicePixelRatio || 1,
    visible,
  )
}

function syncPlayerRect() {
  if (geometryFrame) cancelAnimationFrame(geometryFrame)
  geometryFrame = requestAnimationFrame(() => {
    geometryFrame = 0
    void publishPlayerRect()
  })
}

function handleScroll() {
  if (!scrolling) {
    scrolling = true
    if (geometryFrame) cancelAnimationFrame(geometryFrame)
    geometryFrame = 0
    // A QWidget cannot participate in Chromium's compositor. Hide the native
    // surface while the page is moving, then place it once at the final DOM
    // position. This avoids a trail of delayed WebChannel geometry updates.
    void publishPlayerRect(false)
  }
  if (scrollEndTimer !== undefined) window.clearTimeout(scrollEndTimer)
  scrollEndTimer = window.setTimeout(() => {
    scrollEndTimer = undefined
    scrolling = false
    syncPlayerRect()
  }, 80)
}

function setupPlayerGeometrySync() {
  const slot = playerSlot.value
  if (!slot) return
  resizeObserver = new ResizeObserver(syncPlayerRect)
  resizeObserver.observe(slot)
  window.addEventListener('resize', syncPlayerRect)
  window.addEventListener('scroll', handleScroll, true)
  window.visualViewport?.addEventListener('resize', syncPlayerRect)
  window.visualViewport?.addEventListener('scroll', handleScroll)
  window.addEventListener('autoanime-native-geometry', syncPlayerRect)
  syncPlayerRect()
}

function teardownPlayerGeometrySync() {
  resizeObserver?.disconnect()
  resizeObserver = null
  window.removeEventListener('resize', syncPlayerRect)
  window.removeEventListener('scroll', handleScroll, true)
  window.visualViewport?.removeEventListener('resize', syncPlayerRect)
  window.visualViewport?.removeEventListener('scroll', handleScroll)
  window.removeEventListener('autoanime-native-geometry', syncPlayerRect)
  if (geometryFrame) cancelAnimationFrame(geometryFrame)
  geometryFrame = 0
  if (scrollEndTimer !== undefined) window.clearTimeout(scrollEndTimer)
  scrollEndTimer = undefined
  scrolling = false
  void setPlayerRect(0, 0, 0, 0, window.devicePixelRatio || 1, false)
}

onMounted(async () => {
  setupPlayerGeometrySync()
  unsubscribe = await subscribeNativeEvents({
    playbackStarted: (episodeId) => { if (episodeId === props.episodeId) loading.value = false },
    positionChanged: (value) => { position.value = value },
    durationChanged: (value) => { duration.value = value },
    pauseChanged: (value) => { paused.value = value },
    volumeChanged: (value) => { volume.value = value },
    trackListChanged: (value) => { tracks.value = value },
    playbackEnded: (episodeId, nextEpisodeId) => {
      if (episodeId === props.episodeId) {
        started = false
        syncPlayerRect()
        emit('ended', nextEpisodeId)
      }
    },
    playbackStopped: (episodeId) => {
      if (episodeId === props.episodeId) {
        started = false
        syncPlayerRect()
      }
    },
    playbackError: (message) => { error.value = message; loading.value = false },
  })
  await start()
  syncPlayerRect()
})

watch(() => props.requestKey, () => { if (started || props.requestKey > 0) void start() })

onBeforeUnmount(() => {
  teardownPlayerGeometrySync()
  unsubscribe()
  if (started) void stop()
})
</script>

<template>
  <NCard title="原生播放器" class="native-player-card">
    <NSpin :show="loading">
      <p v-if="error" class="error">{{ error }}</p>
      <div ref="playerSlot" class="native-player-slot">
        <NTag v-if="available" type="success">AutoAnime Desktop</NTag>
        <span v-else class="muted">Desktop capability unavailable</span>
      </div>
      <div v-if="available" class="native-player-controls">
        <div class="native-player-time">{{ formatTime(position) }} / {{ formatTime(duration) }}</div>
        <NProgress type="line" :percentage="duration ? Math.min(100, position / duration * 100) : 0" :show-indicator="false" />
        <NSlider :value="position" :max="duration || 1" :step="0.1" :disabled="!duration" @update:value="commitSeek" />
        <NSpace>
          <NButton @click="togglePause">{{ paused ? '继续' : '暂停' }}</NButton>
          <NButton @click="stop">停止</NButton>
          <NButton @click="toggleFullscreen">全屏</NButton>
        </NSpace>
        <div class="native-player-settings">
          <span>音量</span>
          <NSlider :value="volume" :min="0" :max="100" :step="1" @update:value="setVolume" />
          <NSelect
            :value="selectedAudioTrack"
            :options="audioOptions"
            :disabled="!audioOptions.length"
            placeholder="无音轨"
            @update:value="selectAudioTrack"
          />
          <NSelect
            :value="selectedSubtitleTrack"
            :options="subtitleOptions"
            @update:value="selectSubtitleTrack"
          />
        </div>
      </div>
    </NSpin>
  </NCard>
</template>

<style scoped>
.native-player-card { margin-top: 16px; }
.native-player-slot { align-items: center; aspect-ratio: 16 / 9; background: #050607; display: flex; justify-content: center; min-height: 240px; overflow: hidden; position: relative; }
.native-player-controls { display: grid; gap: 8px; margin-top: 12px; }
.native-player-settings { align-items: center; display: grid; gap: 10px; grid-template-columns: auto minmax(120px, 1fr) minmax(160px, 1fr) minmax(160px, 1fr); }
.native-player-time { color: var(--muted); font-variant-numeric: tabular-nums; }
</style>
