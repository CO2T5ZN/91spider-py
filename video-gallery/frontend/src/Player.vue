<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import XgPlayer from 'xgplayer'
import 'xgplayer/dist/index.min.css'
import mpegts from 'mpegts.js'
import { videoFileUrl } from './api'
import MpegtsPlugin from './mpegtsPlugin'

const props = defineProps({ video: { type: Object, default: null } })
const emit = defineEmits(['close'])

const visible = computed({ get: () => !!props.video, set: v => { if (!v) emit('close') } })
const failed = ref(false)

function fmtSize(n) {
  if (!n) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

// mp4 走浏览器原生；ts 需 mpegts.js（依赖 MSE，老 iOS Safari 不支持则回退下载）
const playable = computed(() => !!props.video &&
  (props.video.ext === 'mp4' || (props.video.ext === 'ts' && mpegts.isSupported())))
const url = computed(() => (props.video ? videoFileUrl(props.video.id) : ''))

const boxRef = ref(null)
let player = null

function destroyPlayer() {
  initSeq++  // 作废可能还在等时长接口的异步初始化
  if (!player) return
  try { player.destroy() } catch (e) { /* 忽略销毁异常 */ }
  player = null
}

let initSeq = 0  // 异步取时长期间弹层可能被关掉，用序号丢弃过期初始化

async function initPlayer() {
  const box = boxRef.value
  const v = props.video
  if (!box || player || !v) return
  const seq = ++initSeq
  // TS 是 VOD 点播，容器无总时长，先取 ffprobe 探测的时长再建播放器（失败降级）
  let tsDuration = null
  if (v.ext === 'ts') {
    try {
      const r = await fetch(`/api/duration/${v.id}`)
      if (r.ok) tsDuration = (await r.json()).duration || null
    } catch (e) { /* 探测失败按无时长处理 */ }
  }
  if (seq !== initSeq || !props.video || player) return
  // 高度封顶在弹层内（视口 92% 减标题/元信息区），videoFillMode: contain
  // 在固定高度内按视频实际宽高比留黑边（与旧原生播放器行为一致，防弹层超宽视频撑爆）
  const cap = Math.max(window.innerHeight * 0.92 - 210, 240)
  player = new XgPlayer({
    el: box,
    url: url.value,
    poster: v.cover_url || '',
    width: '100%',
    height: cap,
    videoFillMode: 'contain',
    autoplay: true,
    playsinline: true,
    lang: 'zh-cn',
    volume: 0.6,
    tsDuration,
    plugins: v.ext === 'ts' ? [MpegtsPlugin] : [],
  })
  player.on('error', () => { failed.value = true; destroyPlayer() })
}

// Player.vue 随 App 常驻（a-modal 内容才是懒渲染的），初始化/销毁挂在 video prop 上：
// 打开时等弹层内容挂载完再建播放器，关闭时立即销毁（停掉声音、释放 MSE）
watch(() => props.video, v => {
  if (v) {
    failed.value = false
    nextTick(initPlayer)
  } else {
    destroyPlayer()
  }
}, { immediate: true })
onBeforeUnmount(destroyPlayer)
</script>

<template>
  <a-modal v-model:open="visible" :title="video?.title" width="94%" centered
           :footer="null" destroy-on-close @cancel="emit('close')">
    <div v-if="video">
      <div v-if="playable && !failed" class="player-box">
        <div ref="boxRef"></div>
      </div>
      <a-alert v-else type="warning" show-icon
               :message="failed ? '在线播放失败' : '当前浏览器不支持该格式在线播放'"
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
.player-box { display: flex; justify-content: center; }
.meta { margin-top: 12px; }
.line { color: #888; font-size: 13px; }
</style>
