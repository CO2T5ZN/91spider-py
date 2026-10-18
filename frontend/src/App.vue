<script setup>
import { computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { store } from './store'
import { connectSSE } from './api'

const router = useRouter()
const route = useRoute()
const activeKey = computed(() => (route.path.startsWith('/tasks') ? 'tasks' : 'categories'))

onMounted(() => {
  connectSSE()
})
</script>

<template>
  <a-layout style="min-height: 100vh">
    <a-layout-sider theme="dark" width="200">
      <div class="logo">91 视频爬虫</div>
      <a-menu :selected-keys="[activeKey]" theme="dark" mode="inline"
              @click="({ key }) => router.push('/' + key)">
        <a-menu-item key="categories">
          <AppstoreOutlined />
          <span>分类管理</span>
        </a-menu-item>
        <a-menu-item key="tasks">
          <DownloadOutlined />
          <span>下载任务</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-header class="header">
        <a-tag :color="store.connected ? 'green' : 'red'" data-testid="sse-status">
          {{ store.connected ? 'SSE 已连接' : 'SSE 未连接' }}
        </a-tag>
      </a-layout-header>
      <a-layout-content class="content">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<style>
body { margin: 0; }
.logo {
  height: 48px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 1px;
}
.header {
  background: #fff;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 0 24px;
  height: 48px;
  line-height: 48px;
}
.content { padding: 16px 24px; }
</style>
