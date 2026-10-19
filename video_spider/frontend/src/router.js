import { createRouter, createWebHistory } from 'vue-router'
import Categories from './views/Categories.vue'
import Tasks from './views/Tasks.vue'
import Videos from './views/Videos.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/categories' },
    { path: '/categories', component: Categories },
    { path: '/tasks', component: Tasks },
    { path: '/videos', component: Videos },
  ],
})
