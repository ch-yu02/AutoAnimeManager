import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api, type SystemStatus } from '../api/client'

export const useSystemStore = defineStore('system', () => {
  const status = ref<SystemStatus | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function refresh() {
    loading.value = true
    error.value = ''
    try {
      status.value = await api.status()
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '无法连接后端'
    } finally {
      loading.value = false
    }
  }

  return { status, loading, error, refresh }
})
