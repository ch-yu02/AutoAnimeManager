<script setup lang="ts">
import { NButton, NCard, NCheckbox, NEmpty, NSelect, NSpin, NTabPane, NTabs, NTag } from 'naive-ui'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { api, type EpisodeView, type LibraryScanStatus, type MediaFileView, type ReviewQueue, type SubjectListItem } from '../api/client'

const queue = ref<ReviewQueue>({ needs_review: [], automatic: [], manually_linked: [], duplicates: [], locked: [], ignored: [], missing: [] })
const subjects = ref<SubjectListItem[]>([])
const episodes = ref<EpisodeView[]>([])
const selectedSubject = ref<number | null>(null)
const selectedEpisodes = ref<number[]>([])
const primary = ref(true)
const lock = ref(true)
const scan = ref<LibraryScanStatus | null>(null)
const loading = ref(false)
const error = ref('')
let timer: ReturnType<typeof setInterval> | undefined

const subjectOptions = computed(() => subjects.value.map((item) => ({ label: item.display_name, value: item.id })))
const episodeOptions = computed(() => episodes.value.map((item) => ({ label: `${item.episode_type} ${item.display_number} · ${item.name_cn || item.name || '未命名'}`, value: item.id })))

async function load() {
  loading.value = true
  error.value = ''
  try { [queue.value, subjects.value, scan.value] = await Promise.all([api.reviewQueue(), api.subjects(), api.libraryScanStatus()]) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '读取媒体库失败' }
  finally { loading.value = false }
}

async function chooseSubject(value: number | null) {
  selectedSubject.value = value
  selectedEpisodes.value = []
  episodes.value = value ? await api.episodes(value) : []
}

async function startScan() {
  const started = await api.startLibraryScan()
  scan.value = { task_id: started.task_id, status: started.status }
  if (timer) clearInterval(timer)
  timer = setInterval(poll, 700)
}

async function poll() {
  if (!scan.value?.task_id) return
  scan.value = await api.libraryScanStatus(scan.value.task_id)
  if (scan.value.status !== 'RUNNING') {
    if (timer) clearInterval(timer)
    timer = undefined
    await load()
  }
}

async function match(file: MediaFileView) {
  if (!selectedSubject.value) return
  await api.matchFile(file.id, { subject_id: selectedSubject.value, episode_ids: selectedEpisodes.value, primary: primary.value, lock: lock.value, write_manifest: true })
  await load()
}

async function ignore(file: MediaFileView, ignored = true) { await api.ignoreFile(file.id, ignored); await load() }
async function unlink(file: MediaFileView) { await api.unlinkFile(file.id); await load() }
async function reparse(file: MediaFileView) { await api.reparseFile(file.id); await load() }
async function fullHash(file: MediaFileView) { await api.fullHashFile(file.id); await load() }

onMounted(load)
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <div>
    <div class="library-heading">
      <div><h1 class="page-title">媒体库</h1><p class="page-description">扫描本地视频，审核低置信度匹配并维护人工锁定。</p></div>
      <NButton type="primary" :loading="scan?.status === 'RUNNING'" @click="startScan">扫描媒体库</NButton>
    </div>
    <p v-if="scan" class="muted">{{ scan.status }} · 发现 {{ scan.discovered_count || 0 }}，新增 {{ scan.added_count || 0 }}，移动 {{ scan.moved_count || 0 }}，缺失 {{ scan.missing_count || 0 }}，待审核 {{ scan.review_count || 0 }}</p>
    <p v-if="error" class="error">{{ error }}</p>
    <NSpin :show="loading">
      <NCard title="人工关联" style="margin-bottom: 16px">
        <div class="match-controls">
          <NSelect filterable clearable placeholder="选择条目" :options="subjectOptions" :value="selectedSubject" @update:value="chooseSubject" />
          <NSelect multiple filterable placeholder="选择一个或多个章节" :options="episodeOptions" v-model:value="selectedEpisodes" />
          <NCheckbox v-model:checked="primary">设为主文件</NCheckbox>
          <NCheckbox v-model:checked="lock">锁定关联</NCheckbox>
        </div>
      </NCard>
      <NTabs type="line" animated>
        <NTabPane v-for="tab in [
          ['needs_review', '待审核'], ['automatic', '自动匹配'], ['manually_linked', '人工关联'],
          ['duplicates', '重复文件'], ['locked', '人工锁定'], ['missing', '缺失'], ['ignored', '已忽略'],
        ]" :key="tab[0]" :name="tab[0]" :tab="`${tab[1]} (${queue[tab[0] as keyof ReviewQueue].length})`">
          <NEmpty v-if="!queue[tab[0] as keyof ReviewQueue].length" description="暂无文件" />
          <div v-else class="review-list">
            <NCard v-for="file in queue[tab[0] as keyof ReviewQueue]" :key="file.id" size="small">
              <div class="review-row">
                <div class="review-info">
                  <strong>{{ file.filename }}</strong>
                  <span class="muted">{{ file.path }}</span>
                  <span><NTag size="small">{{ file.review_reason || file.subject_mapping_source }}</NTag>　{{ file.subject?.name || '未关联条目' }}<template v-if="file.episodes.length"> · {{ file.episodes.map((item) => `${item.type} ${item.display_number}`).join(', ') }}</template></span>
                  <span v-if="file.subject_confidence !== null" class="muted">置信度 {{ file.subject_confidence.toFixed(2) }} · {{ file.subject_reasons.join('；') || '无匹配理由' }}</span>
                  <span v-if="file.hardlink_paths.length" class="muted">硬链接：{{ file.hardlink_paths.join('、') }}</span>
                </div>
                <div class="button-row">
                  <NButton v-if="tab[0] === 'needs_review'" size="small" type="primary" :disabled="!selectedSubject" @click="match(file)">应用关联</NButton>
                  <NButton v-if="tab[0] === 'needs_review'" size="small" @click="reparse(file)">重新解析</NButton>
                  <NButton v-if="tab[0] === 'manually_linked'" size="small" @click="unlink(file)">解除关联</NButton>
                  <NButton v-if="!file.full_hash && file.exists" size="small" @click="fullHash(file)">计算完整哈希</NButton>
                  <NButton v-if="tab[0] !== 'ignored'" size="small" @click="ignore(file)">忽略</NButton>
                  <NButton v-else size="small" @click="ignore(file, false)">恢复</NButton>
                </div>
              </div>
            </NCard>
          </div>
        </NTabPane>
      </NTabs>
    </NSpin>
  </div>
</template>
