import { api } from '../../api'

export default {
  id: 'candidate',
  role: 'candidate',
  login: '/login',
  home: '/me',
  signOutTo: '/',
  who: async () => (await api.me()).nickname,
  nav: [
    { to: '/me', label: '내 평가' },
    { to: '/me/start', label: '새 평가 시작' },
  ],
  routes: [
    { path: '/login', component: () => import('../public/Join.vue'), meta: { public: true, title: '지원자 로그인' } },
    { path: '/me', component: () => import('./Me.vue'), meta: { title: '내 평가' } },
    { path: '/me/review', component: () => import('./Review.vue'), meta: { title: '계정 확인' } },
    { path: '/me/start', component: () => import('./Start.vue'), meta: { title: '평가 시작' } },
    { path: '/s/:id', component: () => import('./Session.vue'), props: true, meta: { title: '팀 채널', wide: true } },
  ],
}
