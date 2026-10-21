import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { moduleById } from './modules'
import { auth } from './state/auth'
import './style.css'

auth.onExpired = (role) => {
  const login = Object.values(moduleById).find((m) => m.role === role)?.login
  const here = router.currentRoute.value
  if (login && here.meta.role === role) router.replace({ path: login, query: { next: here.fullPath, expired: '1' } })
}

createApp(App).use(router).mount('#app')
