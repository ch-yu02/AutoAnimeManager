<script setup lang="ts">
import { NButton, NCard, NEmpty, NSpin, NTag } from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api, type SubjectListItem } from '../api/client'

const router = useRouter()
const subjects = ref<SubjectListItem[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try { subjects.value = await api.subjects() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '读取条目失败' }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 class="page-title">我的条目</h1>
    <p class="page-description">来自 Bangumi 的收藏与章节元数据。</p>
    <NSpin :show="loading">
      <p v-if="error" class="error">{{ error }}</p>
      <NEmpty v-else-if="!subjects.length" description="还没有同步到收藏条目" />
      <div v-else class="subject-grid">
        <NCard v-for="subject in subjects" :key="subject.id" hoverable class="subject-card">
          <button class="subject-card-button" @click="router.push({ name: 'subject-detail', params: { id: subject.id } })">
            <img v-if="subject.image_url" :src="subject.image_url" :alt="subject.display_name" />
            <div class="subject-card-content">
              <h2>{{ subject.display_name }}</h2>
              <p class="muted">{{ subject.main_episode_count }} / {{ subject.total_main_episodes ?? '?' }} 正篇</p>
              <NTag size="small">{{ subject.collection_type || '未分类' }}</NTag>
              <small class="muted">同步于 {{ subject.last_synced_at ? new Date(subject.last_synced_at).toLocaleString() : '未知' }}</small>
            </div>
          </button>
        </NCard>
      </div>
    </NSpin>
    <NButton style="margin-top: 20px" :loading="loading" @click="load">刷新条目</NButton>
  </div>
</template>
