<script setup lang="ts">
import { NButton, NCard, NEmpty, NSelect, NSpin, NSwitch, NTab, NTabs, NTag } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, type SubjectListItem } from '../api/client'

const router = useRouter()
const route = useRoute()
const subjects = ref<SubjectListItem[]>([])
const loading = ref(false)
const error = ref('')
const localOnly = ref(false)
const collectionLabels: Record<string, string> = {
  WISH: '想看',
  DOING: '在看',
  COLLECTED: '看过',
  ON_HOLD: '搁置',
  DROPPED: '抛弃',
}

interface TimeGroup {
  key: string
  label: string
  subjects: SubjectListItem[]
}

const collectionTabs = [
  { slug: 'doing', type: 'DOING' },
  { slug: 'wish', type: 'WISH' },
  { slug: 'collected', type: 'COLLECTED' },
  { slug: 'on-hold', type: 'ON_HOLD' },
  { slug: 'dropped', type: 'DROPPED' },
]
const currentSlug = computed(() => String(route.params.collectionType || 'doing'))
const currentType = computed(() => collectionTabs.find(tab => tab.slug === currentSlug.value)?.type || 'DOING')
const times = computed<TimeGroup[]>(() => {
  const sorted = [...subjects.value].sort((left, right) => {
    const leftTime = left.air_date || ''
    const rightTime = right.air_date || ''
    return rightTime.localeCompare(leftTime) || left.display_name.localeCompare(right.display_name, 'zh-CN')
  })
  const byTime = new Map<string, SubjectListItem[]>()
  for (const subject of sorted) {
    const key = subject.air_date?.slice(0, 4) || 'unknown'
    byTime.set(key, [...(byTime.get(key) || []), subject])
  }
  return [...byTime.entries()]
    .sort(([left], [right]) => left === 'unknown' ? 1 : right === 'unknown' ? -1 : right.localeCompare(left))
    .map(([key, timeSubjects]) => ({ key, label: key === 'unknown' ? '时间未知' : `${key} 年`, subjects: timeSubjects }))
})

function jumpTo(timeKey: string) {
  document.getElementById(`subject-time-${timeKey}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function load() {
  loading.value = true
  error.value = ''
  try { subjects.value = await api.subjects(currentType.value, localOnly.value) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '读取条目失败' }
  finally { loading.value = false }
}

watch(currentType, load, { immediate: true })
</script>

<template>
  <div>
    <h1 class="page-title">我的条目</h1>
    <p class="page-description">来自 Bangumi 的收藏与章节元数据。</p>
    <NTabs :value="currentSlug" type="line" @update:value="value => router.push(`/subjects/${value}`)">
      <NTab v-for="tab in collectionTabs" :key="tab.slug" :name="tab.slug">
        {{ collectionLabels[tab.type] }}
      </NTab>
    </NTabs>
    <div class="local-filter">
      <NSwitch v-model:value="localOnly" @update:value="load" />
      <span>只显示已匹配本地媒体的条目</span>
    </div>
    <NSpin :show="loading">
      <p v-if="error" class="error">{{ error }}</p>
      <NEmpty v-else-if="!subjects.length" description="还没有同步到收藏条目" />
      <div v-else>
        <section class="subject-group">
          <div class="subject-group-heading">
            <h2>{{ collectionLabels[currentType] }}</h2>
            <NSelect
              size="small"
              class="time-select"
              placeholder="跳转到时间"
              :options="times.map(time => ({ label: time.label, value: time.key }))"
              @update:value="jumpTo"
            />
          </div>
          <section v-for="time in times" :id="`subject-time-${time.key}`" :key="time.key" class="subject-time-group">
            <h3>{{ time.label }}</h3>
            <div class="subject-grid">
              <NCard
                v-for="subject in time.subjects"
                :key="subject.id"
                hoverable
                class="subject-card"
                content-style="padding: 0"
              >
                <button class="subject-card-button" @click="router.push({ name: 'subject-detail', params: { id: subject.id } })">
                  <img v-if="subject.image_url" :src="subject.image_url" :alt="subject.display_name" />
                  <div class="subject-card-content">
                    <h2>{{ subject.display_name }}</h2>
                    <div class="subject-card-meta">
                      <span class="muted">{{ subject.main_episode_count }} / {{ subject.total_main_episodes ?? '?' }} 集</span>
                      <NTag size="small">{{ collectionLabels[subject.collection_type || ''] || '未分类' }}</NTag>
                      <small class="muted">{{ subject.air_date || '日期未知' }}</small>
                    </div>
                  </div>
                </button>
              </NCard>
            </div>
          </section>
        </section>
      </div>
    </NSpin>
    <NButton style="margin-top: 20px" :loading="loading" @click="load">刷新条目</NButton>
  </div>
</template>

<style scoped>
.subject-group {
  margin-bottom: 32px;
}

.local-filter {
  align-items: center;
  display: flex;
  gap: 10px;
  margin: 14px 0 20px;
}

.subject-group-heading {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.time-select {
  width: 150px;
}

.subject-time-group {
  scroll-margin-top: 20px;
}

.subject-time-group > h3 {
  color: var(--muted);
  font-size: 14px;
  margin: 12px 0;
}
</style>
