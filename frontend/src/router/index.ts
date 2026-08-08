import { createRouter, createWebHistory } from 'vue-router'

import SettingsPage from '../pages/SettingsPage.vue'
import StatusPage from '../pages/StatusPage.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'status', component: StatusPage },
    { path: '/settings', name: 'settings', component: SettingsPage },
  ],
})
