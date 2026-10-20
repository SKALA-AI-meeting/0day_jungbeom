import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Backend dev server (see backend/README). 8000 is often taken, so default to 8765.
const target = process.env.VITE_API_TARGET || 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { '/api': { target, changeOrigin: true } } },
})
