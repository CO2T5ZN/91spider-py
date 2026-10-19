<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api, loadCategories } from '../api'
import { store } from '../store'

// 全站视频浏览（移动优先）：封面网格 + 分类/状态/搜索筛选 + 点开播放/下载

const statusMeta = {
  pending: { color: '#8c8c8c', text: '排队中' },
  downloading: { color: '#1677ff', text: '下载中' },
  done: { color: '#52c41a', text: '已完成' },
  failed: { color: '#ff4d4f', text: '失败' },
}
const statusOptions = [
  { value: 'all', label: '全部状态' },
  ...Object.entries(statusMeta).map(([value, m]) => ({ value, label: m.text })),
]

const categoryId = ref(null)
const status = ref('all')
const q = ref('')
const items = ref([])
const total = ref(0)
const page = ref(1)
const PAGE_SIZE = 24
const loading = ref(false)
const hasMore = computed(() => items.value.length < total.value)

const categoryOptions = computed(() =>
  store.categories.map(c => ({ value: c.id, label: c.name })))

async function fetchPage(reset = false) {
  if (loading.value) return
  loading.value = true
  try {
    const r = await api.allVideos({
      category_id: categoryId.value,
      status: status.value === 'all' ? null : status.value,
      q: q.value.trim() || null,
      page: reset ? 1 : page.value + 1,
      page_size: PAGE_SIZE,
    })
    total.value = r.total
    page.value = r.page
    items.value = reset ? r.items : [...items.value, ...r.items]
  } catch (e) { message.error(e.message) }
  finally { loading.value = false }
}

function applyFilters() { fetchPage(true) }

// ---- 点开播放 ----
const current = ref(null)
const playerOpen = ref(false)
function openVideo(v) {
  current.value = v
  playerOpen.value = true
}

function fmtSize(n) {
  if (n == null) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

// 滚动到底自动翻页（手机端无缝浏览）
function onScroll() {
  if (loading.value || !hasMore.value) return
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 400)
    fetchPage()
}

onMounted(() => {
  loadCategories().catch(() => {})
  fetchPage(true)
  window.addEventListener('scroll', onScroll, { passive: true })
})
onUnmounted(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <div>
    <a-card :bordered="false" style="margin-bottom: 12px">
      <a-space wrap style="width: 100%">
        <a-select v-model:value="categoryId" allow-clear show-search option-filter-prop="label"
                  placeholder="全部分类" style="min-width: 150px" :options="categoryOptions"
                  @change="applyFilters" />
        <a-select v-model:value="status" style="width: 118px" :options="statusOptions"
                  @change="applyFilters" />
        <a-input-search v-model:value="q" placeholder="标题 / video_key"
                        style="width: 220px; max-width: 100%" enter-button="搜索"
                        @search="applyFilters" />
        <a-typography-text type="secondary" style="font-size: 12px">共 {{ total }} 条</a-typography-text>
      </a-space>
    </a-card>

    <div class="grid">
      <div v-for="v in items" :key="v.id" class="card" @click="openVideo(v)">
        <div class="thumb">
          <img v-if="v.cover" :src="`/api/covers/${v.cover}`" loading="lazy" alt="">
          <div v-else class="nocover">无封面</div>
          <span class="badge" :style="{ background: statusMeta[v.status]?.color || '#8c8c8c' }">
            {{ statusMeta[v.status]?.text || v.status }}
          </span>
          <span v-if="v.ext === 'ts'" class="ext">TS</span>
          <span v-else-if="!v.ext" class="ext">缺文件</span>
        </div>
        <div class="t">{{ v.title }}</div>
        <div class="m">
          {{ v.category_name }}
          <template v-if="v.status === 'downloading' && v.total_segments">
            · {{ v.done_segments ?? 0 }}/{{ v.total_segments }} 片
          </template>
          <template v-else-if="v.size"> · {{ fmtSize(v.size) }}</template>
        </div>
      </div>
    </div>

    <a-empty v-if="!loading && !items.length" description="没有符合条件的视频" />
    <div v-if="loading" style="text-align: center; padding: 16px; color: #999">加载中…</div>
    <div v-else-if="hasMore" style="text-align: center; padding: 16px">
      <a-button @click="fetchPage()">加载更多（{{ items.length }}/{{ total }}）</a-button>
    </div>
    <div v-else-if="items.length" style="text-align: center; padding: 16px; color: #999">
      已全部加载（{{ total }} 条）
    </div>

    <a-modal v-model:open="playerOpen" :footer="null" :title="null" width="min(720px, 96vw)"
             :body-style="{ padding: 0 }" destroy-on-close>
      <template v-if="current">
        <video v-if="current.ext === 'mp4'" :src="`/api/video-file/${current.id}`"
               controls autoplay playsinline
               style="width: 100%; max-height: 68vh; background: #000; display: block" />
        <div v-else-if="current.ext === 'ts'" class="nojs">
          TS 格式不支持在线播放，<a :href="`/api/video-file/${current.id}`" download>下载文件</a>
        </div>
        <div v-else class="nojs" style="color: #999">视频文件缺失</div>
        <div style="padding: 12px 16px">
          <div style="font-weight: 600; margin-bottom: 6px; word-break: break-all">{{ current.title }}</div>
          <a-space wrap size="middle">
            <span>{{ current.category_name }}</span>
            <span :style="{ color: statusMeta[current.status]?.color }">
              {{ statusMeta[current.status]?.text || current.status }}
            </span>
            <span v-if="current.size">{{ fmtSize(current.size) }}</span>
            <a v-if="current.ext" :href="`/api/video-file/${current.id}`" download>下载</a>
          </a-space>
          <div v-if="current.status === 'failed' && current.error"
               style="margin-top: 8px; color: #ff4d4f; font-size: 12px; word-break: break-all">
            {{ current.error }}
          </div>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
  gap: 12px;
}
.card { cursor: pointer; }
.thumb {
  position: relative;
  aspect-ratio: 16 / 9;
  background: #111;
  border-radius: 8px;
  overflow: hidden;
}
.thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.nocover {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: #666; font-size: 12px;
}
.badge {
  position: absolute; left: 6px; bottom: 6px;
  color: #fff; font-size: 11px; line-height: 1;
  padding: 3px 6px; border-radius: 4px;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
}
.ext {
  position: absolute; right: 6px; top: 6px;
  background: rgba(0, 0, 0, 0.65); color: #fff;
  font-size: 11px; line-height: 1; padding: 3px 6px; border-radius: 4px;
}
.t {
  margin-top: 6px; font-size: 13px; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.m { margin-top: 2px; font-size: 12px; color: #999; }
.nojs { padding: 28px 16px; text-align: center; }
.nojs a { color: #1677ff; }
</style>
