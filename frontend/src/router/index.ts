import { createRouter, createWebHistory } from 'vue-router'

import SettingsPage from '../pages/SettingsPage.vue'
import StatusPage from '../pages/StatusPage.vue'
import SubjectsPage from '../pages/SubjectsPage.vue'
import SubjectDetailPage from '../pages/SubjectDetailPage.vue'
import LibraryPage from '../pages/LibraryPage.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'status', component: StatusPage },
    { path: '/subjects', name: 'subjects', component: SubjectsPage },
    { path: '/subjects/:id', name: 'subject-detail', component: SubjectDetailPage },
    { path: '/library', name: 'library', component: LibraryPage },
    { path: '/settings', name: 'settings', component: SettingsPage },
  ],
})
