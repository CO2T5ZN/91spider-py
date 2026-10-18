<script setup>
defineProps({ items: { type: Array, default: () => [] } })
const emit = defineEmits(['play'])

function fmtSize(n) {
  if (!n) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

function coverOf(item) {
  return item.cover_url || null
}
</script>

<template>
  <a-row :gutter="14">
    <a-col v-for="item in items" :key="item.id"
           :xs="12" :sm="8" :md="6" :lg="4" :xxl="3" style="margin-bottom: 14px">
      <div class="card" @click="emit('play', item)">
        <div class="cover">
          <img v-if="coverOf(item)" :src="coverOf(item)" loading="lazy" alt="">
          <div v-else class="cover-fallback">无封面</div>
          <a-tag class="cat-badge" color="blue">{{ item.category_name }}</a-tag>
          <span v-if="item.ext === 'ts'" class="ts-badge" title="TS 格式浏览器不支持在线播放">TS</span>
        </div>
        <div class="body">
          <div class="title" :title="item.title">{{ item.title }}</div>
          <div class="tags">
            <span v-for="t in item.tags.slice(0, 3)" :key="t" class="tag">{{ t }}</span>
            <span v-if="item.tags.length > 3" class="tag">+{{ item.tags.length - 3 }}</span>
            <span v-if="!item.tags.length" class="no-tags">无标签</span>
          </div>
          <div class="meta">
            <span>{{ fmtSize(item.size) || '文件缺失' }}</span>
          </div>
        </div>
      </div>
    </a-col>
  </a-row>
</template>

<style scoped>
.card {
  background: #17171d; border: 1px solid #23232b; border-radius: 8px;
  overflow: hidden; cursor: pointer; transition: transform .12s, border-color .12s;
}
.card:hover { transform: translateY(-2px); border-color: #1677ff; }
.cover { position: relative; aspect-ratio: 16 / 9; background: #0c0c10; overflow: hidden; }
.cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cover-fallback { display: flex; align-items: center; justify-content: center; height: 100%; color: #55555f; font-size: 14px; }
.cat-badge { position: absolute; top: 6px; left: 6px; margin: 0; }
.ts-badge { position: absolute; top: 6px; right: 6px; background: #fa8c16; color: #fff; font-size: 11px; padding: 0 5px; border-radius: 4px; line-height: 18px; }
.body { padding: 8px 10px 10px; }
.title {
  color: #e6e6e6; font-size: 13px; line-height: 1.4; height: 36px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; margin-bottom: 5px;
}
.tags { min-height: 20px; }
.tag {
  display: inline-block; background: #1f1f28; color: #a8a8b2; font-size: 11px;
  padding: 0 6px; border-radius: 4px; margin: 0 4px 4px 0; line-height: 18px;
}
.no-tags { color: #4a4a55; font-size: 12px; }
.meta { color: #7a7a85; font-size: 12px; }
</style>
