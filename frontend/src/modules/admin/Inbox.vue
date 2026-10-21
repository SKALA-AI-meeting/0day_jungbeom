<script setup>
// Human-in-the-loop issue checklist: every decision the agent handed to a person. Decide each one, then the agent resumes.
import { computed, onMounted, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../../api'
import CheckMark from '../../components/CheckMark.vue'
import { inbox, refreshInbox } from '../../state/inbox'

const route = useRoute()
const router = useRouter()
const after = () => (typeof route.query.next === 'string' && route.query.next.startsWith('/admin') ? route.query.next : '/admin')
const meta = ref(null)
const items = ref([])
const loaded = ref(false)
const open = ref(null)
const decisions = reactive({}) // item.id -> { approved, comment }
const comments = reactive({})
const submitting = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    const [r, m] = await Promise.all([refreshInbox(), api.meta()])
    meta.value = m
    if (!r.count) return router.replace(after()) // nothing is waiting on a person: straight on
    items.value = r.items
    open.value = r.items[0].id
  } catch (e) {
    error.value = e.message
  } finally {
    loaded.value = true
  }
})

const KIND = {
  ACCOUNT_REVIEW: ['blue', '계정 승인'],
  REPORT: ['amber', '리포트 공개'],
  ACCOUNT_REVIEW_ERROR: ['red', '검토 실패'],
  REPORT_FAILED: ['red', '리포트 실패'],
}
const REC = {
  approve: ['green', '에이전트 의견 · 승인해도 될 것 같아요'],
  reject: ['red', '에이전트 의견 · 반려를 권해요'],
  ask: ['amber', '에이전트 의견 · 사람이 판단해 주세요'],
  manual: ['gray', '에이전트가 끝내지 못했어요 · 직접 판단'],
  retry: ['amber', '에이전트 의견 · 다시 만들어 보세요'],
}
// Button labels come with the item (item.actions); these are the fallbacks per kind.
const ACTIONS = { REPORT: { approve: '공개 승인', reject: '반려' }, ACCOUNT_REVIEW_ERROR: { approve: '직접 승인', reject: '직접 반려' }, REPORT_FAILED: { approve: '다시 만들기', reject: '넘기기' } }
const act = (it, which) => it.actions?.[which] || ACTIONS[it.kind]?.[which] || (which === 'approve' ? '승인' : '반려')
// How a decision is carried out. A task waiting for approval resumes on its thread; other kinds call their own endpoint.
// Each returns { taskId, fresh } to follow on the next page, or { manual: true } when nothing runs afterwards.
const DECIDE = {
  REPORT_FAILED: async (it, d) => {
    if (!d.approved) { await api.dismissReport(it.sessionId); return { manual: true } }
    const r = await api.requestReport(it.sessionId)
    return { taskId: r.taskId, fresh: true } // a new task: its first approval request is a fresh one
  },
  default: async (it, d) => {
    if (it.taskId) { await api.approve(it.taskId, d.approved, d.comment); return { taskId: it.taskId } }
    await api.decideAccount(it.accountId, d.approved, d.comment)
    return { manual: true }
  },
}
const FIELD = { nickname: '별칭', email: '이메일', desired_job: '희망 직무', industry: '관심 산업', experience_years: '경력', bio: '소개' }
const SOURCE = { rule: '규칙', model: '모델', harness: '하네스' }
const label = (list, id) => meta.value?.dilemma[list].find((x) => x.id === id)?.label || id || '–'
const flagged = (it, field) => (it.flags || []).some((f) => f.field === field)
const fresh = computed(() => inbox.items.filter((i) => !items.value.some((x) => x.id === i.id)))
const decided = computed(() => items.value.filter((i) => decisions[i.id]).length)
const allDecided = computed(() => items.value.length > 0 && decided.value === items.value.length)
const fmt = (t) => new Date(t).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })

function decide(it, approved) {
  decisions[it.id] = { approved, comment: (comments[it.id] || '').trim() }
  const next = items.value.find((x) => !decisions[x.id])
  open.value = next ? next.id : null
}
function undo(it) {
  delete decisions[it.id]
  open.value = it.id
}
function addFresh() {
  items.value.push(...fresh.value)
  if (!open.value) open.value = items.value.find((x) => !decisions[x.id])?.id || null
}

async function submit() {
  submitting.value = true
  error.value = ''
  const jobs = []
  for (const it of items.value) {
    const d = decisions[it.id]
    const base = { kind: it.kind, name: it.subject?.label || '', approved: d.approved, label: act(it, d.approved ? 'approve' : 'reject') }
    try {
      jobs.push({ ...base, ...(await (DECIDE[it.kind] || DECIDE.default)(it, d)) })
    } catch (e) {
      // e.g. 409: someone else already decided it in another tab
      jobs.push({ ...base, error: e.message })
    }
  }
  refreshInbox().catch(() => {})
  router.push({ path: '/admin/working', query: { t: jobs.filter((j) => j.taskId).map((j) => j.taskId).join(','), next: after() }, state: { jobs } })
}
</script>

