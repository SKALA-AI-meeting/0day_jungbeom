import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// The browser only talks to Spring Boot (/api/**); the agent is never exposed.
const target = process.env.VITE_API_TARGET || 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  server: { port: 5173, proxy: { '/api': { target, changeOrigin: true } } },
})
