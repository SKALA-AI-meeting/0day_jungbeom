export default {
  id: 'public',
  role: null,
  nav: [],
  routes: [
    { path: '/', component: () => import('./Landing.vue'), meta: { title: '시작' } },
    { path: '/join/:token', component: () => import('./Join.vue'), props: true, meta: { title: '초대 링크' } },
    { path: '/i/:token', redirect: (to) => `/join/${to.params.token}` }, // invite links sent before accounts existed
    { path: '/:rest(.*)*', component: () => import('./NotFound.vue'), meta: { title: '없는 페이지' } },
  ],
}
