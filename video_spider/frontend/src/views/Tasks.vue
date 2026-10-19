<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api, loadCategories, loadTasks, loadVideos, loadSettings } from '../api'
import { store } from '../store'

const stateColors = {
  running: 'processing', paused: 'warning', stopped: 'default',
  completed: 'success', failed: 'error',
}
const stateNames = { running: '运行中', paused: '已暂停', stopped: '已停止', completed: '已完成', failed: '失败' }

const videoStatus = {
  pending: { color: 'default', text: '排队中' },
  downloading: { color: 'processing', text: '下载中' },
  done: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
}

const categoryById = computed(() => Object.fromEntries(store.categories.map(c => [c.id, c])))

// ---- 任务筛选（前端过滤，SSE 更新后自动保持）----
const stateFilter = ref('all')
const categoryFilter = ref(null)

const statusOptions = computed(() => [
  { value: 'all', label: '全部状态' },
  ...Object.entries(stateNames).map(([value, name]) => {
    const n = store.tasks.filter(t => t.state === value).length
    return { value, label: `${name}（${n}）` }
  }),
])

const taskCategoryOptions = computed(() => {
  const seen = new Map()
  for (const t of store.tasks)
    if (!seen.has(t.category_id))
      seen.set(t.category_id, categoryById.value[t.category_id]?.name || `分类 ${t.category_id}`)
  return [...seen.entries()].map(([value, label]) => ({ value, label }))
})

const filteredTasks = computed(() => store.tasks.filter(t =>
  (stateFilter.value === 'all' || t.state === stateFilter.value) &&
  (categoryFilter.value == null || t.category_id === categoryFilter.value)))

// ---- 全局设置 ----
const defaultThreads = ref(3)
async function saveThreads() {
  try {
    await api.putSettings({ default_threads: String(defaultThreads.value) })
    message.success('默认线程数已保存')
  } catch (e) { message.error(e.message) }
}

// ---- 下载设置：保存位置（多硬盘） + 空间 ----
const videoDirs = ref('')
const disk = ref(null)

function fmtSize(n) {
  if (n == null) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0, v = n
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`
}

function pct(d) {
  return d && d.total ? Math.round((d.used / d.total) * 100) : 0
}

async function loadDisk() {
  try {
    disk.value = await api.disk()
    videoDirs.value = (disk.value.video_dirs || '').trim()
      ? disk.value.video_dirs
      : (disk.value.video_dir || '')
  } catch (e) { message.error(e.message) }
}

async function saveVideoDirs() {
  try {
    await api.putSettings({ video_dirs: videoDirs.value })
    message.success('保存位置列表已更新')
    await loadDisk()
  } catch (e) { message.error(e.message) }
}

async function setDefaultRoot(path) {
  try {
    await api.putSettings({ video_root_default: path })
    message.success(`默认保存盘已设为 ${path}`)
    await loadDisk()
  } catch (e) { message.error(e.message) }
}

async function clearDefaultRoot() {
  try {
    await api.putSettings({ video_root_default: '' })
    message.success('已取消默认盘，恢复为自动选盘（剩余空间最大）')
    await loadDisk()
  } catch (e) { message.error(e.message) }
}

// ---- 自动化：失败自动重试 + 每日增量 ----
const autoRetry = ref(true)
const dailyUpdate = ref(true)
const dailyTime = ref('04:00')
const dailyRunning = ref(false)

function syncAutomationSettings() {
  autoRetry.value = store.settings.auto_retry_failed !== '0'
  dailyUpdate.value = store.settings.daily_update !== '0'
  dailyTime.value = store.settings.daily_update_time || '04:00'
}

async function saveAutomation() {
  try {
    await api.putSettings({
      auto_retry_failed: autoRetry.value ? '1' : '0',
      daily_update: dailyUpdate.value ? '1' : '0',
      daily_update_time: dailyTime.value,
    })
    message.success('自动化设置已保存')
  } catch (e) { message.error(e.message) }
}

async function runDailyNow() {
  if (dailyRunning.value) return
  dailyRunning.value = true
  try {
    const r = await api.runDailyUpdate()
    const parts = [`${r.started.length} 个任务有更新（新增 ${r.new_videos}）`, `${r.unchanged} 个无变化`]
    if (r.failed) parts.push(`${r.failed} 个检查失败`)
    message.info(`每日增量检查完成：${parts.join('，')}`, 6)
    await loadTasks()
  } catch (e) { message.error(e.message) }
  finally { dailyRunning.value = false }
}

// ---- 新建任务 ----
const createModal = ref(false)
const newCategoryId = ref(null)
const newThreads = ref(3)
const categoryOptions = computed(() => {
  const used = new Set(store.tasks.map(t => t.category_id))
  return store.categories
    .filter(c => c.enabled && !used.has(c.id))
    .map(c => ({
      value: c.id,
      label: `${c.name}（${c.video_count != null ? c.video_count.toLocaleString() + ' 个' : '数量未知'}）`,
    }))
})

async function confirmCreate() {
  if (!newCategoryId.value) { message.warning('请选择分类'); return }
  try {
    await api.createTask(newCategoryId.value, newThreads.value)
    message.success('任务已创建并启动')
    createModal.value = false
  } catch (e) { message.error(e.message) }
}

// ---- 任务操作 ----
async function act(task, action) {
  try {
    await api.taskAction(task.id, action)
  } catch (e) { message.error(e.message) }
}

async function remove(task) {
  try {
    await api.deleteTask(task.id)
    message.success(`任务 #${task.id} 已删除`)
  } catch (e) { message.error(e.message) }
}

