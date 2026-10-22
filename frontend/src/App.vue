<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { auth } from './api'
import { moduleById } from './modules'
import { inbox, refreshInbox, refreshInboxCount } from './state/inbox'

const route = useRoute()
const router = useRouter()
const area = computed(() => moduleById[route.meta.module] || moduleById.public)
const signedIn = computed(() => !!(area.value.role && auth.token(area.value.role)))
const nav = computed(() => (signedIn.value ? area.value.nav : []))
const badge = { inbox: () => inbox.count }
const who = ref('')

watch(
  () => [area.value.id, signedIn.value],
  async () => {
    who.value = ''
    try {
      if (signedIn.value && area.value.who) who.value = (await area.value.who()) || ''
    } catch { /* a 401 is handled by the API client */ }
  },
  { immediate: true },
)

// keep the checklist badge fresh while inside the admin area: the count only, except on the checklist itself,
// which offers the items that arrived meanwhile ("새 항목 N건 불러오기")
let timer
const poll = () => (route.path === '/admin/inbox' ? refreshInbox() : refreshInboxCount()).catch(() => {})
watch(
  () => area.value.id === 'admin' && !!auth.state.admin,
  (on) => {
    clearInterval(timer)
    if (on) { poll(); timer = setInterval(poll, 15000) }
  },
  { immediate: true },
)
onBeforeUnmount(() => clearInterval(timer))

const isActive = (item) => (item.exact ? route.path === item.to : route.path === item.to || route.path.startsWith(item.to + '/'))

function signOut() {
  auth.clear(area.value.role)
  router.push(area.value.signOutTo || '/')
}
</script>

<template>
  <header class="topbar">
    <RouterLink :to="signedIn ? area.home : '/'" class="brand">Day&nbsp;Zero <span>{{ area.brand || '협업 대화 관찰' }}</span></RouterLink>
    <nav>
      <RouterLink v-for="n in nav" :key="n.to" :to="n.to" :class="{ on: isActive(n) }">
        {{ n.label }}<i v-if="n.badge && badge[n.badge]?.()" class="badge">{{ badge[n.badge]() }}</i>
      </RouterLink>
      <template v-if="!signedIn && area.id === 'public'">
        <RouterLink to="/login">지원자 로그인</RouterLink>
        <RouterLink to="/admin/login">채용 담당자</RouterLink>
      </template>
    </nav>
    <div class="who">
      <template v-if="signedIn">
        <span class="muted small">{{ who }}</span>
        <button class="btn sm" @click="signOut">로그아웃</button>
      </template>
    </div>
  </header>
  <RouterView v-slot="{ Component, route: r }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="r.path" />
    </Transition>
  </RouterView>
</template>
