import { createRouter, createWebHistory } from 'vue-router'
import { modules } from './modules'
import { auth } from './state/auth'

// Routes come from the module manifests; a route needs its module's sign-in unless meta.public.
const routes = modules.flatMap((m) =>
  m.routes.map((r) => ({ ...r, meta: { module: m.id, role: r.meta?.public ? null : m.role, ...r.meta } })),
)
// the catch-all must stay last whatever order modules are listed in
routes.sort((a, b) => (a.path.startsWith('/:rest') ? 1 : 0) - (b.path.startsWith('/:rest') ? 1 : 0))

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

const LOGIN = Object.fromEntries(modules.filter((m) => m.role).map((m) => [m.role, m.login]))
const HAS = { admin: () => auth.admin(), candidate: () => auth.candidate() }

router.beforeEach((to) => {
  const need = to.meta.role
  if (need && !HAS[need]()) return { path: LOGIN[need], query: { next: to.fullPath } }
})
router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · Day Zero` : 'Day Zero · 협업 대화 관찰'
})

export default router
