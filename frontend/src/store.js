/** 全局响应式 store：REST 首次加载 + SSE 增量更新（前端不轮询）。 */
import { reactive } from 'vue'

export const store = reactive({
  connected: false,          // SSE 连接状态
  categories: [],
  categoriesLoaded: false,
  tasks: [],
  sync: { running: false, done: 0, total: 0, phase: '' },
  settings: {},
  videos: {},                // { [category_id]: video[] }，任务抽屉打开时加载
})

export function upsertCategory(row) {
  if (!row) return
  const i = store.categories.findIndex(c => c.id === row.id)
  if (i >= 0) store.categories.splice(i, 1, row)
  else store.categories.push(row)
}

export function upsertTask(row) {
  if (!row) return
  const i = store.tasks.findIndex(t => t.id === row.id)
  if (i >= 0) store.tasks.splice(i, 1, row)
  else store.tasks.unshift(row)
}

export function removeTask(taskId) {
  const i = store.tasks.findIndex(t => t.id === taskId)
  if (i >= 0) store.tasks.splice(i, 1)
}

export function upsertVideo(categoryId, row) {
  if (!row || !store.videos[categoryId]) return
  const list = store.videos[categoryId]
  const i = list.findIndex(v => v.id === row.id)
  if (i >= 0) list.splice(i, 1, { ...list[i], ...row })
  else list.push(row)
}

export function upsertVideoFull(categoryId, row) {
  if (!row || !store.videos[categoryId]) return
  const list = store.videos[categoryId]
  const i = list.findIndex(v => v.id === row.id)
  if (i >= 0) list.splice(i, 1, row)
  else list.push(row)
}
