<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { api, loadCategories, loadTasks } from '../api'
import { store } from '../store'

const router = useRouter()
const withCounts = ref(true)
const keyword = ref('')

// 每个分类已有的任务（一个分类只允许一个任务）
const categoryTask = computed(() =>
  Object.fromEntries(store.tasks.map(t => [t.category_id, t.id])))

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return store.categories
  return store.categories.filter(c =>
    (c.name || '').toLowerCase().includes(kw) ||
    (c.group_name || '').toLowerCase().includes(kw) ||
    (c.path || '').toLowerCase().includes(kw))
})

const typeColors = {
  video: 'blue', search: 'cyan', melonshort: 'purple',
  heiliao: 'orange', av: 'geekblue', movieset: 'default',
  novel: 'default', external: 'default', other: 'default',
}
const typeNames = {
  video: '视频分类', search: '关键词', melonshort: '91短视频', heiliao: '黑料吃瓜',
  av: 'AV主题', movieset: '合集', novel: '小说', external: '外链', other: '其他',
  manual: '插件提交',
}
const statusMap = {
  ready: { color: 'green', text: '已计数' },
  no_pager: { color: 'orange', text: 'AJAX列表' },
  counting: { color: 'blue', text: '计数中' },
  error: { color: 'red', text: '错误' },
  new: { color: 'default', text: '未同步' },
}

const columns = [
  { title: 'ID', dataIndex: 'id', width: 64 },
  { title: '分组', dataIndex: 'group_name', width: 110 },
  { title: '名称', dataIndex: 'name', width: 130 },
  { title: '类型', dataIndex: 'type', width: 100 },
  { title: '路径', dataIndex: 'path', ellipsis: true },
  { title: '视频数', dataIndex: 'video_count', width: 110 },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '操作', key: 'action', width: 120 },
]

// ---- 新建任务 ----
const taskModal = ref(false)
const taskCategory = ref(null)
const taskThreads = ref(3)

function actionDisabled(record) {
  return !record.enabled || categoryTask.value[record.id] != null
}

function actionTitle(record) {
  if (!record.enabled) return '该类型不支持下载'
  if (categoryTask.value[record.id] != null) {
    return `该分类已创建过任务 #${categoryTask.value[record.id]}，请在下载任务页操作`
  }
  return ''
}

function openTaskModal(cat) {
  taskCategory.value = cat
  taskThreads.value = Number(store.settings.default_threads || 3)
  taskModal.value = true
}

async function confirmCreateTask() {
  try {
    await api.createTask(taskCategory.value.id, taskThreads.value)
    message.success(`已为「${taskCategory.value.name}」创建下载任务`)
    taskModal.value = false
    router.push('/tasks')
  } catch (e) {
    message.error(e.message)
  }
}

async function doSync() {
  if (store.sync.running) return
  store.sync = { running: true, done: 0, total: 0, phase: 'starting' }
  try {
    await api.syncCategories(withCounts.value)
    message.info(withCounts.value ? '开始同步分类与计数，进度实时更新' : '开始提取分类名称')
  } catch (e) {
    store.sync = { running: false, done: 0, total: 0, phase: '' }
    message.error(e.message)
  }
}

onMounted(() => {
  loadCategories().catch(() => {})
  loadTasks().catch(() => {})
})
</script>

<template>
  <div>
    <a-card :bordered="false" style="margin-bottom: 16px">
      <a-space wrap>
        <a-button type="primary" :loading="store.sync.running" @click="doSync">
          <ReloadOutlined /> 同步分类
        </a-button>
        <a-checkbox v-model:checked="withCounts" :disabled="store.sync.running">
          同时抓取各分类视频总数（约50个请求）
        </a-checkbox>
        <a-input-search v-model:value="keyword" placeholder="搜索名称/路径" style="width: 240px" />
        <span v-if="store.sync.running">
          计数进度：{{ store.sync.done }} / {{ store.sync.total }}
        </span>
      </a-space>
    </a-card>

    <a-alert v-if="store.categoriesLoaded && store.categories.length === 0 && !store.sync.running"
             type="info" show-icon style="margin-bottom: 16px"
             message="还没有分类数据，点击「同步分类」从首页提取。" />

    <a-table :data-source="filtered" :columns="columns" row-key="id" size="middle"
             :pagination="{ pageSize: 50, showSizeChanger: false }">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'action'">
          <a-tooltip :title="actionTitle(record)">
            <span>
              <a-button size="small" type="link" :disabled="actionDisabled(record)"
                        @click="openTaskModal(record)">
                下载任务
              </a-button>
            </span>
          </a-tooltip>
        </template>
        <template v-else-if="column.dataIndex === 'type'">
          <a-tag :color="typeColors[record.type] || 'default'">{{ typeNames[record.type] || record.type }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'status'">
          <a-tooltip :title="record.error || ''">
            <a-tag :color="statusMap[record.status]?.color || 'default'">
              {{ statusMap[record.status]?.text || record.status }}
            </a-tag>
          </a-tooltip>
        </template>
        <template v-else-if="column.dataIndex === 'video_count'">
          <span v-if="record.video_count != null">{{ record.video_count.toLocaleString() }}</span>
          <span v-else style="color: #999">未知</span>
        </template>
        <template v-else-if="column.dataIndex === 'path'">
          <code style="font-size: 12px">{{ record.path }}</code>
        </template>
      </template>
    </a-table>

    <a-modal v-model:open="taskModal" :title="`新建下载任务：${taskCategory?.name || ''}`"
             ok-text="创建并启动" cancel-text="取消" @ok="confirmCreateTask">
      <a-space direction="vertical" style="width: 100%">
        <div>路径：<code>{{ taskCategory?.path }}</code></div>
        <div v-if="taskCategory?.video_count != null">
          视频总数：{{ taskCategory.video_count.toLocaleString() }}（全量下载耗时较长）
        </div>
        <a-form layout="inline">
          <a-form-item label="线程数">
            <a-input-number v-model:value="taskThreads" :min="1" :max="32" />
          </a-form-item>
        </a-form>
        <a-typography-text type="secondary" style="font-size: 12px">
          说明：任务自动解析 m3u8（含 AES-128 解密），分片多线程下载并合并为单文件，支持断点续传。
        </a-typography-text>
      </a-space>
    </a-modal>
  </div>
</template>
