// ⚠️ 逐字复制自 dialect-platform/frontend/src/utils/download.js（那份与本平台零耦合）。
// 两边一起改之前先看一眼这份是不是也改了——保留逐字一致，diff 才有意义。
import { ElMessage } from 'element-plus'

/**
 * 通用文件下载：原生 fetch（axios 拦截器会剥掉 headers，拿不到文件名），
 * 从 Content-Disposition 解析真实文件名，触发浏览器下载。
 *
 * ★★ 调用方必须自己带 `/api` 前缀。
 *    这里是**原生 fetch**，不走 axios 的 `baseURL: '/api'`。
 *    写成 `downloadFile('/annotations/export?...')` 会打到前端的静态路由上，
 *    表现是「点了导出页面莫名跳走 / 404」，而不是一个能看出原因的报错。
 *    正确写法：`downloadFile('/api/annotations/export?...')`。
 *
 * @param {string} url 后端下载端点，**必须自带 /api 前缀**（见上）
 * @param {string} fallbackName 解析失败时的兜底文件名
 * @param {import('vue').Ref<boolean> | null} exportingRef 可选 loading 开关（行内操作为 null，不显 spinner）
 * @returns {Promise<boolean>} 是否导出成功
 */
export async function downloadFile(url, fallbackName, exportingRef) {
  const token = localStorage.getItem('token') || ''
  if (exportingRef) exportingRef.value = true
  try {
    const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!resp.ok) {
      let msg = '导出失败'
      try {
        const data = await resp.json()
        if (data?.detail) msg = data.detail
      } catch (e) { /* 非 JSON 错误体，用默认提示 */ }
      ElMessage.error(msg)
      return false
    }
    const blob = await resp.blob()
    let filename = fallbackName
    const cd = resp.headers.get('Content-Disposition') || ''
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i)
    if (m && m[1]) filename = decodeURIComponent(m[1])
    const urlObj = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = urlObj
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(urlObj)
    ElMessage.success('已导出')
    return true
  } finally {
    if (exportingRef) exportingRef.value = false
  }
}
