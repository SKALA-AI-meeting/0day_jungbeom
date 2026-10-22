<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api, auth } from '../../api'
import { MS_LABEL } from '../../constants'
import { inbox } from '../../state/inbox'

const rows = ref([])
const tasks = ref([])
const invites = ref([])
const accounts = ref([])
const meta = ref(null)
const error = ref('')
const inv = ref({ alias: '', email: '' })
const created = ref(null)
const loaded = ref(false) // the empty-state texts wait for the first answer
const now = ref(Date.now())
let timer

async function load() {
  try {
    ;[rows.value, tasks.value, invites.value, accounts.value] = await Promise.all([
      api.adminList(), api.myTasks(auth.admin()), api.adminInvites(), api.accounts(),
    ])
    error.value = ''
    now.value = Date.now()
    refreshStale(rows.value)
  } catch (e) {
    if (e.status !== 401) error.value = e.message || '목록을 불러오지 못했어요.' // 401 is routed to login by the API client
  } finally {
    loaded.value = true
  }
}

// Rows carry analytics_status (api-contract §5). When the set of sessions whose snapshot is not fresh changes,
// ask Spring once to refresh up to 20 of them (it creates or reuses ANALYTICS tasks); the 5 s poll alone never asks again.
// A row reads "분석 갱신 중" only while a task it asked for may still be running; after that (task failed, agent down)
// it says plainly that the numbers are behind, and the session page offers "다시 계산".
const REFRESH_MS = 90_000
const notFresh = (r) => !!r.analytics_status && r.analytics_status !== 'fresh'
const asked = ref({}) // sessionId -> when its refresh was asked for
const refreshing = (r) => notFresh(r) && now.value - (asked.value[r.id] || 0) < REFRESH_MS
let staleKey = ''
function refreshStale(list) {
  const ids = list.filter(notFresh).map((r) => r.id)
  const key = [...ids].sort().join(',')
  if (key === staleKey) return
  staleKey = key
  if (!ids.length) return
  api.refreshAnalytics(ids.slice(0, 20))
    .then((started) => {
      const at = Date.now()
      asked.value = { ...asked.value, ...Object.fromEntries(started.map((x) => [x.sessionId, at])) }
    })
    .catch(() => {}) // best effort: the rows say the numbers are behind either way
}
onMounted(() => {
  api.meta().then((m) => (meta.value = m)).catch(() => {}) // labels only (jobLabel falls back to the id); /api/meta goes through the agent, never awaited
  load()
  timer = setInterval(load, 5000)
})
onBeforeUnmount(() => clearInterval(timer))

async function createInvite() {
  try {
    const r = await api.adminInvite(inv.value.alias || null, inv.value.email)
    created.value = `${location.origin}${r.path}`
    inv.value = { alias: '', email: '' }
    await load()
  } catch (e) {
    error.value = e.message
  }
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text) } catch { /* select manually */ }
}

const ACCOUNT = { ACTIVE: ['green', '활성'], PENDING_REVIEW: ['blue', '확인 중'], REVIEW_ERROR: ['amber', '검토 실패'], REJECTED: ['red', '반려'] }
const BASIS = { auto_clean: '에이전트 자동 승인', auto_schema: '요건 불충족 자동 반려', admin_approved: '담당자 승인', admin_rejected: '담당자 반려' }
const basisOf = (a) => (a.review?.manual_by ? (a.status === 'ACTIVE' ? '담당자 직접 승인' : '담당자 직접 반려') : BASIS[a.review?.basis])
const jobLabel = (id) => meta.value?.dilemma.jobs.find((x) => x.id === id)?.label || id

