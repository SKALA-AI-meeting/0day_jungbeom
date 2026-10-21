<script setup>
// After the checklist: the agent resumes each paused task on its own thread. Follow them to the end, then the dashboard.
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, auth, streamTask } from '../../api'
import CheckMark from '../../components/CheckMark.vue'
import StageChecklist from '../../components/StageChecklist.vue'

const route = useRoute()
const router = useRouter()
const after = typeof route.query.next === 'string' && route.query.next.startsWith('/admin') ? route.query.next : '/admin'
const KIND = { ACCOUNT_REVIEW: '계정 승인', REPORT: '리포트 공개', ACCOUNT_REVIEW_ERROR: '계정 직접 결정' }
const TOOL = {
  'business.decide_account': '계정 상태 저장',
  'business.save_report': '리포트 저장',
  'business.get_account': '가입 정보 다시 불러오기',
  'business.get_session_state': '세션 불러오기',
}
const jobs = ref([])
const leaving = ref(false)
let alive = true
let auto

const allDone = computed(() => jobs.value.length > 0 && jobs.value.every((j) => ['done', 'failed'].includes(j.status)))
const okCount = computed(() => jobs.value.filter((j) => j.status === 'done').length)

function job(j) {
  return reactive({ ...j, steps: [], status: j.error ? 'failed' : j.manual ? 'done' : 'running', note: j.error || '' })
}

function step(j, key, label, status) {
  let s = j.steps.find((x) => x.key === key)
  if (!s) j.steps.push((s = { key, label, status: 'running' }))
  s.status = status
}

async function follow(j) {
  let resumed = false // the replay starts with the run that asked for approval; show only what happened after it
  try {
    await streamTask(j.taskId, auth.admin(), (ev) => {
      const d = ev.data || {}
      if (ev.type === 'APPROVAL_REQUIRED') { resumed = true; j.steps = []; return }
      if (ev.type === 'DONE') {
        j.steps.forEach((s) => { if (s.status === 'running') s.status = 'done' })
        j.status = 'done'
        j.note = j.approved ? '승인을 반영했어요' : '반려를 반영했어요'
      } else if (ev.type === 'FAILED') {
        j.status = 'failed'
        j.note = d.error || '작업이 실패했어요'
      } else if (!resumed) return
      else if (ev.type === 'PROGRESS') step(j, `p:${d.stage}`, d.label, d.status === 'done' ? 'done' : 'running')
      else if (ev.type === 'TOOL_START') step(j, `t:${d.tool}`, TOOL[d.tool] || d.tool, 'running')
      else if (ev.type === 'TOOL_END') step(j, `t:${d.tool}`, TOOL[d.tool] || d.tool, d.ok === false ? 'failed' : 'done')
    })
  } catch (e) {
    if (j.status === 'running') { j.status = 'failed'; j.note = e.message }
  }
  if (j.status === 'running') {
    // stream closed without a terminal event: read the task once
    const t = await api.task(j.taskId, auth.admin()).catch(() => null)
    j.status = t && ['DONE', 'REJECTED'].includes(t.status) ? 'done' : 'failed'
    if (j.status === 'failed') j.note = t?.error || '결과를 확인하지 못했어요'
  }
}

onMounted(async () => {
  const fromState = window.history.state?.jobs
  const list = Array.isArray(fromState)
    ? fromState
    : String(route.query.t || '').split(',').filter(Boolean).map((taskId) => ({ taskId, kind: '', name: '' }))
  if (!list.length) return router.replace(after)
  jobs.value = list.map(job)
  // a reload loses the decision labels: fill the kind from the task
  await Promise.all(jobs.value.filter((j) => j.taskId && !j.kind).map(async (j) => {
    const t = await api.task(j.taskId, auth.admin()).catch(() => null)
    if (t) { j.kind = t.type; j.approved = t.status !== 'REJECTED' }
  }))
  await Promise.all(jobs.value.filter((j) => j.taskId && !j.error).map(follow))
  if (alive) auto = setTimeout(() => { leaving.value = true; setTimeout(() => alive && router.replace(after), 350) }, 1800)
})
onBeforeUnmount(() => { alive = false; clearTimeout(auto) })
</script>

