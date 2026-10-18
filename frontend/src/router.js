import { createRouter, createWebHistory } from 'vue-router'
import Categories from './views/Categories.vue'
import Tasks from './views/Tasks.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/categories' },
    { path: '/categories', component: Categories },
    { path: '/tasks', component: Tasks },
  ],
})