const MS = ['communicate', 'coordinate', 'compromise', 'persuade']
const STATUS = { active: ['blue', '진행 중'], completed: ['green', '완료'] }
const REPORT = { ready: ['green', '리포트 준비됨'], awaiting_approval: ['amber', '승인 대기'], pending: ['blue', '생성 중'], failed: ['red', '실패'], rejected: ['gray', '반려됨'], dismissed: ['gray', '넘김'], none: ['gray', '대기'] }
const TASK = { QUEUED: 'gray', RUNNING: 'blue', WAITING_APPROVAL: 'amber', DONE: 'green', FAILED: 'red', REJECTED: 'gray' }
const traceOf = (t) => {
  const tr = Array.isArray(t.trace) ? t.trace : []
  if (!tr.length) return ''
  const llm = tr.reduce((a, x) => a + (x.llm_calls || 0), 0)
  const tok = tr.reduce((a, x) => a + (x.tokens_in || 0) + (x.tokens_out || 0), 0)
  return `trace ${String(tr[0].trace_id || '').slice(0, 8)} · LLM ${llm}회 · ${tok.toLocaleString()} tok${tr.some((x) => x.retries || x.fallbacks) ? ' · 복구 있음' : ''}`
}
const fmt = (t) => new Date(typeof t === 'number' ? t * 1000 : t).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <main class="page">
    <h1>대시보드</h1>
    <p class="sub">세션별 진행 단계와 관찰 근거를 한눈에 확인합니다. 점수나 합격 표시는 없습니다.</p>
    <p v-if="error" class="chip red">{{ error }}</p>
    <Transition name="drop">
      <RouterLink v-if="inbox.count" to="/admin/inbox" class="banner">
        <span class="pulse" /> 에이전트가 결정을 기다리는 항목 <b>{{ inbox.count }}건</b> · 이슈 체크리스트 열기 →
      </RouterLink>
    </Transition>

    <section class="card">
      <p v-if="!loaded" class="muted">불러오는 중…</p>
      <p v-else-if="!rows.length" class="muted">아직 세션이 없어요. 지원자 화면에서 대화를 시작해 보세요.</p>
      <table v-else>
        <thead><tr><th>별칭</th><th>시나리오</th><th>가치 축 · 선택</th><th>진행</th><th>상태</th><th>메시지</th><th>근거</th><th>리포트</th><th>시작</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" tabindex="0" @click="$router.push(`/admin/sessions/${r.id}`)" @keydown.enter="$router.push(`/admin/sessions/${r.id}`)">
            <td>
              <b>{{ r.alias }}</b>
              <div v-if="refreshing(r)" class="anl" title="차트와 수치를 최신 대화 기준으로 다시 계산하고 있어요"><i aria-hidden="true" />분석 갱신 중</div>
              <div v-else-if="notFresh(r)" class="anl idle" title="최근 대화가 아직 차트와 수치에 반영되지 않았어요. 세션을 열면 다시 계산할 수 있어요.">분석 최신 아님</div>
            </td>
            <td>{{ r.category }}</td>
            <td>
              <template v-if="r.axis"><span class="small">{{ r.axis }}</span><br /><span class="chip" :class="r.choice ? 'blue' : 'gray'">{{ r.choice || '미선택' }}</span></template>
              <span v-else class="muted small">–</span>
              <div v-if="r.condition" class="muted small">{{ r.condition }}</div>
            </td>
            <td>
              <div class="bar"><i v-for="(k, i) in MS" :key="k" :class="{ on: i <= r.milestone_idx }" :title="MS_LABEL[k]" /></div>
              <small class="muted">{{ MS_LABEL[MS[r.milestone_idx]] }}</small>
            </td>
            <td><span class="chip" :class="STATUS[r.status][0]">{{ STATUS[r.status][1] }}</span></td>
            <td>{{ r.messages }}</td>
            <td>{{ r.observations }}</td>
            <td><span class="chip" :class="(REPORT[r.report_status] || REPORT.none)[0]">{{ (REPORT[r.report_status] || REPORT.none)[1] }}</span></td>
            <td class="muted small">{{ fmt(r.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card accts">
      <h3>지원자 계정 <small class="muted">에이전트가 가입 요건과 입력값을 확인한 결과예요</small></h3>
      <p v-if="!loaded" class="muted">불러오는 중…</p>
      <p v-else-if="!accounts.length" class="muted">아직 가입한 지원자가 없어요. 아래에서 초대 링크를 만들어 보내 보세요.</p>
      <table v-else class="tasks">
        <thead><tr><th>별칭</th><th>이메일</th><th>직무 · 경력</th><th>상태</th><th>근거</th><th>가입</th></tr></thead>
        <tbody>
          <tr v-for="a in accounts.slice(0, 10)" :key="a.id" @click="['PENDING_REVIEW', 'REVIEW_ERROR'].includes(a.status) && inbox.count && $router.push('/admin/inbox')">
            <td><b>{{ a.nickname }}</b></td>
            <td class="muted small">{{ a.email }}</td>
            <td class="small">{{ jobLabel(a.desiredJob) }} · {{ a.experienceYears }}년</td>
            <td><span class="chip" :class="ACCOUNT[a.status]?.[0]">{{ ACCOUNT[a.status]?.[1] || a.status }}</span></td>
            <td class="muted small">{{ basisOf(a) || (a.status === 'PENDING_REVIEW' ? '에이전트 확인 중' : '–') }}<template v-if="a.review?.flags?.length"> · 확인 {{ a.review.flags.length }}건</template></td>
            <td class="muted small">{{ fmt(a.createdAt) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="two">
      <div class="card">
        <h3>지원자 초대</h3>
        <p class="muted small">1회용 링크를 만들어요. 지원자는 이 링크에서 가입하고, 72시간 뒤 만료돼요.</p>
        <form class="invite" @submit.prevent="createInvite">
          <input id="inv-alias" v-model="inv.alias" class="text" maxlength="20" placeholder="별칭 (선택)" />
          <input id="inv-email" v-model="inv.email" class="text" type="email" placeholder="이메일 (선택)" />
          <button class="btn primary">링크 만들기</button>
        </form>
        <p v-if="created" class="made"><code>{{ created }}</code> <button class="btn sm" @click="copy(created)">복사</button></p>
        <ul class="invites">
          <li v-for="i in invites.slice(0, 6)" :key="i.token">
            <code>{{ i.path }}</code> <span class="muted small">{{ i.alias || '별칭 없음' }} · {{ i.reusable ? '재사용(데모)' : i.usedAt ? '사용됨' : '만료 ' + fmt(i.expiresAt) }}</span>
          </li>
        </ul>
      </div>
      <div class="card">
        <h3>AI 작업 이력</h3>
        <p class="muted small">계정 확인·대화·리포트처럼 회사 안에서 실행된 에이전트 작업이에요. 분석 스냅숏 갱신은 세션 상세에서 볼 수 있어요. (GET /api/ai/tasks?mine=true)</p>
        <p v-if="!loaded" class="muted">불러오는 중…</p>
        <p v-else-if="!tasks.length" class="muted">아직 요청한 작업이 없어요.</p>
        <table v-else class="tasks">
          <tbody>
            <tr v-for="t in tasks.slice(0, 8)" :key="t.id" @click="t.sessionId && $router.push(`/admin/sessions/${t.sessionId}`)">
              <td><span class="chip" :class="TASK[t.status]">{{ t.status }}</span></td><td>{{ t.type }}</td>
              <td class="muted small">{{ fmt(t.createdAt) }}</td><td class="muted small">{{ t.error || traceOf(t) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>

<style scoped>
.banner { display: flex; align-items: center; gap: 10px; margin: 0 0 16px; padding: 12px 16px; border-radius: 12px; background: #fef3c7; color: #92400e; font-weight: 600; }
.banner:hover { text-decoration: none; filter: brightness(0.98); }
.pulse { width: 10px; height: 10px; border-radius: 50%; background: var(--warn); animation: ping 1.4s ease-in-out infinite; }
@keyframes ping { 0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--warn) 55%, transparent); } 50% { box-shadow: 0 0 0 7px transparent; } }
.drop-enter-active { transition: opacity 0.3s, transform 0.3s; }
.drop-enter-from { opacity: 0; transform: translateY(-6px); }
.accts { margin-top: 16px; }
.accts h3 small { font-weight: 500; font-size: 12px; margin-left: 6px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; }
.invite { display: flex; gap: 8px; flex-wrap: wrap; }
.invite .text { flex: 1; min-width: 140px; }
.made { margin: 10px 0 0; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.invites { list-style: none; padding: 0; margin: 12px 0 0; font-size: 13px; display: grid; gap: 4px; }
.tasks { width: 100%; font-size: 13px; }
.tasks td { padding: 6px 8px; border-bottom: 1px solid var(--line); }
@media (max-width: 800px) { .two { grid-template-columns: 1fr; } }
.tok { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; }
.tok .text { max-width: 280px; }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; font-size: 12px; color: var(--muted); font-weight: 600; padding: 8px 10px; border-bottom: 1px solid var(--line); }
td { padding: 12px 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }
tbody tr { cursor: pointer; }
tbody tr:hover, tbody tr:focus-visible { background: var(--bg); }
tbody tr:focus-visible { outline: 2px solid var(--brand); outline-offset: -2px; }
.anl { display: inline-flex; align-items: center; gap: 5px; margin-top: 4px; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line); background: var(--bg); color: var(--muted); font-size: 11px; font-weight: 600; white-space: nowrap; }
.anl i { width: 6px; height: 6px; border-radius: 50%; background: var(--brand); animation: blink 1.6s ease-in-out infinite; }
.anl.idle { border-style: dashed; }
@keyframes blink { 50% { opacity: 0.3; } }
@media (prefers-reduced-motion: reduce) { .anl i, .pulse { animation: none; } }
.bar { display: flex; gap: 3px; width: 88px; }
.bar i { flex: 1; height: 6px; border-radius: 3px; background: var(--line); }
.bar i.on { background: var(--brand); }
</style>
