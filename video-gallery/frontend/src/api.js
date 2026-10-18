/** 极简 API 客户端：返回解析后的 JSON，非 2xx 抛 Error(detail)。 */
async function req(url) {
  const resp = await fetch(url)
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`
    try { msg = (await resp.json()).detail || msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return resp.json()
}

export const fetchCategories = () => req('/api/categories')
export const fetchVideos = ({ categoryId, q, page, pageSize }) => {
  const p = new URLSearchParams({ page, page_size: pageSize })
  if (categoryId) p.set('category_id', categoryId)
  if (q) p.set('q', q)
  return req(`/api/videos?${p}`)
}
export const videoFileUrl = id => `/api/video-file/${id}`
