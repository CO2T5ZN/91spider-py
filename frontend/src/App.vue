<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { fetchCategories, fetchVideos } from './api'
import Gallery from './Gallery.vue'
import Player from './Player.vue'

const categories = ref([])
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const loading = ref(false)

const categoryId = ref(null)
const keyword = ref('')
let searchTimer = null

const grouped = computed(() => {
  const groups = {}
  for (const c of categories.value) {
    const label = c.group_name || '其他'
    ;(groups[label] = groups[label] || []).push(c)
  }
  return Object.entries(groups).map(([label, options]) => ({ label, options }))
})

async function load() {
  loading.value = true
  try {
    const d = await fetchVideos({ categoryId: categoryId.value, q: keyword.value.trim(),
                                  page: page.value, pageSize: pageSize.value })
    items.value = d.items
    total.value = d.total
  } catch (e) { message.error(e.message) } finally { loading.value = false }
}

function onSearch(v) { keyword.value = v; page.value = 1; load() }
function onInput(v) {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => onSearch(v), 300)
}
function onPage(p, ps) { page.value = p; pageSize.value = ps; load() }
function pickCategory(id) { categoryId.value = id; page.value = 1; load() }

const playing = ref(null)
function play(item) {
  // 移动端：新标签页打开全屏播放页；桌面端：弹层播放
  if (window.matchMedia('(max-width: 768px)').matches) {
    window.open(`/watch/${item.id}`, '_blank')
    return
  }
  playing.value = item
}

onMounted(async () => {
  load()
  try { categories.value = (await fetchCategories()).categories } catch (e) { message.error(e.message) }
})
</script>

<template>
  <div class="page">
    <header class="topbar">
      <div class="brand">视频库</div>
      <a-input-search class="search" placeholder="搜索标题 / ID" allow-clear
                      :value="keyword" @input="onInput($event.target.value)" @search="onSearch" />
      <span class="total">共 {{ total.toLocaleString() }} 个</span>
    </header>

    <div class="cat-bar">
      <a-checkable-tag class="cat-tag" :checked="categoryId === null" @change="pickCategory(null)">
        全部（{{ categories.reduce((s, c) => s + c.count, 0) }}）
      </a-checkable-tag>
      <template v-for="g in grouped" :key="g.label">
        <a-checkable-tag v-for="c in g.options" :key="c.id" class="cat-tag"
                         :checked="categoryId === c.id" @change="pickCategory(c.id)">
          {{ c.name }}（{{ c.count }}）
        </a-checkable-tag>
      </template>
    </div>

    <main class="grid-area">
      <a-spin :spinning="loading">
        <a-empty v-if="!loading && items.length === 0" description="没有匹配的视频" />
        <Gallery :items="items" @play="play" />
        <div class="pager" v-if="total > 0">
          <a-pagination :current="page" :page-size="pageSize" :total="total"
                        :page-size-options="['12', '24', '48']" show-size-changer
                        :show-total="t => `共 ${t} 个`" @change="onPage" />
        </div>
      </a-spin>
    </main>

    <Player :video="playing" @close="playing = null" />
  </div>
</template>

<style>
html, body, #app { margin: 0; padding: 0; min-height: 100vh; background: #101014; }
.page { min-height: 100vh; display: flex; flex-direction: column; background: #101014; }
.topbar {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 18px 6px; color: #e6e6e6;
}
.brand { color: #1677ff; font-size: 20px; font-weight: 700; white-space: nowrap; }
.search { width: 360px; }
.total { color: #8a8a93; font-size: 12px; white-space: nowrap; margin-left: auto; }
.cat-bar {
  display: flex; flex-wrap: wrap; gap: 6px 4px;
  padding: 2px 18px 10px; border-bottom: 1px solid #23232b;
}
.cat-tag {
  font-size: 13px; padding: 3px 12px; border-radius: 999px;
  background: #1d1d25; color: #c9c9d1; border: 1px solid #2c2c36;
}
.cat-tag:hover { color: #fff; }
.cat-tag.ant-tag-checkable-checked { background: #1677ff; color: #fff; border-color: #1677ff; }
.grid-area { flex: 1; padding: 14px 18px 8px; }
.pager { display: flex; justify-content: center; padding: 20px 0 10px; }

/* 移动端适配 */
@media (max-width: 768px) {
  .topbar { flex-wrap: wrap; gap: 8px 10px; padding: 8px 12px 4px; }
  .brand { font-size: 17px; }
  .search { flex: 1; min-width: 0; width: auto; }
  .total { width: 100%; margin-left: 0; }
  .cat-bar {
    flex-wrap: nowrap; overflow-x: auto; padding: 4px 12px 8px;
    -webkit-overflow-scrolling: touch;
  }
  .cat-tag { white-space: nowrap; flex: 0 0 auto; }
  .grid-area { padding: 10px 12px 6px; }
}
</style>
