/** REST 客户端 + SSE 连接（EventSource 自动重连，前端零轮询）。 */
import { store, upsertCategory, upsertTask, removeTask, upsertVideoFull } from './store'

async function req(url, options = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`
    try {
      const j = await resp.json()
      msg = j.detail || msg
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  return resp.json()
}

export const api = {
  categories: () => req('/api/categories'),
  syncCategories: (withCounts = true) =>
    req('/api/categories/sync', { method: 'POST', body: JSON.stringify({ with_counts: withCounts }) }),
  videos: (categoryId, status = null, limit = 300) =>
    req(`/api/videos?category_id=${categoryId}&limit=${limit}${status ? `&status=${status}` : ''}`),
  tasks: () => req('/api/tasks'),
  createTask: (categoryId, threadCount) =>
    req('/api/tasks', { method: 'POST', body: JSON.stringify({ category_id: categoryId, thread_count: threadCount }) }),
  taskAction: (id, action) => req(`/api/tasks/${id}/${action}`, { method: 'POST' }),
  deleteTask: id => req(`/api/tasks/${id}`, { method: 'DELETE' }),
  patchTask: (id, threadCount) =>
    req(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ thread_count: threadCount }) }),
  settings: () => req('/api/settings'),
  putSettings: values => req('/api/settings', { method: 'PUT', body: JSON.stringify({ values }) }),
  disk: () => req('/api/disk'),
}

export function loadCategories() {
  return api.categories().then(({ categories }) => {
    store.categories = categories
    store.categoriesLoaded = true
  })
}

export function loadTasks() {
  return api.tasks().then(({ tasks }) => {
    store.tasks = tasks
  })
}

export function loadSettings() {
  return api.settings().then(({ settings }) => {
    store.settings = settings
  })
}

export function loadVideos(categoryId) {
  return api.videos(categoryId).then(({ videos }) => {
    store.videos[categoryId] = videos
  })
}

export function connectSSE() {
  const es = new EventSource('/api/events')
  es.onopen = () => { store.connected = true }
  es.onerror = () => { store.connected = false }
  es.addEventListener('sync', e => {
    const d = JSON.parse(e.data)
    if (d.phase === 'start') {
      store.sync = { running: true, done: 0, total: d.total, phase: 'counting' }
    } else if (d.phase === 'progress') {
      store.sync.done = d.done
      store.sync.total = d.total
    } else if (d.phase === 'done') {
      store.sync = { running: false, done: d.total, total: d.total, phase: 'done' }
    } else if (d.phase === 'error') {
      store.sync = { running: false, done: 0, total: 0, phase: 'error' }
    }
  })
  es.addEventListener('categories', e => {
    const { category } = JSON.parse(e.data)
    upsertCategory(category)
  })
  es.addEventListener('task', e => {
    const d = JSON.parse(e.data)
    if (d.deleted) {
      removeTask(d.deleted)
      return
    }
    upsertTask(d.task)
  })
  es.addEventListener('video', e => {
    const d = JSON.parse(e.data)
    // 分片级事件只带进度，需要与库内全量行合并
    const list = store.videos[d.category_id]
    const exist = list && list.find(v => v.id === d.id)
    upsertVideoFull(d.category_id, { ...(exist || {}), ...d })
  })
}
