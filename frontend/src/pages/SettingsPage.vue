<script setup lang="ts">
import { NButton, NCard, NCode, NSpin, NTag } from 'naive-ui'
import { onMounted, ref } from 'vue'

import { api, type ConnectionTestResult } from '../api/client'

const settings = ref<Record<string, unknown> | null>(null)
const error = ref('')
const loading = ref(false)
const testing = ref('')
const results = ref<Record<string, ConnectionTestResult>>({})

async function load() {
  loading.value = true
  error.value = ''
  try { settings.value = await api.settings() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '读取配置失败' }
  finally { loading.value = false }
}

async function test(service: 'bangumi' | 'qbittorrent' | 'mpv') {
  testing.value = service
  try { results.value[service] = await api.testConnection(service) }
  catch (reason) {
    results.value[service] = {
      service,
      status: 'error',
      detail: reason instanceof Error ? reason.message : '测试失败',
    }
  } finally { testing.value = '' }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="page-title">设置</h1>
    <p class="page-description">阶段 0 从 config.yaml 或 AUTOANIME_* 环境变量读取配置；敏感值已脱敏。</p>
    <NSpin :show="loading">
      <p v-if="error" class="error">{{ error }}</p>
      <div class="settings-grid">
        <NCard v-for="service in ['bangumi', 'qbittorrent', 'mpv']" :key="service" :title="service">
          <p class="muted">{{ results[service]?.detail || '尚未测试' }}</p>
          <NTag v-if="results[service]" style="margin-bottom: 12px">{{ results[service].status }}</NTag>
          <br />
          <NButton :loading="testing === service" @click="test(service as 'bangumi' | 'qbittorrent' | 'mpv')">
            测试连接
          </NButton>
        </NCard>
      </div>
      <NCard title="当前配置（脱敏）" style="margin-top: 20px">
        <NCode v-if="settings" :code="JSON.stringify(settings, null, 2)" language="json" word-wrap />
      </NCard>
    </NSpin>
  </div>
</template>
