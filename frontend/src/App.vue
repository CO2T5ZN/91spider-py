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
function onCategory() { page.value = 1; load() }

const playing = ref(null)
function play(item) { playing.value = item }

onMounted(async () => {
  load()
  try { categories.value = (await fetchCategories()).categories } catch (e) { message.error(e.message) }
})
</script>

<template>
  <a-layout style="min-height: 100vh; background: #f5f5f5">
    <a-layout-header class="header">
      <div class="brand">视频库</div>
      <a-input-search class="search" placeholder="搜索标题 / ID" allow-clear enter-button
                      :value="keyword" @input="onInput($event.target.value)" @search="onSearch" />
      <a-select class="cat" v-model:value="categoryId" allow-clear show-search option-filter-prop="label"
                placeholder="全部分类" @change="onCategory">
        <a-select-opt-group v-for="g in grouped" :key="g.label" :label="g.label">
          <a-select-option v-for="c in g.options" :key="c.id" :value="c.id"
                           :label="`${c.name} (${c.count})`">
            {{ c.name }}（{{ c.count }}）
          </a-select-option>
        </a-select-opt-group>
      </a-select>
      <span class="total">共 {{ total.toLocaleString() }} 个视频</span>
    </a-layout-header>

    <a-layout-content class="content">
      <a-spin :spinning="loading">
        <a-empty v-if="!loading && items.length === 0" description="没有匹配的视频" />
        <Gallery :items="items" @play="play" />
        <div class="pager" v-if="total > 0">
          <a-pagination :current="page" :page-size="pageSize" :total="total"
                        :page-size-options="['12', '24', '48']" show-size-changer
                        :show-total="t => `共 ${t} 个`" @change="onPage" />
        </div>
      </a-spin>
    </a-layout-content>

    <Player :video="playing" @close="playing = null" />
  </a-layout>
</template>

<style>
.header { display: flex; align-items: center; gap: 16px; padding: 0 24px; background: #fff; }
.brand { color: #1677ff; font-size: 18px; font-weight: 600; white-space: nowrap; }
.search { width: 340px; }
.cat { min-width: 240px; }
.total { color: #999; font-size: 12px; white-space: nowrap; }
.content { padding: 16px 24px; }
.pager { display: flex; justify-content: center; padding: 24px 0 8px; }
</style>
