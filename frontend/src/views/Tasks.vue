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
    message.success('保存位置已更新，之后完成的视频自动存到剩余空间最大的盘')
    await loadDisk()
  } catch (e) { message.error(e.message) }
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
const videoColumns = [
  { title: 'ID', dataIndex: 'id', width: 70 },
  { title: '标题', dataIndex: 'title', ellipsis: true },
  { title: '来源', dataIndex: 'source', width: 80 },
  { title: '状态', dataIndex: 'status', width: 90 },
  { title: '分片', key: 'segments', width: 160 },
  { title: '错误', dataIndex: 'error', ellipsis: true, width: 220 },
]

async function openDrawer(task) {
  drawerTask.value = task
  drawer.value = true
  await loadVideos(task.category_id).catch(e => message.error(e.message))
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
    </a-card>

    <a-card :bordered="false" style="margin-bottom: 16px" title="下载设置">
      <a-space direction="vertical" style="width: 100%" size="middle">
        <a-space direction="vertical" style="width: 100%" size="small">
          <span>视频保存位置（每行一个目录，支持多硬盘；每个视频完成后自动存到<b>剩余空间最大</b>的可用盘）</span>
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
            <span><code>{{ d.path }}</code></span>
            <template v-if="d.error">
              <a-typography-text type="danger" style="font-size: 12px">不可用：{{ d.error }}</a-typography-text>
            </template>
            <template v-else>
              <span>视频占用 <b>{{ fmtSize(d.videos_size) }}</b></span>
              <span>磁盘已用 {{ fmtSize(d.used) }} / {{ fmtSize(d.total) }}</span>
              <span>剩余 <b>{{ fmtSize(d.free) }}</b></span>
            </template>
          </a-space>
        </div>
      </a-space>
    </a-card>

    <a-empty v-if="store.tasks.length === 0" description="暂无任务：在「分类管理」或上方「新建任务」创建。" />

    <a-card v-for="task in store.tasks" :key="task.id" size="small" style="margin-bottom: 12px">
      <template #title>
        <a-space>
          <span>任务 #{{ task.id }}</span>
          <span>{{ categoryById[task.category_id]?.name || ('分类 ' + task.category_id) }}</span>
          <a-tag :color="stateColors[task.state] || 'default'">{{ stateNames[task.state] || task.state }}</a-tag>
          <a-typography-text v-if="task.note" type="secondary" style="font-size: 12px">{{ task.note }}</a-typography-text>
        </a-space>
      </template>
      <template #extra>
        <a-space>
          <a-input-number v-model:value="threadEdits[task.id]" :min="1" :max="32" size="small"
                          :placeholder="String(task.thread_count)" style="width: 90px"
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
        </a-space>
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
    </a-card>

    <a-drawer v-model:open="drawer" :title="`任务 #${drawerTask?.id} 视频列表（${categoryById[drawerTask?.category_id]?.name || ''}）`"
              width="860" destroy-on-close>
      <a-table :data-source="store.videos[drawerTask?.category_id] || []" :columns="videoColumns"
               row-key="id" size="small"
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
