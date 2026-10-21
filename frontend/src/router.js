import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Session from './views/Session.vue'
import AdminList from './views/AdminList.vue'
import AdminDetail from './views/AdminDetail.vue'
import AdminLogin from './views/AdminLogin.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/i/:token', component: Home, props: true },
    { path: '/admin/login', component: AdminLogin },
    { path: '/s/:id', component: Session, props: true },
    { path: '/admin', component: AdminList },
    { path: '/admin/:id', component: AdminDetail, props: true },
  ],
})