<template>
  <main class="page">
    <h1>이슈 체크리스트</h1>
    <p class="sub">에이전트가 사람의 결정을 기다리는 항목이에요. 모두 결정하면 에이전트가 이어서 반영하고 대시보드로 넘어가요.</p>
    <p v-if="error" class="chip red">{{ error }}</p>
    <p v-if="!loaded" class="muted">불러오는 중…</p>

    <template v-else-if="items.length">
      <div class="progress">
        <span><b>{{ decided }}</b> / {{ items.length }}건 결정함</span>
        <div class="track"><i :style="{ width: `${(decided / items.length) * 100}%` }" /></div>
        <button v-if="fresh.length" class="btn sm" @click="addFresh">새 항목 {{ fresh.length }}건 불러오기</button>
      </div>

      <TransitionGroup tag="ol" name="item" class="items">
        <li v-for="it in items" :key="it.id" class="card item" :class="{ open: open === it.id, done: decisions[it.id] }">
          <button class="head" :aria-expanded="open === it.id" :aria-label="`${it.subject?.label || ''} · ${it.title || it.kind}`" @click="open = open === it.id ? null : it.id">
            <span class="mark">
              <CheckMark v-if="decisions[it.id]?.approved" :size="24" />
              <span v-else-if="decisions[it.id]" class="no">✕</span>
              <span v-else class="ring" />
            </span>
            <span class="chip" :class="KIND[it.kind]?.[0] || 'gray'">{{ KIND[it.kind]?.[1] || it.kind }}</span>
            <span class="ttl"><b>{{ it.subject?.label || '–' }}</b> <span class="muted small">{{ it.title }}</span></span>
            <span v-if="decisions[it.id]" class="chip" :class="decisions[it.id].approved ? 'green' : 'red'">{{ act(it, decisions[it.id].approved ? 'approve' : 'reject') }}</span>
            <span class="muted small when">{{ fmt(it.createdAt) }}</span>
          </button>

          <div v-if="open === it.id" class="body">
            <p class="reason">{{ it.reason }}</p>
            <span v-if="it.recommendation" class="chip" :class="REC[it.recommendation]?.[0]">{{ REC[it.recommendation]?.[1] }}</span>

            <div v-if="it.subject?.profile" class="profile">
              <div :class="{ flag: flagged(it, 'nickname') }"><small>별칭</small><b>{{ it.subject.label }}</b></div>
              <div :class="{ flag: flagged(it, 'email') }"><small>이메일</small><b>{{ it.subject.detail }}</b></div>
              <div :class="{ flag: flagged(it, 'desired_job') }"><small>희망 직무</small><b>{{ label('jobs', it.subject.profile.desiredJob) }}</b></div>
              <div :class="{ flag: flagged(it, 'industry') }"><small>관심 산업</small><b>{{ it.subject.profile.industry ? label('industries', it.subject.profile.industry) : '–' }}</b></div>
              <div :class="{ flag: flagged(it, 'experience_years') }"><small>경력</small><b>{{ it.subject.profile.experienceYears }}년</b></div>
              <div class="wide" :class="{ flag: flagged(it, 'bio') }"><small>소개</small><b>{{ it.subject.profile.bio || '–' }}</b></div>
            </div>

            <ul v-if="it.flags?.length" class="flags">
              <li v-for="(f, i) in it.flags" :key="i">
                <span class="src" :class="f.source">{{ SOURCE[f.source] || f.source }}</span>
                <b>{{ FIELD[f.field] || f.field }}</b> {{ f.message }}
              </li>
            </ul>
            <ul v-if="it.checks?.length" class="checks">
              <li v-for="c in it.checks" :key="c.stage + c.name" :class="{ ok: c.ok }"><span>{{ c.ok ? '✓' : '!' }}</span>{{ c.name }} · <span class="muted">{{ c.detail }}</span></li>
            </ul>

            <div v-if="it.kind === 'REPORT' && it.draft" class="draft">
              <div v-for="(c, cid) in it.draft" :key="cid"><b>{{ cid }} {{ c.name }}</b> <span class="muted small">근거 {{ c.count }}건</span><p>{{ c.summary }}</p></div>
              <RouterLink v-if="it.sessionId" :to="`/admin/sessions/${it.sessionId}`" class="small">대화와 근거 전체 보기 →</RouterLink>
            </div>
            <div v-else-if="it.kind === 'REPORT_FAILED'" class="draft">
              <span class="small"><b>{{ act(it, 'approve') }}</b> · 리포트 작업을 새로 시작해요. 초안이 나오면 이 체크리스트에 다시 올라와요.</span>
              <span class="small"><b>{{ act(it, 'reject') }}</b> · 리포트 없이 이 세션을 체크리스트에서 내려요.</span>
              <RouterLink v-if="it.sessionId" :to="`/admin/sessions/${it.sessionId}`" class="small">세션 상세 보기 →</RouterLink>
            </div>

            <div class="acts">
              <input v-if="it.kind !== 'REPORT_FAILED'" v-model="comments[it.id]" class="text" maxlength="500" placeholder="메모 (선택) · 에이전트와 기록에 남아요" />
              <span v-else class="spacer" />
              <button class="btn danger" @click="decide(it, false)">{{ act(it, 'reject') }}</button>
              <button class="btn primary" @click="decide(it, true)">{{ act(it, 'approve') }}</button>
            </div>
          </div>
          <div v-else-if="decisions[it.id]" class="sum">
            <span class="muted small">{{ decisions[it.id].comment || '메모 없음' }}</span>
            <button class="btn sm" @click.stop="undo(it)">되돌리기</button>
          </div>
        </li>
      </TransitionGroup>

      <div class="bar" :class="{ ready: allDecided }">
        <RouterLink :to="after()" class="btn link">나중에 처리하기</RouterLink>
        <span class="muted small">{{ allDecided ? '모두 결정했어요. 반영하면 에이전트가 멈춘 지점부터 이어서 작업해요.' : `${items.length - decided}건 남았어요` }}</span>
        <button class="btn primary" :disabled="!allDecided || submitting" @click="submit">{{ submitting ? '보내는 중…' : '결정 반영하고 에이전트 이어서 작업' }}</button>
      </div>
    </template>
  </main>
