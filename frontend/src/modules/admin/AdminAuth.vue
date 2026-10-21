<script setup>
import { ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, auth } from '../../api'

const props = defineProps({ mode: { type: String, default: 'login' } })
const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const company = ref('')
const busy = ref(false)
const error = ref(route.query.expired ? '로그인이 만료됐어요. 다시 로그인해 주세요.' : '')

async function submit() {
  busy.value = true
  error.value = ''
  try {
    const r = props.mode === 'login' ? await api.login(email.value, password.value) : await api.signup(company.value, email.value, password.value)
    auth.setAdmin(r.token)
    // the issue checklist always comes first; it forwards to `next` (or the dashboard) when nothing is waiting
    const next = route.query.next && route.query.next !== '/admin/inbox' ? route.query.next : null
    router.replace({ path: '/admin/inbox', query: next ? { next } : {} })
  } catch (e) {
    error.value = e.status === 401 ? '이메일이나 비밀번호가 맞지 않아요.' : e.status === 409 ? '이미 가입한 이메일이에요.' : e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page narrow">
    <h1>{{ props.mode === 'login' ? '채용 담당자 로그인' : '기업 계정 만들기' }}</h1>
    <p class="sub">기업 관리자는 자기 회사의 지원자와 리포트만 볼 수 있어요. 로그인하면 에이전트가 확인을 요청한 항목부터 보여 드려요.</p>
    <form class="card form" @submit.prevent="submit">
      <div v-if="props.mode === 'signup'" class="field">
        <label for="company">회사 이름</label>
        <input id="company" v-model="company" class="text" required maxlength="100" />
      </div>
      <div class="field">
        <label for="email">이메일</label>
        <input id="email" v-model.trim="email" class="text" type="email" required autocomplete="username" />
      </div>
      <div class="field">
        <label for="password">비밀번호</label>
        <input id="password" v-model="password" class="text" type="password" required minlength="8" :autocomplete="props.mode === 'login' ? 'current-password' : 'new-password'" />
      </div>
      <p v-if="error" class="chip red">{{ error }}</p>
      <button class="btn primary" :disabled="busy">{{ busy ? '확인 중…' : props.mode === 'login' ? '로그인' : '가입하고 시작' }}</button>
      <RouterLink class="btn link" :to="props.mode === 'login' ? '/admin/signup' : '/admin/login'" replace>
        {{ props.mode === 'login' ? '처음이라면 기업 계정 만들기' : '이미 계정이 있어요' }}
      </RouterLink>
    </form>
  </main>
</template>

<style scoped>
.narrow { max-width: 460px; }
.form { display: flex; flex-direction: column; gap: 14px; }
.btn.link { text-align: center; }
</style>
