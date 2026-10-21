<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, auth } from '../api'

const router = useRouter()
const mode = ref('login')
const email = ref('')
const password = ref('')
const company = ref('')
const busy = ref(false)
const error = ref('')

async function submit() {
  busy.value = true
  error.value = ''
  try {
    const r = mode.value === 'login' ? await api.login(email.value, password.value) : await api.signup(company.value, email.value, password.value)
    auth.setAdmin(r.token)
    router.push('/admin')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page narrow">
    <h1>{{ mode === 'login' ? '관리자 로그인' : '기업 계정 만들기' }}</h1>
    <p class="sub">기업 관리자는 자기 회사의 지원자와 리포트만 볼 수 있어요.</p>
    <form class="card form" @submit.prevent="submit">
      <label v-if="mode === 'signup'" for="company">회사 이름</label>
      <input v-if="mode === 'signup'" id="company" v-model="company" class="text" required maxlength="100" />
      <label for="email">이메일</label>
      <input id="email" v-model="email" class="text" type="email" required autocomplete="username" />
      <label for="password">비밀번호</label>
      <input id="password" v-model="password" class="text" type="password" required minlength="8" autocomplete="current-password" />
      <p v-if="error" class="chip red">{{ error }}</p>
      <button class="btn primary" :disabled="busy">{{ busy ? '확인 중…' : mode === 'login' ? '로그인' : '가입하고 시작' }}</button>
      <button type="button" class="btn link" @click="mode = mode === 'login' ? 'signup' : 'login'">
        {{ mode === 'login' ? '처음이라면 기업 계정 만들기' : '이미 계정이 있어요' }}
      </button>
    </form>
  </main>
</template>

<style scoped>
.narrow { max-width: 460px; }
.form { display: flex; flex-direction: column; gap: 8px; }
label { font-size: 13px; font-weight: 600; color: var(--muted); margin-top: 6px; }
.btn.link { border: 0; background: none; color: var(--brand); }
</style>
