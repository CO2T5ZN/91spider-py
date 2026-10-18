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

function fmtTime(s) {
  if (!Number.isFinite(s)) return '-'
  s = Math.max(0, Math.floor(s))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  const mm = String(m).padStart(2, '0'), ss = String(sec).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`
}

// ---- 触摸手势：在画面上左右滑动快进/快退（右滑 +，左滑 -）----
const videoRef = ref(null)
const seekHint = ref(null) // { forward, target, duration }
const SWIPE_START = 24     // 触发滑动的最小横向位移 px
const SPEED = 0.2          // 每像素对应秒数

let touch = null

function clamp(v, lo, hi) { return Math.min(Math.max(v, lo), hi) }

function onTouchStart(e) {
  const t = e.touches[0]
  const el = videoRef.value
  if (!el || !Number.isFinite(el.duration)) return
  touch = { x: t.clientX, y: t.clientY, time: el.currentTime, active: false }
}

function onTouchMove(e) {
  if (!touch) return
  const t = e.touches[0]
  const dx = t.clientX - touch.x
  const dy = t.clientY - touch.y
  if (!touch.active) {
    if (Math.abs(dx) < SWIPE_START || Math.abs(dx) <= Math.abs(dy)) return
    touch.active = true
  }
  e.preventDefault()
  const el = videoRef.value
  const target = clamp(touch.time + dx * SPEED, 0, el.duration)
  seekHint.value = { forward: dx > 0, target, duration: el.duration }
}

function onTouchEnd() {
  if (touch?.active && seekHint.value) videoRef.value.currentTime = seekHint.value.target
  touch = null
  seekHint.value = null
}

const playable = computed(() => props.video?.ext === 'mp4')
const url = computed(() => (props.video ? videoFileUrl(props.video.id) : ''))
</script>

<template>
  <a-modal v-model:open="visible" :title="video?.title" width="94%" centered
           :footer="null" destroy-on-close @cancel="emit('close')">
    <div v-if="video">
      <div v-if="playable && !failed" class="player-box">
        <video ref="videoRef" :src="url" controls autoplay playsinline
               style="width: 100%; max-height: calc(92vh - 190px); background: #000; border-radius: 6px"
               @error="failed = true"
               @touchstart="onTouchStart" @touchmove="onTouchMove" @touchend="onTouchEnd"></video>
        <div v-if="seekHint" class="seek-hint">
          <span class="arrow">{{ seekHint.forward ? '⏩' : '⏪' }}</span>
          {{ seekHint.forward ? '快进' : '快退' }}
          <span class="time">{{ fmtTime(seekHint.target) }} / {{ fmtTime(seekHint.duration) }}</span>
        </div>
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
.player-box { position: relative; display: flex; justify-content: center; }
.meta { margin-top: 12px; }
.line { color: #888; font-size: 13px; }
.seek-hint {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.72); color: #fff; font-size: 15px;
  padding: 10px 18px; border-radius: 10px; pointer-events: none; white-space: nowrap;
}
.seek-hint .time { color: #9ecbff; margin-left: 8px; }
.seek-hint .arrow { margin-right: 6px; }
</style>