const threadEdits = ref({})
function threadOf(task) {
  return threadEdits.value[task.id] ?? task.thread_count
}
async function applyThreads(task) {
  try {
    await api.patchTask(task.id, threadOf(task))
    message.success(`任务 #${task.id} 线程数已调整为 ${threadOf(task)}`)
  } catch (e) { message.error(e.message) }
}

// ---- 视频抽屉 ----
const drawer = ref(false)
const drawerTask = ref(null)
const drawerStatus = ref('all')
const drawerLoading = ref(false)
const videoColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '标题', dataIndex: 'title', ellipsis: true },
  { title: '来源', dataIndex: 'source', width: 80 },
  { title: '状态', dataIndex: 'status', width: 90 },
  { title: '分片', key: 'segments', width: 160 },
  { title: '错误', dataIndex: 'error', ellipsis: true, width: 220 },
]

// SSE 会就地更新/追加 store.videos，这里再按当前筛选做一层守卫过滤：
// 行状态变化后自动进出筛选视图（如筛"失败"时某行重试成功会立即消失）
const drawerVideos = computed(() => {
  const list = store.videos[drawerTask.value?.category_id] || []
  return drawerStatus.value === 'all' ? list : list.filter(v => v.status === drawerStatus.value)
})
const drawerSummary = computed(() => store.videosSummary[drawerTask.value?.category_id] || {})

async function fetchDrawerVideos() {
  const cat = drawerTask.value?.category_id
  if (cat == null) return
  drawerLoading.value = true
  try {
    await loadVideos(cat, drawerStatus.value === 'all' ? null : drawerStatus.value)
  } catch (e) { message.error(e.message) }
  finally { drawerLoading.value = false }
}

async function openDrawer(task) {
  drawerTask.value = task
  drawerStatus.value = 'all'
  drawer.value = true
  await fetchDrawerVideos()
}

function progressOf(task) {
  const p = task.progress || {}
  if (!p.total) return { percent: 0, text: '等待列表枚举…' }
  const percent = Math.round(((p.done || 0) / p.total) * 100)
  return {
    percent,
    text: `完成 ${p.done || 0} / ${p.total}${p.failed ? `（失败 ${p.failed}）` : ''}`,
  }
}

onMounted(async () => {
  loadCategories().catch(() => {})
  loadTasks().catch(() => {})
  loadDisk()
  loadSettings().then(() => {
    defaultThreads.value = Number(store.settings.default_threads || 3)
    syncAutomationSettings()
  }).catch(() => {})
})
</script>

