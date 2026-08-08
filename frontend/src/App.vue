<script setup lang="ts">
import { NConfigProvider, NGlobalStyle, NLayout, NLayoutContent, NLayoutHeader, NMenu, darkTheme } from 'naive-ui'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { computed, h } from 'vue'

const route = useRoute()
const router = useRouter()
const activeKey = computed(() => String(route.name ?? 'status'))

const menuOptions = [
  { label: '系统状态', key: 'status' },
  { label: '我的条目', key: 'subjects' },
  { label: '媒体库', key: 'library' },
  { label: '设置', key: 'settings' },
]
</script>

<template>
  <NConfigProvider :theme="darkTheme">
    <NGlobalStyle />
    <NLayout class="app-shell">
      <NLayoutHeader class="topbar" bordered>
        <div class="brand">
          <span class="brand-mark">A</span>
          <div>
            <strong>AutoAnime</strong>
            <small>本地追番管理器</small>
          </div>
        </div>
        <NMenu
          mode="horizontal"
          :value="activeKey"
          :options="menuOptions"
          @update:value="(key) => router.push({ name: key })"
        />
      </NLayoutHeader>
      <NLayoutContent content-style="padding: 32px;">
        <main class="page-container">
          <RouterView />
        </main>
      </NLayoutContent>
    </NLayout>
  </NConfigProvider>
</template>
