export interface NativeTrack {
  id: number
  type: string
  title: string
  language: string
  codec: string
  selected: boolean
  external: boolean
}

interface NativeSignal<T extends (...args: any[]) => void> {
  connect(callback: T): void
  disconnect?(callback: T): void
}

export interface NativeBridgeProxy {
  available: boolean
  playEpisode(episodeId: number, fromStart: boolean): void
  pause(): void
  resume(): void
  seek(seconds: number): void
  stop(): void
  toggleFullscreen(): void
  setVolume(value: number): void
  selectAudioTrack(id: number): void
  selectSubtitleTrack(id: number): void
  setPlayerRect(
    x: number,
    y: number,
    width: number,
    height: number,
    devicePixelRatio: number,
    visible: boolean,
  ): void
  playerReady: NativeSignal<(episodeId: number) => void>
  playbackStarted: NativeSignal<(episodeId: number) => void>
  positionChanged: NativeSignal<(seconds: number) => void>
  durationChanged: NativeSignal<(seconds: number) => void>
  pauseChanged: NativeSignal<(paused: boolean) => void>
  volumeChanged: NativeSignal<(value: number) => void>
  trackListChanged: NativeSignal<(tracks: NativeTrack[]) => void>
  playbackEnded: NativeSignal<(episodeId: number, nextEpisodeId: number) => void>
  playbackStopped: NativeSignal<(episodeId: number) => void>
  playbackError: NativeSignal<(message: string) => void>
}

export interface NativeEventHandlers {
  playerReady?: (episodeId: number) => void
  playbackStarted?: (episodeId: number) => void
  positionChanged?: (seconds: number) => void
  durationChanged?: (seconds: number) => void
  pauseChanged?: (paused: boolean) => void
  volumeChanged?: (value: number) => void
  trackListChanged?: (tracks: NativeTrack[]) => void
  playbackEnded?: (episodeId: number, nextEpisodeId: number) => void
  playbackStopped?: (episodeId: number) => void
  playbackError?: (message: string) => void
}

declare global {
  interface Window {
    autoanimeNative?: NativeBridgeProxy
    qt?: { webChannelTransport?: unknown }
  }
}

let readyPromise: Promise<NativeBridgeProxy | null> | null = null

function resolveBridge(): NativeBridgeProxy | null {
  return window.autoanimeNative?.available ? window.autoanimeNative : null
}

export function isNativeAvailable(): boolean {
  return resolveBridge() !== null
}

export function nativeBridge(): Promise<NativeBridgeProxy | null> {
  if (readyPromise) return readyPromise
  readyPromise = new Promise((resolve) => {
    const current = resolveBridge()
    if (current) {
      resolve(current)
      return
    }
    if (!window.qt?.webChannelTransport) {
      resolve(null)
      return
    }
    const onReady = () => {
      window.removeEventListener('autoanime-native-ready', onReady)
      resolve(resolveBridge())
    }
    window.addEventListener('autoanime-native-ready', onReady, { once: true })
    window.setTimeout(() => {
      window.removeEventListener('autoanime-native-ready', onReady)
      resolve(resolveBridge())
    }, 3000)
  })
  return readyPromise
}

export async function subscribeNativeEvents(
  handlers: NativeEventHandlers,
): Promise<() => void> {
  const bridge = await nativeBridge()
  if (!bridge) return () => undefined
  const connections: Array<{ signal: NativeSignal<any>; callback: (...args: any[]) => void }> = []
  for (const [name, callback] of Object.entries(handlers)) {
    if (typeof callback !== 'function') continue
    const signal = (bridge as unknown as Record<string, NativeSignal<(...args: any[]) => void>>)[name]
    signal?.connect(callback)
    if (signal) connections.push({ signal, callback })
  }
  return () => {
    for (const { signal, callback } of connections) signal.disconnect?.(callback)
  }
}

export async function playEpisode(episodeId: number, fromStart = false): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.playEpisode(episodeId, fromStart)
  return true
}

export async function pause(): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.pause()
  return true
}

export async function resume(): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.resume()
  return true
}

export async function seek(seconds: number): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.seek(seconds)
  return true
}

export async function stop(): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.stop()
  return true
}

export async function setVolume(value: number): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.setVolume(value)
  return true
}

export async function toggleFullscreen(): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.toggleFullscreen()
  return true
}

export async function selectAudioTrack(id: number): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.selectAudioTrack(id)
  return true
}

export async function selectSubtitleTrack(id: number): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.selectSubtitleTrack(id)
  return true
}

export async function setPlayerRect(
  x: number,
  y: number,
  width: number,
  height: number,
  devicePixelRatio: number,
  visible: boolean,
): Promise<boolean> {
  const bridge = await nativeBridge()
  if (!bridge) return false
  bridge.setPlayerRect(x, y, width, height, devicePixelRatio, visible)
  return true
}
