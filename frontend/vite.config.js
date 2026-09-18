import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5174,
    proxy: {
      // 本地开发后端跑在 8001（与服务器上的 crm-api 端口一致）。
      // 方言平台本地用 8000，两个项目同时开也不打架。
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      },
      '/media': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true
      }
    }
  }
})
