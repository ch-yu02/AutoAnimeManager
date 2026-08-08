<script setup lang="ts">
import { NButton, NCard, NDataTable, NEmpty, NSpin, NTag } from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, type EpisodeView, type SubjectDetail } from '../api/client'

const route = useRoute()
const router = useRouter()
const subject = ref<SubjectDetail | null>(null)
const episodes = ref<EpisodeView[]>([])
const loading = ref(false)
const error = ref('')
const episodeColumns = [
  { title: '类型', key: 'episode_type', render: (row: EpisodeView) => row.episode_type },
  { title: '集数', key: 'display_number' },
  { title: '名称', key: 'name_cn', render: (row: EpisodeView) => row.name_cn || row.name || '未命名' },
  { title: '放送日期', key: 'air_date', render: (row: EpisodeView) => row.air_date || '-' },
  { title: 'Bangumi 状态', key: 'bangumi_watch_status', render: (row: EpisodeView) => row.bangumi_watch_status || '未记录' },
  { title: '本地状态', key: 'local_status', render: (row: EpisodeView) => row.local_status },
]
const relationText = computed(() => subject.value?.relations.map((relation) => `${relation.relation_type} · ${relation.name_cn || relation.name}`).join('、') || '无')

async function load() {
  loading.value = true
  error.value = ''
  const id = Number(route.params.id)
  try {
    const [detail, episodeList] = await Promise.all([api.subject(id), api.episodes(id)])
    subject.value = detail
    episodes.value = episodeList
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取条目详情失败' }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <NButton quaternary @click="router.push({ name: 'subjects' })">返回条目列表</NButton>
    <NSpin :show="loading">
      <p v-if="error" class="error">{{ error }}</p>
      <template v-if="subject">
        <h1 class="page-title">{{ subject.display_name }}</h1>
        <p class="page-description">{{ subject.name !== subject.display_name ? subject.name : '' }}</p>
        <div class="detail-grid">
          <NCard title="条目元数据">
            <p>{{ subject.summary || '暂无简介' }}</p>
            <p class="muted">收藏状态：<NTag size="small">{{ subject.collection_type || '未分类' }}</NTag></p>
            <p class="muted">平台：{{ subject.platform || '未知' }}　首播：{{ subject.air_date || '未知' }}</p>
            <p class="muted">条目关系：{{ relationText }}</p>
          </NCard>
        </div>
        <NCard title="Episodes" style="margin-top: 16px">
          <NEmpty v-if="!episodes.length" description="暂无章节数据" />
          <NDataTable v-else :columns="episodeColumns" :data="episodes" :pagination="false" />
        </NCard>
      </template>
    </NSpin>
  </div>
</template>
