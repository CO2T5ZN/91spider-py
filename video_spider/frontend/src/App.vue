<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { AppstoreOutlined, DownloadOutlined, PlaySquareOutlined } from '@ant-design/icons-vue'
import { store } from './store'
import { connectSSE } from './api'

const router = useRouter()
const route = useRoute()
const activeKey = computed(() => {
  if (route.path.startsWith('/tasks')) return 'tasks'
  if (route.path.startsWith('/videos')) return 'videos'
  return 'categories'
})
const menus = [
  { key: 'categories', label: '分类' },
  { key: 'tasks', label: '任务' },
  { key: 'videos', label: '视频' },
]

// 窄屏（手机）：深色顶部标签栏替代桌面侧栏
const isMobile = ref(false)
let mq = null
function onMq(e) { isMobile.value = e.matches }

onMounted(() => {
  connectSSE()
  mq = window.matchMedia('(max-width: 768px)')
  isMobile.value = mq.matches
  mq.addEventListener('change', onMq)
})
onUnmounted(() => mq?.removeEventListener('change', onMq))
</script>

<template>
  <a-layout style="min-height: 100vh">
    <a-layout-sider v-if="!isMobile" theme="dark" width="200">
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
        <a-menu-item key="videos">
          <PlaySquareOutlined />
          <span>全部视频</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>
    <a-layout>
      <a-layout-header v-if="isMobile" class="m-header">
        <span class="m-logo">91爬虫</span>
        <nav class="m-tabs">
          <span v-for="m in menus" :key="m.key" class="m-tab"
                :class="{ active: activeKey === m.key }"
                @click="router.push('/' + m.key)">{{ m.label }}</span>
        </nav>
        <a-tag :color="store.connected ? 'green' : 'red'" data-testid="sse-status">
          {{ store.connected ? 'SSE' : '断线' }}
        </a-tag>
      </a-layout-header>
      <a-layout-header v-else class="header">
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
  gap: 8px;
  padding: 0 24px;
  height: 48px;
  line-height: 48px;
}
.content { padding: 16px 24px; }

/* ---- 手机端顶栏：与桌面侧栏同款的深色底 ---- */
.m-header {
  background: #001529;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  height: 48px;
  line-height: 48px;
}
.m-logo { color: #fff; font-weight: 600; white-space: nowrap; font-size: 15px; }
.m-tabs {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  gap: 6px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.m-tab {
  align-self: center;
  color: rgba(255, 255, 255, 0.68);
  font-size: 14px;
  line-height: 1.6;
  white-space: nowrap;
  padding: 4px 14px;
  border-radius: 999px;
  cursor: pointer;
}
.m-tab.active { color: #fff; background: #1677ff; }

/* ---- 手机端兜底：弹窗不超屏、媒体不撑破容器 ---- */
.ant-modal { max-width: calc(100vw - 16px); }
img, video { max-width: 100%; }

@media (max-width: 768px) {
  .content { padding: 8px; }
}
</style>
