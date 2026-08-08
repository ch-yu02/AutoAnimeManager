<script setup lang="ts">
import { NButton, NCard, NSpin, NTag } from 'naive-ui'
import { onMounted } from 'vue'

import { useSystemStore } from '../stores/system'

const system = useSystemStore()
const tagType = (status: string) => status === 'ok' ? 'success' : status === 'error' ? 'error' : 'warning'
onMounted(system.refresh)
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
            <span>阶段 0 不运行自动任务</span>
            <NTag>{{ system.status.scheduler.jobs }} jobs</NTag>
          </div>
        </NCard>
      </div>
    </NSpin>
    <NButton style="margin-top: 20px" :loading="system.loading" @click="system.refresh">刷新状态</NButton>
  </div>
</template>