</template>

<style scoped>
.progress { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.track { flex: 1; height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; }
.track i { display: block; height: 100%; background: var(--ok); border-radius: 3px; transition: width 0.45s cubic-bezier(0.3, 0.9, 0.4, 1); }
.items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.item { padding: 0; overflow: hidden; transition: box-shadow 0.2s, border-color 0.2s, opacity 0.2s; }
.item.open { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
.item.done:not(.open) { opacity: 0.8; }
.head { width: 100%; display: flex; align-items: center; gap: 10px; padding: 14px 16px; border: 0; background: none; color: var(--ink); text-align: left; }
.mark { width: 24px; height: 24px; flex: none; display: grid; place-items: center; }
.ring { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--warn); animation: beat 1.4s ease-in-out infinite; }
.no { width: 24px; height: 24px; border-radius: 50%; background: #dc2626; color: #fff; display: grid; place-items: center; font-size: 12px; font-weight: 800; animation: pop 0.3s ease both; }
.ttl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.when { flex: none; }
.body { padding: 0 16px 16px 50px; display: flex; flex-direction: column; gap: 12px; animation: unfold 0.25s ease; }
.reason { margin: 0; }
.body > .chip { align-self: flex-start; }
.profile { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.profile div { display: flex; flex-direction: column; padding: 8px 10px; border-radius: 8px; background: var(--bg); border: 1px solid transparent; min-width: 0; }
.profile div.wide { grid-column: 1 / -1; }
.profile small { font-size: 11px; color: var(--muted); }
.profile b { font-weight: 600; overflow-wrap: anywhere; }
.profile div.flag { border-color: var(--warn); background: color-mix(in srgb, #fef3c7 60%, var(--panel)); }
.flags, .checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.src { display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 6px; margin-right: 6px; background: var(--line); color: var(--muted); }
.src.model { background: #ede9fe; color: #6d28d9; }
.src.harness { background: #fee2e2; color: #991b1b; }
.checks li span:first-child { display: inline-grid; place-items: center; width: 16px; height: 16px; border-radius: 50%; margin-right: 6px; font-size: 10px; font-weight: 800; background: var(--warn); color: #fff; }
.checks li.ok span:first-child { background: var(--ok); }
.draft { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-radius: 10px; background: var(--bg); }
.draft p { margin: 2px 0 0; font-size: 13px; }
.acts { display: flex; gap: 8px; }
.acts .text, .acts .spacer { flex: 1; }
.sum { display: flex; justify-content: space-between; align-items: center; padding: 0 16px 12px 50px; }
.bar { position: sticky; bottom: 0; margin-top: 18px; display: flex; align-items: center; gap: 14px; padding: 12px 16px; border-radius: 14px; background: var(--panel); border: 1px solid var(--line); box-shadow: 0 -4px 18px rgba(15, 23, 42, 0.06); transition: border-color 0.3s; }
.bar.ready { border-color: var(--ok); }
.bar > span { flex: 1; }
.item-enter-active, .item-move { transition: opacity 0.3s, transform 0.3s; }
.item-enter-from { opacity: 0; transform: translateY(8px); }
@keyframes beat { 0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--warn) 50%, transparent); } 50% { box-shadow: 0 0 0 6px transparent; } }
@keyframes pop { from { transform: scale(0.4); } }
@keyframes unfold { from { opacity: 0; transform: translateY(-4px); } }
@media (prefers-reduced-motion: reduce) { .ring, .body, .no { animation: none; } }
@media (max-width: 700px) { .profile { grid-template-columns: 1fr 1fr; } .body, .sum { padding-left: 16px; } .when { display: none; } }
</style>
