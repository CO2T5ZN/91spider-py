<script setup>
import { computed, ref, watch } from 'vue'
import { videoFileUrl } from './api'

const props = defineProps({ video: { type: Object, default: null } })
const emit = defineEmits(['close'])

const visible = computed({ get: () => !!props.video, set: v => { if (!v) emit('close') } })
const failed = ref(false)

watch(() => props.video, () => { failed.value = false })

function fmtSize(n) {
  if (!n) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

const playable = computed(() => props.video?.ext === 'mp4')
const url = computed(() => (props.video ? videoFileUrl(props.video.id) : ''))
</script>

<template>
  <a-modal v-model:open="visible" :title="video?.title" width="94%" style="top: 12px"
           :footer="null" destroy-on-close @cancel="emit('close')">
    <div v-if="video">
      <div v-if="playable && !failed" class="player-box">
        <video :src="url" controls autoplay playsinline
               style="width: 100%; max-height: 80vh; background: #000; border-radius: 6px"
               @error="failed = true"></video>
      </div>
      <a-alert v-else type="warning" show-icon
               :message="failed ? '在线播放失败' : 'TS 格式浏览器不支持在线播放'"
               description="可直接下载后本地播放。">
        <template #action>
          <a-button :href="url" download>下载文件</a-button>
        </template>
      </a-alert>

      <div class="meta">
        <p>
          <a-tag v-for="t in video.tags" :key="t" color="blue">{{ t }}</a-tag>
          <span v-if="!video.tags.length" style="color: #666">无标签</span>
        </p>
        <p class="line">
          分类：{{ video.category_name }} ｜ 大小：{{ fmtSize(video.size) || '未知' }} ｜
          格式：{{ (video.ext || '?').toUpperCase() }} ｜ ID：{{ video.video_key }}
        </p>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.meta { margin-top: 12px; }
.line { color: #888; font-size: 13px; }
</style>
