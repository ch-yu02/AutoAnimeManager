<script setup lang="ts">
import { NButton, NCard, NProgress, NSpin, NTag } from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, type ContinueWatching } from '../api/client'
import { useSystemStore } from '../stores/system'

const system = useSystemStore()
const router = useRouter()
const tagType = (status: string) => status === 'ok' ? 'success' : status === 'error' ? 'error' : 'warning'
const watching = ref<ContinueWatching[]>([])
const playbackError = ref('')

async function loadPlayback() {
  try {
    watching.value = await api.continueWatching()
    playbackError.value = ''
  }
  catch (reason) { playbackError.value = reason instanceof Error ? reason.message : '读取播放状态失败' }
}

function play(item: ContinueWatching) {
  router.push({ name: 'subject-detail', params: { id: item.episode.subject_id }, query: { play: item.episode_id } })
}

onMounted(() => { system.refresh(); loadPlayback() })
</script>

<template>
  <div>
    <h1 class="page-title">系统状态</h1>
    <p class="page-description">确认后端、数据库、配置与任务调度骨架是否正常。</p>

    <NSpin :show="system.loading">
      <p v-if="system.error" class="error">{{ system.error }}</p>
      <div v-if="system.status" class="status-grid">
        <NCard title="后端 API">
          <div class="status-row">
            <span>版本 {{ system.status.version }}</span>
            <NTag :type="tagType(system.status.status)">{{ system.status.status }}</NTag>
          </div>
        </NCard>
        <NCard title="SQLite">
          <div class="status-row">
            <span>{{ system.status.database.detail || '连接正常' }}</span>
            <NTag :type="tagType(system.status.database.status)">{{ system.status.database.status }}</NTag>
          </div>
        </NCard>
        <NCard title="配置">
          <div class="status-row">
            <span>{{ system.status.configuration.detail || '配置完整' }}</span>
            <NTag :type="tagType(system.status.configuration.status)">{{ system.status.configuration.status }}</NTag>
          </div>
        </NCard>
        <NCard title="调度器">
          <div class="status-row">
            <span>阶段 3 暂不启用自动调度</span>
            <NTag>{{ system.status.scheduler.jobs }} jobs</NTag>
          </div>
        </NCard>
      </div>
    </NSpin>
    <NButton style="margin-top: 20px" :loading="system.loading" @click="system.refresh">刷新状态</NButton>

    <section style="margin-top: 24px">
      <h2>继续观看</h2>
      <p v-if="playbackError" class="error">{{ playbackError }}</p>
      <p v-if="!watching.length" class="muted">暂无未完成的观看记录。</p>
      <div v-else class="continue-grid">
        <NCard v-for="item in watching" :key="item.episode_id" class="continue-card">
          <img v-if="item.subject.image_url" :src="item.subject.image_url" :alt="item.subject.name" />
          <div class="continue-content">
            <h3>{{ item.subject.name }}</h3>
            <span>第 {{ item.episode.display_number }} 集 · {{ item.episode.name }}</span>
            <NProgress type="line" :percentage="Math.round(item.progress_ratio * 100)" />
            <NButton type="primary" :disabled="!item.playable" @click="play(item)">{{ item.playable ? '继续观看' : '文件已缺失' }}</NButton>
          </div>
        </NCard>
      </div>
    </section>
  </div>
</template>
