<script setup lang="ts">
import { NButton, NCard, NCode, NForm, NFormItem, NInput, NSpin, NTag } from 'naive-ui'
import { onMounted, onUnmounted, ref } from 'vue'

import { api, type ConnectionTestResult, type SyncStatus } from '../api/client'

const settings = ref<Record<string, unknown> | null>(null)
const error = ref('')
const loading = ref(false)
const testing = ref('')
const results = ref<Record<string, ConnectionTestResult>>({})
const username = ref('')
const token = ref('')
const saving = ref(false)
const sync = ref<SyncStatus | null>(null)
let syncTimer: ReturnType<typeof setInterval> | undefined

async function load() {
  loading.value = true
  error.value = ''
  try {
    settings.value = await api.settings()
    const bangumi = settings.value.bangumi as { username?: string } | undefined
    username.value = bangumi?.username || ''
  }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '读取配置失败' }
  finally { loading.value = false }
}

async function save() {
  saving.value = true
  try {
    const payload: { bangumi_username?: string; bangumi_access_token?: string } = { bangumi_username: username.value }
    if (token.value) payload.bangumi_access_token = token.value
    settings.value = await api.updateSettings(payload)
    token.value = ''
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '保存配置失败' }
  finally { saving.value = false }
}

async function startSync() {
  error.value = ''
  try {
    const started = await api.startSync()
    sync.value = {
      task_id: started.task_id,
      status: started.status,
      processed_count: 0,
      succeeded_count: 0,
      failed_count: 0,
      reused: started.reused,
    }
    if (syncTimer) clearInterval(syncTimer)
    syncTimer = setInterval(pollSync, 800)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '启动同步失败' }
}

function stopPolling() {
  if (syncTimer) clearInterval(syncTimer)
  syncTimer = undefined
}

async function pollSync() {
  if (!sync.value?.task_id) return
  try {
    sync.value = await api.syncStatus(sync.value.task_id)
    if (sync.value.status !== 'RUNNING') stopPolling()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '读取同步状态失败'
    stopPolling()
  }
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
onUnmounted(stopPolling)
</script>

<template>
  <div>
    <h1 class="page-title">设置</h1>
    <p class="page-description">配置 Bangumi 账号后测试连接并手动同步；Token 只显示为已配置状态。</p>
    <NSpin :show="loading">
      <p v-if="error" class="error">{{ error }}</p>
      <NCard title="Bangumi" style="margin-bottom: 20px">
        <NForm label-placement="top">
          <NFormItem label="用户名"><NInput v-model:value="username" placeholder="Bangumi 用户名" /></NFormItem>
          <NFormItem label="Access Token"><NInput v-model:value="token" type="password" show-password-on="click" placeholder="留空表示保留当前 Token" /></NFormItem>
        </NForm>
        <div class="button-row">
          <NButton :loading="saving" type="primary" @click="save">保存配置</NButton>
          <NButton :loading="testing === 'bangumi'" @click="test('bangumi')">测试连接</NButton>
          <NButton :loading="sync?.status === 'RUNNING'" @click="startSync">手动同步</NButton>
        </div>
        <p v-if="results.bangumi" class="muted">{{ results.bangumi.detail }}</p>
        <p v-if="sync" class="sync-message">同步状态：{{ sync.status }}，成功 {{ sync.succeeded_count }}，失败 {{ sync.failed_count }}{{ sync.error_summary ? `；${sync.error_summary}` : '' }}</p>
      </NCard>
      <div class="settings-grid">
        <NCard v-for="service in ['qbittorrent', 'mpv']" :key="service" :title="service">
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
