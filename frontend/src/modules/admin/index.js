import { api } from '../../api'

export default {
  id: 'admin',
  role: 'admin',
  login: '/admin/login',
  home: '/admin/inbox', // the issue checklist comes first; it forwards to the dashboard when nothing is waiting
  signOutTo: '/admin/login',
  brand: '채용 담당자',
  who: async () => (await api.adminMe()).company,
  nav: [
    { to: '/admin/inbox', label: '이슈 체크리스트', badge: 'inbox' },
    { to: '/admin', label: '대시보드', exact: true },
  ],
  routes: [
    { path: '/admin/login', component: () => import('./AdminAuth.vue'), props: { mode: 'login' }, meta: { public: true, title: '관리자 로그인' } },
    { path: '/admin/signup', component: () => import('./AdminAuth.vue'), props: { mode: 'signup' }, meta: { public: true, title: '기업 계정 만들기' } },
    { path: '/admin/inbox', component: () => import('./Inbox.vue'), meta: { title: '이슈 체크리스트' } },
    { path: '/admin/working', component: () => import('./Working.vue'), meta: { title: '반영 중' } },
    { path: '/admin', component: () => import('./Dashboard.vue'), meta: { title: '대시보드' } },
    { path: '/admin/sessions/:id', component: () => import('./SessionDetail.vue'), props: true, meta: { title: '세션 상세' } },
  ],
}