<template>
  <div>
    <a-card :bordered="false" style="margin-bottom: 16px">
      <a-space wrap>
        <a-button type="primary" @click="createModal = true; newThreads = Number(store.settings.default_threads || 3)">
          新建任务
        </a-button>
        <span>新任务默认线程数</span>
        <a-input-number v-model:value="defaultThreads" :min="1" :max="32" />
        <a-button @click="saveThreads">保存</a-button>
        <a-typography-text type="secondary" style="font-size: 12px">
          所有进度变化通过 SSE 实时推送，无需手动刷新。
        </a-typography-text>
      </a-space>
      <a-space wrap style="margin-top: 12px">
        <span>筛选</span>
        <a-select v-model:value="stateFilter" size="small" style="width: 150px" :options="statusOptions" />
        <a-select v-model:value="categoryFilter" size="small" style="min-width: 170px"
                  placeholder="全部分类" allow-clear :options="taskCategoryOptions" />
        <a-typography-text type="secondary" style="font-size: 12px">
          显示 {{ filteredTasks.length }} / {{ store.tasks.length }} 个任务
        </a-typography-text>
      </a-space>
    </a-card>

    <a-card :bordered="false" style="margin-bottom: 16px" title="下载设置">
      <a-space direction="vertical" style="width: 100%" size="middle">
        <a-space direction="vertical" style="width: 100%" size="small">
          <span>视频保存位置（每行一个目录，支持多硬盘）。设为默认后，之后完成的视频<b>固定存到默认盘</b>；未设默认或默认盘不可用时自动存到剩余空间最大的可写盘</span>
          <a-textarea v-model:value="videoDirs" :rows="3"
                      placeholder="/mnt/hdd/videos&#10;/mnt/disk2/videos" />
          <a-space>
            <a-button type="primary" ghost @click="saveVideoDirs">保存</a-button>
            <a-button @click="loadDisk">刷新</a-button>
            <a-typography-text type="secondary" style="font-size: 12px">
              下一个视频将保存于 <code>{{ disk?.save_path }}</code>
            </a-typography-text>
          </a-space>
        </a-space>
        <div v-for="d in disk?.disks || []" :key="d.path">
          <a-progress v-if="!d.error && d.total" :percent="pct(d)"
                      :status="pct(d) >= 90 ? 'exception' : 'normal'"
                      :format="() => `已用 ${pct(d)}%`" />
          <a-space wrap size="large">
            <span>
              <code>{{ d.path }}</code>
              <a-tag v-if="d.is_default" color="blue" style="margin-left: 8px">默认盘</a-tag>
            </span>
            <template v-if="d.error">
              <a-typography-text type="danger" style="font-size: 12px">不可用：{{ d.error }}</a-typography-text>
            </template>
            <template v-else>
              <span>视频占用 <b>{{ fmtSize(d.videos_size) }}</b></span>
              <span>磁盘已用 {{ fmtSize(d.used) }} / {{ fmtSize(d.total) }}</span>
              <span>剩余 <b>{{ fmtSize(d.free) }}</b></span>
              <a-typography-text v-if="!d.writable" type="warning" style="font-size: 12px">只读/不可写</a-typography-text>
            </template>
            <a-button v-if="d.is_default" size="small" @click="clearDefaultRoot">取消默认</a-button>
            <a-button v-else size="small" type="primary" ghost
                      :disabled="d.error || !d.writable"
                      @click="setDefaultRoot(d.path)">设为默认</a-button>
          </a-space>
        </div>
        <a-space wrap>
          <a-checkbox v-model:checked="autoRetry">任务完成后自动重试失败视频（一遍）</a-checkbox>
          <a-checkbox v-model:checked="dailyUpdate">每日增量检查已完成任务</a-checkbox>
          <template v-if="dailyUpdate">
            <span>检查时间</span>
            <a-input v-model:value="dailyTime" style="width: 72px" placeholder="04:00" />
            <a-tooltip title="立即按同一逻辑检查一次：抓取各已完成任务的分类列表页，与本地对比，新增则自动下载">
              <a-button size="small" :loading="dailyRunning" @click="runDailyNow">立即检查</a-button>
            </a-tooltip>
          </template>
          <a-button size="small" type="primary" ghost @click="saveAutomation">保存</a-button>
        </a-space>
      </a-space>
    </a-card>

    <a-empty v-if="store.tasks.length === 0" description="暂无任务：在「分类管理」或上方「新建任务」创建。" />
    <a-empty v-else-if="filteredTasks.length === 0" description="没有符合筛选条件的任务" />

    <a-card v-for="task in filteredTasks" :key="task.id" class="task-card" size="small" style="margin-bottom: 12px">
      <template #title>
        <div>
          <a-space wrap>
            <span>任务 #{{ task.id }}</span>
            <span>{{ categoryById[task.category_id]?.name || ('分类 ' + task.category_id) }}</span>
            <a-tag :color="stateColors[task.state] || 'default'">{{ stateNames[task.state] || task.state }}</a-tag>
          </a-space>
          <a-typography-text v-if="task.note" type="secondary"
                              style="display: block; font-size: 12px; white-space: normal; word-break: break-all">
            {{ task.note }}
          </a-typography-text>
        </div>
      </template>
      <a-progress :percent="progressOf(task).percent"
                  :status="task.state === 'completed' ? 'success' : (task.progress?.failed ? 'exception' : 'active')" />
      <a-space wrap>
        <span>{{ progressOf(task).text }}</span>
        <span v-if="task.progress?.downloading" type="secondary">下载中 {{ task.progress.downloading }}</span>
        <a-typography-text type="secondary" style="font-size: 12px">
          创建于 {{ (task.created_at || '').replace('T', ' ').slice(0, 19) }}
        </a-typography-text>
      </a-space>
      <div class="actions">
        <a-input-number v-model:value="threadEdits[task.id]" :min="1" :max="32" size="small"
                        :placeholder="String(task.thread_count)" style="width: 88px"
                        :value="threadOf(task)" @change="v => (threadEdits[task.id] = v)" />
        <a-button size="small" @click="applyThreads(task)">线程数</a-button>
        <a-button v-if="task.state === 'running'" size="small" @click="act(task, 'pause')">暂停</a-button>
        <a-button v-if="task.state === 'paused' || task.state === 'stopped'" size="small" type="primary"
                  ghost @click="act(task, 'start')">继续</a-button>
        <a-button v-if="task.state === 'running' || task.state === 'paused'" size="small" danger
                  @click="act(task, 'stop')">停止</a-button>
        <a-button v-if="task.progress?.failed" size="small" @click="act(task, 'retry')">重试失败</a-button>
        <a-popconfirm title="删除任务将同时清除该分类的视频记录，确定？" ok-text="删除"
                      cancel-text="取消" @confirm="remove(task)">
          <a-button v-if="task.state !== 'running'" size="small" danger ghost>删除</a-button>
        </a-popconfirm>
        <a-button size="small" @click="openDrawer(task)">查看视频</a-button>
      </div>
    </a-card>

    <a-drawer v-model:open="drawer" :title="`任务 #${drawerTask?.id} 视频列表（${categoryById[drawerTask?.category_id]?.name || ''}）`"
              width="min(860px, 100vw)" destroy-on-close>
      <a-radio-group v-model:value="drawerStatus" size="small" button-style="solid"
                     style="margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 4px"
                     @change="fetchDrawerVideos">
        <a-radio-button value="all">全部 {{ drawerSummary.total ?? '' }}</a-radio-button>
        <a-radio-button value="pending">排队中 {{ drawerSummary.pending ?? '' }}</a-radio-button>
        <a-radio-button value="downloading">下载中 {{ drawerSummary.downloading ?? '' }}</a-radio-button>
        <a-radio-button value="done">已完成 {{ drawerSummary.done ?? '' }}</a-radio-button>
        <a-radio-button value="failed">失败 {{ drawerSummary.failed ?? '' }}</a-radio-button>
      </a-radio-group>
      <a-table :data-source="drawerVideos" :columns="videoColumns"
               row-key="id" size="small" :loading="drawerLoading"
               :scroll="{ x: 700 }"
               :pagination="{ pageSize: 20, showSizeChanger: false }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'source'">
            <a-tag :color="record.source === 'manual' ? 'purple' : 'blue'">
              {{ record.source === 'manual' ? '手动' : '批量' }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="videoStatus[record.status]?.color || 'default'">
              {{ videoStatus[record.status]?.text || record.status }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'segments'">
            <span v-if="record.total_segments">
              {{ record.done_segments ?? 0 }} / {{ record.total_segments }}
            </span>
            <span v-else style="color: #999">-</span>
          </template>
          <template v-else-if="column.dataIndex === 'title'">
            <a-tooltip v-if="record.title" :title="record.title">
              {{ record.title }}
            </a-tooltip>
            <a-tooltip v-else title="列表页未提供有效标题，任务处理到该视频时会从详情页自动补全">
              <span style="color: #999">ID: {{ record.video_key }}（标题待解析）</span>
            </a-tooltip>
          </template>
        </template>
      </a-table>
    </a-drawer>

    <a-modal v-model:open="createModal" title="新建下载任务" ok-text="创建并启动" cancel-text="取消"
             @ok="confirmCreate">
      <a-space direction="vertical" style="width: 100%">
        <a-select v-model:value="newCategoryId" show-search option-filter-prop="label"
                  placeholder="选择分类（已有任务的分类不显示）" style="width: 100%" :options="categoryOptions" />
        <a-form layout="inline">
          <a-form-item label="线程数">
            <a-input-number v-model:value="newThreads" :min="1" :max="32" />
          </a-form-item>
        </a-form>
      </a-space>
    </a-modal>
  </div>
</template>

<style scoped>
/* 操作行：普通 flex-wrap（不用 a-space，其内部样式在窄屏不可控），手机上自然换成多行 */
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  align-items: center;
}
.actions :deep(.ant-input-number) {
  flex: 0 0 auto;
}
</style>
