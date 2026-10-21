<script setup>
// The agent screens a new account: schema → normality → (담당자 확인) → 반영. Stage names only; flags stay with the admin.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api, streamReview } from '../../api'
import CheckMark from '../../components/CheckMark.vue'
import StageChecklist from '../../components/StageChecklist.vue'

const router = useRouter()
const me = ref(null)
const error = ref('')
const PLAN = [
  ['load', '가입 정보 불러오기'],
  ['schema', '가입 요건 확인'],
  ['normality', '입력값이 자연스러운지 점검'],
  ['apply', '결과 반영'],
]
const steps = ref(PLAN.map(([key, label]) => ({ key, label, status: 'pending' })))
const finished = ref(false)
let alive = true
let auto

const outcome = computed(() => me.value?.status)
const waiting = computed(() => steps.value.some((s) => s.status === 'waiting'))

function mark(key, status, label) {
  let s = steps.value.find((x) => x.key === key)
  if (!s) {
    // admin_review only appears when the agent hands the decision to a person: slot it in before "결과 반영"
    s = { key, label: label || key, status: 'pending' }
    const at = steps.value.findIndex((x) => x.key === 'apply')
    steps.value.splice(at < 0 ? steps.value.length : at, 0, s)
  }
  const idx = steps.value.indexOf(s)
  steps.value.forEach((x, i) => { if (i < idx) settle(x) })
  s.status = { done: 'done', failed: 'failed', waiting: 'waiting' }[status] || 'running'
}
// a stage behind the current one is over: finished if it started, skipped if it never ran (e.g. schema failed)
const settle = (x) => { x.status = x.status === 'pending' ? 'skipped' : x.status === 'failed' ? 'failed' : 'done' }

function onEvent(ev) {
  const d = ev.data || {}
  if (ev.type === 'PROGRESS') mark(d.stage, d.status, d.stage === 'admin_review' ? '담당자 확인' : d.label)
  else if (ev.type === 'DONE') {
    steps.value.forEach(settle)
    finished.value = true
  } else if (ev.type === 'FAILED') {
    const s = steps.value.find((x) => ['running', 'waiting'].includes(x.status)) || steps.value.at(-1)
    s.status = 'failed'
    finished.value = true
  }
}

async function follow() {
  // the stream ends at DONE/FAILED, or when the connection times out while a person is deciding: then reconnect
  while (alive && !finished.value) {
    try {
      await streamReview(onEvent)
    } catch (e) {
      if (e.status === 404) break // no review task (an account made before reviews existed)
    }
    if (!finished.value && alive) {
      me.value = await api.me().catch(() => me.value)
      if (me.value && me.value.status !== 'PENDING_REVIEW') break
      await new Promise((r) => setTimeout(r, 3000))
    }
  }
  // the account row can land a moment after the stream's last event
  for (let i = 0; alive && i < 6; i++) {
    me.value = await api.me().catch(() => me.value)
    if (me.value?.status !== 'PENDING_REVIEW') break
    await new Promise((r) => setTimeout(r, 700))
  }
  if (me.value?.status === 'ACTIVE') auto = setTimeout(() => alive && router.replace('/me/start'), 2600)
}

onMounted(async () => {
  try {
    me.value = await api.me()
  } catch (e) {
    error.value = e.message
    return
  }
  follow()
})
onBeforeUnmount(() => { alive = false; clearTimeout(auto) })
</script>

<template>
  <main class="page narrow">
    <h1>{{ outcome === 'ACTIVE' ? '계정 확인이 끝났어요' : outcome === 'REJECTED' ? '계정 확인 결과' : '계정을 확인하고 있어요' }}</h1>
    <p class="sub">에이전트가 가입 요건과 입력값을 차례로 점검해요. 확인이 애매하면 채용 담당자가 직접 보고 결정해요.</p>
    <p v-if="error" class="chip red">{{ error }}</p>

    <section v-if="me" class="card">
      <div class="who">
        <span class="av">{{ me.nickname.slice(0, 1) }}</span>
        <div><b>{{ me.nickname }}</b><small class="muted">{{ me.email }} · {{ me.company }}</small></div>
      </div>
      <StageChecklist :steps="steps" />

      <Transition name="fade">
        <div v-if="waiting && !finished" class="note amber">
          담당자가 확인하고 있어요. 이 화면을 닫아도 괜찮아요. 다시 로그인하면 결과를 볼 수 있어요.
        </div>
      </Transition>

      <Transition name="fade">
        <div v-if="finished || (outcome && outcome !== 'PENDING_REVIEW')" class="result">
          <template v-if="outcome === 'ACTIVE'">
            <CheckMark :size="40" />
            <div>
              <b>확인이 끝났어요. 평가를 시작할 수 있어요.</b>
              <small class="muted">잠시 뒤 평가 시작 화면으로 이동해요.</small>
            </div>
            <RouterLink to="/me/start" class="btn primary">지금 시작</RouterLink>
          </template>
          <template v-else-if="outcome === 'REJECTED'">
            <span class="x">!</span>
            <div><b>이번 평가에는 참여할 수 없어요.</b><small class="muted">{{ me.rejectReason }}</small></div>
          </template>
          <template v-else-if="outcome === 'REVIEW_ERROR'">
            <span class="x amber">…</span>
            <div><b>자동 확인을 끝내지 못해 담당자가 직접 확인하고 있어요.</b><small class="muted">결과가 나오면 다시 로그인해 확인해 주세요.</small></div>
          </template>
        </div>
      </Transition>
    </section>
  </main>
</template>

<style scoped>
.narrow { max-width: 560px; }
.who { display: flex; gap: 12px; align-items: center; padding-bottom: 14px; margin-bottom: 8px; border-bottom: 1px solid var(--line); }
.who div { display: flex; flex-direction: column; line-height: 1.3; }
.av { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 50%; background: var(--brand); color: #fff; font-weight: 800; }
.note { margin-top: 12px; padding: 10px 12px; border-radius: 10px; font-size: 13px; }
.note.amber { background: #fef3c7; color: #92400e; }
.result { display: flex; gap: 14px; align-items: center; margin-top: 16px; padding: 14px; border-radius: 12px; background: var(--bg); }
.result div { display: flex; flex-direction: column; flex: 1; line-height: 1.4; }
.x { width: 40px; height: 40px; flex: none; display: grid; place-items: center; border-radius: 50%; background: #dc2626; color: #fff; font-weight: 800; font-size: 18px; }
.x.amber { background: var(--warn); }
.fade-enter-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.fade-enter-from { opacity: 0; transform: translateY(6px); }
</style>