<template>
  <main class="page narrow" :class="{ leaving }">
    <div class="hdr">
      <Transition name="swap" mode="out-in">
        <CheckMark v-if="allDone" key="ok" :size="44" />
        <span v-else key="spin" class="spin" />
      </Transition>
      <div>
        <h1>{{ allDone ? '모두 반영했어요' : '에이전트가 결정을 반영하는 중' }}</h1>
        <p class="sub">{{ allDone ? `${okCount}/${jobs.length}건 완료 · 잠시 뒤 대시보드로 이동해요` : '멈췄던 작업이 같은 스레드에서 이어서 실행돼요. 승인한 항목만 저장돼요.' }}</p>
      </div>
    </div>

    <TransitionGroup tag="ul" name="job" class="jobs">
      <li v-for="(j, i) in jobs" :key="j.taskId || `m${i}`" class="card job" :class="j.status" :style="{ transitionDelay: `${i * 60}ms` }">
        <div class="top">
          <span class="chip" :class="j.approved ? 'green' : 'red'">{{ j.approved ? '승인' : '반려' }}</span>
          <b>{{ j.name || '–' }}</b>
          <span class="muted small">{{ KIND[j.kind] || j.kind }}</span>
          <span class="state">
            <CheckMark v-if="j.status === 'done'" :size="20" />
            <span v-else-if="j.status === 'failed'" class="x">!</span>
            <span v-else class="dot" />
          </span>
        </div>
        <StageChecklist v-if="j.steps.length" :steps="j.steps" compact />
        <p v-if="j.note" class="note" :class="{ bad: j.status === 'failed' }">{{ j.note }}</p>
        <p v-else-if="j.manual" class="note">계정 상태를 직접 바꿨어요</p>
      </li>
    </TransitionGroup>

    <div class="foot">
      <RouterLink :to="after" class="btn" :class="{ primary: allDone }">대시보드로</RouterLink>
    </div>
  </main>
</template>

<style scoped>
.narrow { max-width: 640px; transition: opacity 0.3s; }
.leaving { opacity: 0; }
.hdr { display: flex; gap: 16px; align-items: center; margin-bottom: 16px; }
.hdr h1 { margin: 0; }
.hdr .sub { margin: 2px 0 0; }
.spin { width: 44px; height: 44px; flex: none; border-radius: 50%; border: 3px solid var(--brand-soft); border-top-color: var(--brand); animation: spin 0.9s linear infinite; }
.jobs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.job { padding: 14px 16px; transition: border-color 0.3s; }
.job.done { border-color: color-mix(in srgb, var(--ok) 45%, var(--line)); }
.job.failed { border-color: #fca5a5; }
.top { display: flex; gap: 10px; align-items: center; margin-bottom: 4px; }
.top b { flex: 1; }
.state { width: 20px; height: 20px; display: grid; place-items: center; }
.dot { width: 12px; height: 12px; border-radius: 50%; background: var(--brand); animation: beat 1.1s ease-in-out infinite; }
.x { width: 20px; height: 20px; border-radius: 50%; background: #dc2626; color: #fff; display: grid; place-items: center; font-size: 11px; font-weight: 800; }
.note { margin: 6px 0 0; font-size: 13px; color: var(--muted); }
.note.bad { color: #b91c1c; }
.foot { margin-top: 18px; display: flex; justify-content: flex-end; }
.job-enter-active { transition: opacity 0.35s, transform 0.35s; }
.job-enter-from { opacity: 0; transform: translateY(8px); }
.swap-enter-active, .swap-leave-active { transition: opacity 0.2s, transform 0.2s; }
.swap-enter-from, .swap-leave-to { opacity: 0; transform: scale(0.7); }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes beat { 50% { transform: scale(0.6); opacity: 0.5; } }
@media (prefers-reduced-motion: reduce) { .spin, .dot { animation: none; } }
</style>
