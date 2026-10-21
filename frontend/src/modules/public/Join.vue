<script setup>
// Candidate entry: /join/:token (invite → sign up or log in) and /login (log in only; sign-up needs an invite).
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, auth } from '../../api'

const props = defineProps({ token: { type: String, default: '' } })
const route = useRoute()
const router = useRouter()
const invite = ref(null)
const meta = ref(null)
const mode = ref(props.token ? 'signup' : 'login')
const busy = ref(false)
const error = ref(route.query.expired ? '로그인이 만료됐어요. 다시 로그인해 주세요.' : '')
const tried = ref(false)
const touched = reactive({})
const me = ref(null)

const f = reactive({ email: '', password: '', nickname: '', desiredJob: null, industry: null, experienceYears: 0, bio: '', consent: false })
const login = reactive({ email: '', password: '' })

onMounted(async () => {
  try {
    const [m, inv] = await Promise.all([api.meta(), props.token ? api.invite(props.token) : null])
    meta.value = m
    invite.value = inv
    if (inv?.alias) f.nickname = inv.alias
  } catch {
    error.value = '서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  }
  if (auth.state.candidate) me.value = await api.me().catch(() => null)
})

// the same rules the agent checks first (schema); the agent then looks at whether the values are plausible
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const problems = computed(() => ({
  email: EMAIL.test(f.email) ? '' : '이메일 형식으로 적어 주세요.',
  password: f.password.length >= 8 ? '' : '비밀번호는 8자 이상이에요.',
  nickname: f.nickname.trim().length >= 2 && f.nickname.trim().length <= 20 ? '' : '별칭은 2~20자예요.',
  desiredJob: f.desiredJob ? '' : '희망 직무를 골라 주세요.',
  experienceYears: Number.isInteger(f.experienceYears) && f.experienceYears >= 0 && f.experienceYears <= 40 ? '' : '0~40 사이 정수로 적어 주세요.',
  bio: f.bio.length <= 300 ? '' : '300자 이하로 줄여 주세요.',
  consent: f.consent ? '' : '안내를 확인하고 동의해 주세요.',
}))
const show = (k) => (tried.value || touched[k]) && problems.value[k]
const valid = computed(() => Object.values(problems.value).every((p) => !p))
const inviteOk = computed(() => !props.token || invite.value?.valid)

function afterLogin(account) {
  const next = route.query.next
  if (next && account.status === 'ACTIVE') return router.replace(next)
  if (account.status === 'PENDING_REVIEW') return router.replace('/me/review')
  if (account.status === 'ACTIVE' && props.token) return router.replace({ path: '/me/start', query: { invite: props.token } })
  router.replace('/me')
}

async function signup() {
  tried.value = true
  if (!valid.value || !inviteOk.value) return
  busy.value = true
  error.value = ''
  try {
    const r = await api.candidateSignup({ inviteToken: props.token, ...f, nickname: f.nickname.trim(), bio: f.bio.trim() || null })
    auth.setCandidate(r.token)
    router.replace('/me/review')
  } catch (e) {
    error.value = e.status === 409 ? '이미 가입한 이메일이에요. 로그인해 주세요.' : e.message
  } finally {
    busy.value = false
  }
}

async function signin() {
  busy.value = true
  error.value = ''
  try {
    const r = await api.candidateLogin(login.email, login.password)
    auth.setCandidate(r.token)
    afterLogin(r.account)
  } catch (e) {
    error.value = e.status === 401 ? '이메일이나 비밀번호가 맞지 않아요.' : e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page narrow">
    <template v-if="props.token">
      <h1>{{ invite?.company ? `${invite.company}에서 초대했어요` : '초대 링크' }}</h1>
      <p class="sub">계정을 만들면 에이전트가 가입 정보를 확인하고, 확인이 끝나면 바로 평가를 시작할 수 있어요.</p>
    </template>
    <template v-else>
      <h1>지원자 로그인</h1>
      <p class="sub">가입은 채용 담당자가 보낸 초대 링크에서 할 수 있어요. <RouterLink to="/join/demo">데모 초대 링크</RouterLink></p>
    </template>

    <p v-if="invite && !invite.valid" class="chip red">{{ invite.message }}</p>
    <div v-if="me" class="card signed">
      <span><b>{{ me.nickname }}</b>님으로 로그인돼 있어요.</span>
      <RouterLink class="btn sm primary" :to="props.token && me.status === 'ACTIVE' ? { path: '/me/start', query: { invite: props.token } } : '/me'">
        {{ props.token && me.status === 'ACTIVE' ? '이 초대로 평가 시작' : '내 평가로' }}
      </RouterLink>
    </div>

    <div v-if="props.token" class="tabs">
      <button :class="{ on: mode === 'signup' }" @click="mode = 'signup'">처음이에요</button>
      <button :class="{ on: mode === 'login' }" @click="mode = 'login'">이미 계정이 있어요</button>
    </div>

    <Transition name="swap" mode="out-in">
      <form v-if="mode === 'signup'" key="s" class="card form" novalidate @submit.prevent="signup">
        <div class="grid">
          <div class="field" :class="{ invalid: show('email') }">
            <label for="email">이메일</label>
            <input id="email" v-model.trim="f.email" class="text" type="email" autocomplete="email" @blur="touched.email = true" />
            <span v-if="show('email')" class="bad">{{ problems.email }}</span>
          </div>
          <div class="field" :class="{ invalid: show('password') }">
            <label for="password">비밀번호</label>
            <input id="password" v-model="f.password" class="text" type="password" autocomplete="new-password" @blur="touched.password = true" />
            <span v-if="show('password')" class="bad">{{ problems.password }}</span>
            <span v-else class="hint">8자 이상</span>
          </div>
          <div class="field" :class="{ invalid: show('nickname') }">
            <label for="nickname">별칭</label>
            <input id="nickname" v-model="f.nickname" class="text" maxlength="20" placeholder="대화방에서 보일 이름" @blur="touched.nickname = true" />
            <span v-if="show('nickname')" class="bad">{{ problems.nickname }}</span>
            <span v-else class="hint">실명 대신 별칭을 써 주세요</span>
          </div>
          <div class="field" :class="{ invalid: show('experienceYears') }">
            <label for="exp">경력 (년)</label>
            <input id="exp" v-model.number="f.experienceYears" class="text" type="number" min="0" max="40" step="1" @blur="touched.experienceYears = true" />
            <span v-if="show('experienceYears')" class="bad">{{ problems.experienceYears }}</span>
            <span v-else class="hint">신입이면 0</span>
          </div>
        </div>

        <div class="field" :class="{ invalid: show('desiredJob') }">
          <label>희망 직무</label>
          <div class="pills">
            <button v-for="j in meta?.dilemma.jobs" :key="j.id" type="button" class="pill" :class="{ on: f.desiredJob === j.id }" @click="f.desiredJob = j.id">{{ j.label }}</button>
          </div>
          <span v-if="show('desiredJob')" class="bad">{{ problems.desiredJob }}</span>
        </div>
        <div class="field">
          <label>관심 산업 <span class="hint">(선택)</span></label>
          <div class="pills">
            <button v-for="i in meta?.dilemma.industries" :key="i.id" type="button" class="pill" :class="{ on: f.industry === i.id }" @click="f.industry = f.industry === i.id ? null : i.id">{{ i.label }}</button>
          </div>
        </div>
        <div class="field" :class="{ invalid: show('bio') }">
          <label for="bio">한 줄 소개 <span class="hint">(선택)</span></label>
          <textarea id="bio" v-model="f.bio" class="text" rows="2" maxlength="320" placeholder="어떤 일을 해 왔는지 짧게" @blur="touched.bio = true" />
          <span :class="show('bio') ? 'bad' : 'hint'">{{ f.bio.length }}/300</span>
        </div>

        <label class="consent" :class="{ invalid: show('consent') }">
          <input v-model="f.consent" type="checkbox" />
          <span>입력한 가입 정보는 <b>에이전트가 가입 요건과 입력값을 점검</b>하는 데 쓰이고, 애매한 경우 <b>채용 담당자가 직접 확인</b>한다는 점에 동의합니다.</span>
        </label>

        <p v-if="error" class="chip red">{{ error }}</p>
        <button class="btn primary go" :disabled="busy || !inviteOk">{{ busy ? '가입하는 중…' : '가입하고 계정 확인 받기' }}</button>
      </form>

      <form v-else key="l" class="card form" @submit.prevent="signin">
        <div class="field">
          <label for="lemail">이메일</label>
          <input id="lemail" v-model.trim="login.email" class="text" type="email" required autocomplete="username" />
        </div>
        <div class="field">
          <label for="lpw">비밀번호</label>
          <input id="lpw" v-model="login.password" class="text" type="password" required autocomplete="current-password" />
        </div>
        <p v-if="error" class="chip red">{{ error }}</p>
        <button class="btn primary go" :disabled="busy">{{ busy ? '확인 중…' : '로그인' }}</button>
      </form>
    </Transition>
  </main>
</template>

<style scoped>
.narrow { max-width: 640px; }
.signed { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 16px; margin-bottom: 14px; }
.tabs { display: inline-flex; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 3px; margin-bottom: 12px; }
.tabs button { border: 0; background: transparent; padding: 7px 14px; border-radius: 8px; font-weight: 600; color: var(--muted); transition: background 0.2s, color 0.2s; }
.tabs button.on { background: var(--brand-soft); color: var(--brand); }
.form { display: flex; flex-direction: column; gap: 16px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.consent { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border-radius: 10px; background: var(--bg); font-size: 13px; cursor: pointer; border: 1px solid transparent; }
.consent.invalid { border-color: #f87171; }
.consent input { margin-top: 3px; }
.go { padding: 12px; font-size: 15px; }
.swap-enter-active, .swap-leave-active { transition: opacity 0.15s ease; }
.swap-enter-from, .swap-leave-to { opacity: 0; }
@media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
