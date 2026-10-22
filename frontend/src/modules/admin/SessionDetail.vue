<script setup>
// Admin session detail. Since v4 (api-contract §5) every number and chart on this page comes from the analytics snapshot
// Spring stores (`analytics`, produced by analytics-mcp through an agent task); the page itself never counts and never
// calls the agent. Missing / stale snapshot -> one ANALYTICS task per page load, followed over SSE.
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, auth, streamTask } from '../../api'
import ArtifactTable from '../../components/ArtifactTable.vue'
import ArtifactViewer from '../../components/ArtifactViewer.vue'
import ChartGallery from '../../components/ChartGallery.vue'
import ChatBubble from '../../components/ChatBubble.vue'
import FigureChips from '../../components/FigureChips.vue'
import StageChecklist from '../../components/StageChecklist.vue'
import { COMP_COLOR, MODE_LABEL, MODE_POS, MS_LABEL, SIGNAL, kappaWord } from '../../constants'
import { normArtifacts, normCheck } from '../../utils/artifacts'
import { fmtAt } from '../../utils/charts'
import { renderMarkdown } from '../../utils/markdown'

const props = defineProps({ id: String })
const d = ref(null)
const meta = ref(null) // competency and persona names before the first snapshot only; /api/meta goes through the agent, so it is never awaited
const error = ref('')
const filter = ref({ cid: null, mkey: null })
const hl = ref(null)
const regen = ref(false)

async function load() {
  try {
    d.value = await api.adminGet(props.id)
    error.value = ''
  } catch (e) {
    error.value = e.status === 401 ? '관리자 로그인이 필요해요.' : e.message || '불러오지 못했어요.'
    return
  }
  ensureAnalytics()
}
onMounted(() => {
  load()
  api.meta().then((m) => (meta.value = m)).catch(() => {})
})

// ---------------------------------------------------------------- analytics snapshot
const an = computed(() => d.value?.analytics || null)
const anStatus = computed(() => d.value?.analytics_status || (an.value ? 'fresh' : 'missing'))
const ACTIVE = ['QUEUED', 'RUNNING']
const STEP = { 'analytics.session_analytics': '분석 도구 호출', 'business.save_analytics': '스냅숏 저장', 'analytics.render_charts': '차트 그리기' }
const plan = () => [
  { key: 't:analytics.session_analytics', label: STEP['analytics.session_analytics'], status: 'waiting' },
  { key: 't:business.save_analytics', label: STEP['business.save_analytics'], status: 'pending' },
]
const job = ref({ state: 'idle', steps: [], error: '', slow: false }) // state: idle | running | failed; slow: no word from the agent yet
const SLOW_MS = 15000 // a QUEUED task stays silent while the agent is down (it runs once the agent is back)
let autoStarted = false // one ANALYTICS task per page load; after that only the buttons start one
let stopJob = null

function ensureAnalytics() {
  if (!d.value || anStatus.value === 'fresh' || job.value.state !== 'idle') return
  const t = d.value.analytics_task
  if (t?.id && ACTIVE.includes(t.status)) {
    autoStarted = true
    follow(t.id) // already running (the dashboard's or another tab's): follow that one
  } else if (!autoStarted) {
    autoStarted = true
    runAnalytics()
  }
}
async function runAnalytics() {
  job.value = { state: 'running', steps: plan(), error: '', slow: false }
  try {
    const r = await api.requestAnalytics(props.id) // Spring hands back the running one when there is one
    await follow(r.taskId)
  } catch (e) {
    job.value.state = 'failed'
    job.value.error = e.message || '분석 작업을 시작하지 못했어요.'
  }
}
function step(key, label, status) {
  const steps = job.value.steps
  let s = steps.find((x) => x.key === key)
  if (!s) steps.push((s = { key, label, status }))
  s.status = status
  if (status === 'running') steps.forEach((x) => { if (x !== s && x.status === 'waiting') x.status = 'pending' })
}
async function follow(taskId) {
  stopJob?.abort()
  const stop = (stopJob = new AbortController())
  if (job.value.state !== 'running') job.value = { state: 'running', steps: plan(), error: '', slow: false }
  let end = null
  let why = ''
  const silent = setTimeout(() => { if (stop === stopJob) job.value.slow = true }, SLOW_MS)
  try {
    await streamTask(taskId, auth.admin(), (ev) => {
      clearTimeout(silent)
      job.value.slow = false
      const x = ev.data || {}
      if (ev.type === 'TOOL_START') step(`t:${x.tool}`, STEP[x.tool] || x.tool, 'running')
      else if (ev.type === 'TOOL_END') step(`t:${x.tool}`, STEP[x.tool] || x.tool, x.ok === false ? 'failed' : 'done')
      else if (ev.type === 'PROGRESS' && x.stage) step(`p:${x.stage}`, x.label || x.stage, x.status === 'done' ? 'done' : 'running')
      else if (ev.type === 'DONE' || ev.type === 'FAILED') { end = ev.type; why = x.error || '' }
    }, stop.signal)
  } catch (e) {
    if (e.name === 'AbortError') return // left the page or a newer follow took over
    why = e.message
  } finally {
    clearTimeout(silent)
  }
  if (stop !== stopJob) return
  job.value.slow = false
  if (!end) {
    // the stream closed without a terminal event: read the task once
    const t = await api.task(taskId, auth.admin()).catch(() => null)
    end = t?.status === 'DONE' ? 'DONE' : 'FAILED'
    why ||= t?.error || ''
  }
  if (end === 'DONE') {
    job.value.steps.forEach((s) => { if (s.status !== 'failed') s.status = 'done' })
    job.value.state = 'idle'
  } else {
    job.value.steps.forEach((s) => { if (s.status === 'running' || s.status === 'waiting') s.status = 'failed' })
    job.value.state = 'failed'
    job.value.error = why || '분석 작업이 실패했어요.'
  }
  await load()
}
onBeforeUnmount(() => stopJob?.abort())

const scn = computed(() => an.value?.context?.scenario || null)
const row = computed(() => an.value?.row || {})
const charts = computed(() => an.value?.charts || [])
const cap = (id) => charts.value.find((c) => c.id === id && c.available !== false)?.caption || ''
const hm = computed(() => an.value?.heatmap || { competencies: [], milestones: [], cells: [], max_n: 0 })
const comps = computed(() => (hm.value.competencies?.length ? hm.value.competencies : meta.value?.competencies || d.value?.report?.competencies || []))
const tl = computed(() => an.value?.timeline || [])
const cc = (cid) => COMP_COLOR[cid] || { fg: '#64748b', bg: 'var(--line)' }

const SPEAKER = { lead: '팀장', peer: '동료' }
// names: the snapshot's scenario, else the public catalog (/api/meta, not awaited); without either, roles (utils/artifacts ownerOf)
const catalogPersonas = computed(() => {
  const s = meta.value?.scenarios?.find((x) => x.id === d.value?.scenario_id)
  return s ? Object.fromEntries((s.personas || []).map((p) => [p.id, p])) : {}
})
const personas = computed(() => scn.value?.personas || catalogPersonas.value)
const whoOf = (sp) => (sp === 'user' ? { name: d.value.alias } : personas.value[sp] || { name: SPEAKER[sp] || sp })

// presentation only: which competencies were observed on a message (transcript badges) and the filtered evidence list
const obsByMsg = computed(() => {
  const m = {}
  for (const o of d.value?.observations || []) (m[o.msg_idx] ||= []).push(o)
  return m
})
const shown = computed(() =>
  (d.value?.observations || []).filter(
    (o) => (!filter.value.cid || o.competency === filter.value.cid) && (!filter.value.mkey || o.milestone === filter.value.mkey),
  ),
)
// heatmap cells come counted in the snapshot; index them by (competency, milestone)
const EMPTY = { n: 0, positive: 0, neutral: 0, risk: 0 }
const cellAt = computed(() => {
  const m = {}
  for (const c of hm.value.cells || []) m[`${c.cid}:${c.mkey}`] = c
  return m
})
const cellOf = (cid, mkey) => cellAt.value[`${cid}:${mkey}`] || EMPTY
const rowTotal = (cid) => hm.value.totals?.[cid] ?? 0
const heat = (c) => {
  if (!c.n) return {}
  const a = 0.15 + (c.n / Math.max(hm.value.max_n || 0, c.n, 1)) * 0.7 // 0.15 .. 0.85 of the busiest cell
  return { background: `color-mix(in srgb, var(--brand) ${Math.round(a * 100)}%, transparent)`, ...(a >= 0.55 ? { color: '#fff' } : {}) }
}
const reportComp = (cid) => d.value.report?.competencies?.find((c) => c.id === cid)
const hasFilter = computed(() => filter.value.cid || filter.value.mkey)

function toggle(cid, mkey) {
  const f = filter.value
  filter.value = f.cid === cid && f.mkey === mkey ? { cid: null, mkey: null } : { cid, mkey }
}
function toggleComp(cid) {
  const f = filter.value
  filter.value = f.cid === cid && !f.mkey ? { cid: null, mkey: null } : { cid, mkey: null }
}
function toggleMs(mkey) {
  const f = filter.value
  filter.value = f.mkey === mkey && !f.cid ? { cid: null, mkey: null } : { cid: null, mkey }
}
async function jump(o) {
  hl.value = o.msg_idx
  await nextTick()
  document.getElementById(`m-${o.msg_idx}`)?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' })
  setTimeout(() => (hl.value = null), 2500)
}
async function watchTask(taskId) {
  try {
    await streamTask(taskId, auth.admin(), () => {})
  } finally {
    await load()
  }
}
async function regenerate() {
  regen.value = true
  try {
    const r = await api.requestReport(props.id)
    await watchTask(r.taskId)
  } catch (e) {
    error.value = e.message
  } finally {
    regen.value = false
  }
}
const approving = ref(false)
const comment = ref('')
async function decide(approved) {
  approving.value = true
  try {
    const taskId = d.value.pending_approval.taskId
    await api.approve(taskId, approved, comment.value)
    await watchTask(taskId)
  } catch (e) {
    error.value = e.message
  } finally {
    approving.value = false
  }
}
const SRC = { survey: '설문', article: '기사', paper: '논문', report: '보고서' }
const REPORT_CHIP = { ready: ['green', '준비됨'], awaiting_approval: ['amber', '승인 대기'], pending: ['blue', '생성 중'], failed: ['red', '실패'], rejected: ['gray', '반려됨'], dismissed: ['gray', '넘김'], none: ['gray', '대기'] }
const pct = (x) => `${Math.round(x * 100)}%`
const FACET_ROLE = { lead: '팀장이', peer: '동료가' }
const dl = computed(() => an.value?.dilemma || null)
const poleOf = (side) => dl.value.axis.poles.find((p) => p.side === side)
const personaFor = (side) => Object.entries(dl.value.pole_of).find(([, s]) => s === side)?.[0]
const marker = computed(() => {
  const c = dl.value?.choice
  if (!c) return null
  const st = dl.value.axis.stats
  // a on the left, tie in the middle, b on the right
  if (c.pole === 'a') return (st.prefer_a / 2) * 100
  if (c.pole === 'b') return (1 - st.prefer_b / 2) * 100
  return (st.prefer_a + st.tie / 2) * 100
})
const det = computed(() => an.value?.detector || null)
const cond = computed(() => an.value?.condition || null)
const agreeOf = (cid) => det.value?.agreement?.per_competency?.[cid] || {}
// TKI plane: x = cooperativeness, y = assertiveness, both 1..5 -> 20..220 px
const px = (v) => 20 + ((v - 1) / 4) * 200
const py = (v) => 220 - ((v - 1) / 4) * 200
function jumpMsg(idx) {
  jump({ msg_idx: idx })
}

// shared artifacts: the candidate's markups next to the planted checkpoints (an objective signal, not a score)
const arts = computed(() => normArtifacts(d.value?.artifacts, d.value?.annotations))
const checks = computed(() => (an.value?.artifact_checks || []).map(normCheck))
const cpFigure = computed(() => an.value?.figures?.checkpoints || `0/${checks.value.length}`) // "N/M", counted by analytics-mcp
const artTitle = (id) => arts.value.find((a) => a.id === id)?.title || id
const viewer = ref({ id: null, line: null })
const openArt = computed(() => arts.value.find((a) => a.id === viewer.value.id) || null)
const markupsOf = (c) => {
  const a = arts.value.find((x) => x.id === c.artifactId)
  return (a?.annotations || []).filter((n) => c.annotationIds.map(String).includes(String(n.id)))
}

// dialogue ledger the turn harness keeps (api-contract §2); read-only here
const ledger = computed(() => d.value?.dialogue || null)
const WHO = (w) => (w === 'user' ? d.value.alias : personas.value[w]?.name || SPEAKER[w] || w)
const ISSUE = { open: ['amber', '열림'], agreed: ['green', '합의'], parked: ['gray', '보류'] }
const positions = computed(() => Object.entries(ledger.value?.positions || {}).filter(([, p]) => p && (p.claim || p.conceded)))

// the report's charts (frozen when it was approved) and the ones in a draft waiting for approval
const draft = computed(() => d.value?.pending_approval?.draft || {})
const reportCharts = computed(() => d.value?.report?.charts || [])
</script>

<template>
  <main v-if="d" class="wrap">
    <section class="main">
      <header class="head">
        <div>
          <RouterLink to="/admin" class="small">← 대시보드</RouterLink>
          <h1>{{ d.alias }} <small class="muted">· {{ row.category || scn?.category || d.scenario_id }}<template v-if="row.scenario_title || scn?.title"> — {{ row.scenario_title || scn.title }}</template></small></h1>
        </div>
        <div class="hr">
          <span class="chip" :class="d.status === 'completed' ? 'green' : 'blue'">{{ d.status === 'completed' ? '완료' : '진행 중' }}</span>
          <span class="chip" :class="REPORT_CHIP[d.report_status]?.[0] || 'gray'">
            리포트 {{ REPORT_CHIP[d.report_status]?.[1] || '대기' }}
          </span>
          <button v-if="d.status === 'completed' && !d.pending_approval" class="btn sm" :disabled="regen || d.report_status === 'pending'" @click="regenerate">{{ regen || d.report_status === 'pending' ? '생성 중…' : '리포트 다시 생성' }}</button>
          <button class="btn sm" @click="load">새로고침</button>
        </div>
      </header>
      <p v-if="error" class="chip red err">{{ error }}</p>

      <section v-if="d.pending_approval" class="card approve">
        <h2>리포트 승인 요청 <span class="chip amber">APPROVAL_REQUIRED</span></h2>
        <p class="small muted">Agent가 <code>{{ draft.tool || 'business.save_report' }}</code> 앞에서 멈췄어요. 승인하면 같은 thread id로 재개해 리포트를 저장하고 공개해요.</p>
        <FigureChips v-if="draft.figures" :figures="draft.figures" compact class="ap-figs" />
        <div class="drafts">
          <div v-for="(c, cid) in draft.draft || {}" :key="cid" class="draft">
            <b>{{ cid }} {{ c.name }}</b> <span class="muted small">근거 {{ c.count }}건</span>
            <p>{{ c.summary }}</p>
          </div>
        </div>
        <ChartGallery v-if="draft.charts?.length" :charts="draft.charts" compact class="ap-charts" />
        <div class="decide">
          <input id="approve-comment" v-model="comment" class="text" maxlength="500" placeholder="메모 (선택)" />
          <button class="btn primary" :disabled="approving" @click="decide(true)">승인하고 저장</button>
          <button class="btn" :disabled="approving" @click="decide(false)">반려</button>
        </div>
      </section>

      <!-- 0. analytics snapshot (api-contract §5): what every chart below is drawn from -->
      <section class="card snap" :class="{ wait: !an }">
        <div class="snap-h">
          <h2>분석 스냅숏 <small class="muted">analytics-mcp가 계산해 서버에 저장한 값이에요</small></h2>
          <span v-if="an" class="muted small">{{ fmtAt(an.computed_at) }} 기준</span>
        </div>
        <template v-if="an">
          <FigureChips v-if="an.figures" :figures="an.figures" />
          <p v-if="anStatus !== 'fresh'" class="note" :class="{ bad: job.state === 'failed' }" role="status">
            <template v-if="job.state === 'running'"><i class="live" aria-hidden="true" />최신 대화 반영 중…<span v-if="job.slow"> 에이전트가 아직 작업을 받지 않았어요. 에이전트가 다시 켜지면 이어서 계산해요.</span></template>
            <template v-else-if="job.state === 'failed'">
              최신 대화를 반영하지 못했어요. 아래는 이전 기준이에요.
              <button class="btn sm" @click="runAnalytics">다시 시도</button>
            </template>
            <template v-else>
              최근 대화가 아직 반영되지 않았어요. 아래는 이전 기준이에요.
              <button class="btn sm" @click="runAnalytics">다시 계산</button>
            </template>
          </p>
        </template>
        <div v-else class="wait-b">
          <div class="wait-t" role="status">
            <template v-if="job.state === 'running'">
              <b>분석 스냅숏을 만드는 중이에요</b>
              <p class="muted small">에이전트가 analytics-mcp로 타임라인·관찰 지도·디텍터 일치도를 계산해 저장해요. 끝나면 바로 보여 드려요.</p>
              <p v-if="job.slow" class="small">에이전트가 아직 작업을 받지 않았어요. 에이전트가 다시 켜지면 이어서 계산해요.</p>
            </template>
            <template v-else-if="job.state === 'failed'">
              <b>분석 스냅숏을 만들지 못했어요</b>
              <p class="small bad">{{ job.error }}</p>
              <button class="btn sm" @click="runAnalytics">다시 시도</button>
            </template>
            <template v-else>
              <b>아직 분석 스냅숏이 없어요</b>
              <p class="muted small">대화·관찰 근거·마크업은 아래에서 바로 볼 수 있어요. 차트는 분석을 마치면 보여요.</p>
              <button class="btn sm" @click="runAnalytics">분석 시작</button>
            </template>
          </div>
          <StageChecklist v-if="job.steps.length" :steps="job.steps" compact class="wait-s" />
        </div>
      </section>

      <!-- 1. milestone timeline -->
      <section v-if="an" class="card">
        <h2>논의 마일스톤 타임라인</h2>
        <p v-if="cap('timeline')" class="cap muted small">{{ cap('timeline') }}</p>
        <div class="tl">
          <button v-for="m in tl" :key="m.key" class="seg" :class="{ reached: m.reached, on: filter.mkey === m.key && !filter.cid }" :aria-pressed="filter.mkey === m.key && !filter.cid" @click="toggleMs(m.key)">
            <div class="seg-top"><b>{{ m.label || MS_LABEL[m.key] }}</b><small class="muted">{{ m.offset_label || '미도달' }}</small></div>
            <div class="seg-dots">
              <span v-for="o in m.obs || []" :key="o.id" class="d" :style="{ background: cc(o.competency).fg }" :title="`${o.competency} ${o.behavior}`" />
              <small v-if="!m.obs?.length" class="muted">근거 없음</small>
            </div>
            <small class="muted">메시지 {{ m.messages }}개 · 근거 {{ m.observations }}건</small>
          </button>
        </div>
      </section>

      <!-- 1.2 shared artifacts + planted checkpoints (item 4) -->
      <section v-if="arts.length" class="card">
        <h2>같이 확인한 과제 · 마크업 <small class="muted">행을 누르면 과제와 지원자 마크업을 열어요</small></h2>
        <ArtifactTable :artifacts="arts" :personas="personas" :checks="checks" :active="viewer.id" @open="(a) => (viewer = { id: a.id, line: null })" />
        <template v-if="checks.length">
          <h3 class="sub-h">
            심어 둔 확인 지점 <span class="chip" :class="parseInt(cpFigure, 10) ? 'green' : 'gray'">{{ cpFigure }} 발견</span>
          </h3>
          <p class="muted small chk-note">과제마다 일부러 넣어 둔 문제예요. 지원자의 마크업 줄 범위가 그 줄 ±1 안에 들면 ‘발견’이에요. 대화로만 짚은 경우는 여기에 잡히지 않으니 대화 원문과 함께 보세요.</p>
          <table class="agree chk">
            <thead><tr><th>과제</th><th>줄</th><th>심어 둔 문제</th><th>결과</th><th>지원자 마크업</th></tr></thead>
            <tbody>
              <tr v-for="c in checks" :key="`${c.artifactId}:${c.line}`" class="clk" tabindex="0" @click="viewer = { id: c.artifactId, line: c.line }" @keydown.enter="viewer = { id: c.artifactId, line: c.line }">
                <td>{{ artTitle(c.artifactId) }}</td>
                <td><b>L{{ c.line }}</b></td>
                <td>{{ c.issue }}</td>
                <td><span class="chip" :class="c.spotted ? 'green' : 'amber'">{{ c.spotted ? '발견' : '놓침' }}</span></td>
                <td class="small">
                  <template v-if="markupsOf(c).length"><div v-for="n in markupsOf(c)" :key="n.id">“{{ n.text }}”</div></template>
                  <span v-else class="muted">–</span>
                </td>
              </tr>
            </tbody>
          </table>
        </template>
      </section>

      <!-- 1.5 value dilemma (PR2) -->
      <section v-if="dl" class="card dl">
        <h2>가치 딜레마 <span class="chip blue">{{ dl.axis.id }} · {{ dl.axis.name }}</span></h2>
        <p class="muted small q">{{ dl.axis.question }} — 선택은 <b>성향 정보</b>이며 좋고 나쁨이 아닙니다.</p>

        <div class="dist">
          <div class="dist-lbl">
            <span><b>{{ poleOf('a').label }}</b> · {{ poleOf('a').desc }}<br /><small class="muted">{{ FACET_ROLE[personaFor('a')] }} 대변</small></span>
            <span class="r"><b>{{ poleOf('b').label }}</b> · {{ poleOf('b').desc }}<br /><small class="muted">{{ FACET_ROLE[personaFor('b')] }} 대변</small></span>
          </div>
          <div class="bar3">
            <i class="pa" :style="{ width: pct(dl.axis.stats.prefer_a) }">{{ pct(dl.axis.stats.prefer_a) }}</i>
            <i class="pt" :style="{ width: pct(dl.axis.stats.tie) }">{{ pct(dl.axis.stats.tie) }}</i>
            <i class="pb" :style="{ width: pct(dl.axis.stats.prefer_b) }">{{ pct(dl.axis.stats.prefer_b) }}</i>
            <span v-if="marker !== null" class="mk" :style="{ left: marker + '%' }">▼ 지원자</span>
          </div>
          <small class="muted">공개 설문 표본 N={{ dl.population.n.toLocaleString() }}명의 측면 점수 차(±{{ dl.population.pref_gap }}점 기준) 분포 · {{ dl.population.note }}</small>
        </div>

        <div class="two">
          <div class="pick" :class="{ none: !dl.choice }">
            <h3>지원자의 선택</h3>
            <template v-if="dl.choice">
              <span class="chip" :class="dl.choice.pole === 'both' ? 'amber' : 'blue'">{{ dl.choice.pole_label }}</span>
              <p class="opt-l">{{ dl.choice.label }}</p>
              <blockquote tabindex="0" @click="jumpMsg(dl.choice.msg_idx)" @keydown.enter="jumpMsg(dl.choice.msg_idx)">“{{ dl.choice.rationale }}” <small>→ 대화에서 보기</small></blockquote>
            </template>
            <p v-else class="muted">아직 선택하지 않았어요{{ d.status === 'completed' ? ' (선택 없이 종료)' : '' }}.</p>
            <details class="small">
              <summary>제시된 선택지 {{ dl.options.length }}개</summary>
              <ul><li v-for="o in dl.options" :key="o.id"><b>{{ o.pole === 'both' ? '통합안' : poleOf(o.pole).label }}</b> — {{ o.label }}</li></ul>
            </details>
          </div>
          <div class="basis">
            <h3>이 축의 데이터 근거</h3>
            <table class="kv">
              <tr><th>관계 유형</th><td>{{ dl.axis.relation }} · {{ poleOf('a').facet_ko }} ↔ {{ poleOf('b').facet_ko }}</td></tr>
              <tr><th>상관 r [95% CI]</th><td>{{ dl.axis.stats.r }} [{{ dl.axis.stats.r_ci[0] }}, {{ dl.axis.stats.r_ci[1] }}]</td></tr>
              <tr><th>상대 우선순위 r</th><td>{{ dl.axis.stats.r_ipsative }}</td></tr>
              <tr><th>동아시아 표본 r</th><td>{{ dl.axis.stats.r_east_asia }} (n={{ dl.population.n_east_asia }})</td></tr>
              <tr><th>절반 재현 r</th><td>{{ dl.axis.stats.split_half.map((h) => h.r).join(' / ') }}</td></tr>
              <tr><th>딜레마 균형</th><td>{{ dl.axis.stats.balance }} (0.5 = 완전 균형)</td></tr>
              <tr><th>선정 점수</th><td>{{ dl.axis.score }} / {{ dl.axis.max_score }}</td></tr>
            </table>
            <h3>직무·산업에서 이 축을 고른 이유</h3>
            <ol class="rank">
              <li v-for="(r, i) in dl.axis_ranking" :key="r.axis" :class="{ top: i === 0 }">
                <b>{{ r.name }}</b> <small class="muted">직무 {{ r.job_w }}×1.5 + 산업 {{ r.industry_w }} = {{ r.total }}</small>
                <div v-if="i === 0" class="small muted">{{ r.why }}</div>
              </li>
            </ol>
          </div>
        </div>
      </section>

      <!-- 1.6 counterpart condition + external detector (PR3) -->
      <section v-if="cond || det" class="card ext">
        <h2>상대 페르소나 조건 · 외부 디텍터 <small class="muted">detector-mcp (규칙 + Gemini), 관찰기와 독립</small></h2>
        <p v-if="cap('tki')" class="cap muted small">{{ cap('tki') }}</p>
        <div class="ext-grid">
          <div>
            <svg viewBox="0 0 240 250" class="tki" role="img" aria-label="주장성과 협력성 평면">
              <rect x="20" y="20" width="200" height="200" rx="8" class="plane" />
              <line x1="120" y1="20" x2="120" y2="220" class="mid" /><line x1="20" y1="120" x2="220" y2="120" class="mid" />
              <text x="26" y="34" class="q">경쟁형</text><text x="214" y="34" class="q" text-anchor="end">협력형</text>
              <text x="26" y="214" class="q">회피형</text><text x="214" y="214" class="q" text-anchor="end">수용형</text>
              <text x="120" y="138" class="q" text-anchor="middle">타협형</text>
              <text x="120" y="240" class="ax" text-anchor="middle">협력성 →</text>
              <text x="8" y="120" class="ax" text-anchor="middle" transform="rotate(-90 8 120)">주장성 →</text>
              <template v-if="cond">
                <template v-for="(who, k) in { lead: '팀장', peer: '동료' }" :key="k">
                  <g v-if="MODE_POS[cond[k]]">
                    <rect :x="px(MODE_POS[cond[k]][0]) - 6" :y="py(MODE_POS[cond[k]][1]) - 6" width="12" height="12" :class="['pm', k]" :transform="`rotate(45 ${px(MODE_POS[cond[k]][0])} ${py(MODE_POS[cond[k]][1])})`" />
                    <text :x="px(MODE_POS[cond[k]][0])" :y="py(MODE_POS[cond[k]][1]) + (MODE_POS[cond[k]][1] > 3 ? 20 : -12)" class="pl" text-anchor="middle">{{ who }}</text>
                  </g>
                </template>
              </template>
              <template v-if="det?.status === 'ready'">
                <circle v-for="p in det.points" :key="p.msg_idx" :cx="px(p.c)" :cy="py(p.a)" r="4" class="dot" @click="jumpMsg(p.msg_idx)"><title>메시지 #{{ p.msg_idx }}: 주장 {{ p.a }} · 협력 {{ p.c }} · {{ p.focus }}</title></circle>
                <circle :cx="px(det.cooperativeness)" :cy="py(det.assertiveness)" r="9" class="me" />
                <text :x="px(det.cooperativeness)" :y="py(det.assertiveness) - 13" class="pl me-l" text-anchor="middle">지원자</text>
              </template>
            </svg>
            <small class="muted">◆ 상대 페르소나 유형(배정) · ● 지원자 발화별 판정 · ⬤ 평균. 위치는 참고용 성향 기술이며 점수가 아니에요.</small>
          </div>
          <div>
            <template v-if="cond">
              <h3>배정된 상대 유형</h3>
              <div class="modes">
                <div class="mode lead"><b>팀장 · {{ cond.lead_mode?.label }}</b><small>{{ cond.lead_mode?.summary }}</small></div>
                <div class="mode peer"><b>동료 · {{ cond.peer_mode?.label }}</b><small>{{ cond.peer_mode?.summary }}</small></div>
              </div>
              <small class="muted">무작위 균형 배정(최소화법, 층: {{ cond.stratum }}). 상대 유형에 따라 같은 지원자도 다르게 반응할 수 있으니, 같은 조건끼리 비교하세요.</small>
            </template>
            <template v-if="det?.status === 'ready'">
              <h3>지원자 성향 추정 <span class="chip blue">{{ MODE_LABEL[det.tki_estimate] }}에 가까움</span></h3>
              <p class="small">주장성 <b>{{ det.assertiveness }}</b> · 협력성 <b>{{ det.cooperativeness }}</b> (1–5) · 판정 {{ det.coverage }}
                <span class="muted">({{ Object.entries(det.sources || {}).map(([k, v]) => `${k} ${v}`).join(', ') }})</span></p>
              <p v-if="det.rules_vs_model_mad" class="small muted">규칙 vs 모델 평균 차: 주장 {{ det.rules_vs_model_mad.assertiveness }} · 협력 {{ det.rules_vs_model_mad.cooperativeness }}</p>
              <p v-if="Object.keys(det.flags || {}).length" class="small">신호: <span v-for="(n, f) in det.flags" :key="f" class="chip amber flag">{{ { blame: '비난 표현', hedge_avoid: '회피 표현', vague: '모호한 약속', eval_probe: '평가 기준 질문' }[f] || f }} {{ n }}</span></p>
            </template>
            <p v-else-if="det?.status === 'disabled'" class="muted small">디텍터가 연결되지 않았어요 (DETECTOR_MCP_URL 미설정).</p>
            <p v-else-if="det" class="muted small">디텍터 판정이 아직 없어요.</p>
          </div>
        </div>

        <template v-if="det?.status === 'ready'">
          <h3>관찰기 ↔ 디텍터 일치도 <small class="muted">발화×역량 {{ det.agreement.n_judgements }}건, Cohen's κ</small></h3>
          <p v-if="cap('agreement')" class="cap muted small">{{ cap('agreement') }}</p>
          <table class="agree">
            <thead><tr><th>역량</th><th>κ</th><th>해석</th><th>일치율</th><th>관찰기 예</th><th>디텍터 예</th></tr></thead>
            <tbody>
              <tr v-for="c in comps" :key="c.id">
                <td><span class="cid" :style="{ background: cc(c.id).bg, color: cc(c.id).fg }">{{ c.id }}</span> {{ c.name }}</td>
                <td><b>{{ agreeOf(c.id).kappa ?? '–' }}</b></td>
                <td class="muted">{{ kappaWord(agreeOf(c.id).kappa) }}</td>
                <td>{{ agreeOf(c.id).agree != null ? pct(agreeOf(c.id).agree) : '–' }}</td>
                <td>{{ agreeOf(c.id).observer_yes ?? '–' }}</td>
                <td>{{ agreeOf(c.id).detector_yes ?? '–' }}</td>
              </tr>
              <tr class="tot"><td>전체</td><td><b>{{ det.agreement.pooled_kappa ?? '–' }}</b></td><td class="muted">{{ kappaWord(det.agreement.pooled_kappa) }}</td><td>{{ det.agreement.pooled_agree != null ? pct(det.agreement.pooled_agree) : '–' }}</td><td /><td /></tr>
            </tbody>
          </table>
          <details v-if="det.disagreements?.length" class="small dis">
            <summary>판정이 엇갈린 {{ det.disagreements.length }}건 — 사람이 확인해 주세요</summary>
            <ul>
              <li v-for="x in det.disagreements" :key="`${x.msg_idx}-${x.competency}`" tabindex="0" @click="jumpMsg(x.msg_idx)" @keydown.enter="jumpMsg(x.msg_idx)">
                #{{ x.msg_idx }} <b>{{ x.competency }}</b>: 관찰기 {{ x.observer ? '있음' : '없음' }} / 디텍터 {{ x.detector ? '있음' : '없음' }} →
              </li>
            </ul>
          </details>
        </template>
      </section>

      <!-- 2. competency x milestone heatmap -->
      <section v-if="an" class="card">
        <h2>역량 × 단계 관찰 지도 <small class="muted">셀을 누르면 근거가 필터돼요</small></h2>
        <p v-if="cap('heatmap')" class="cap muted small">{{ cap('heatmap') }}</p>
        <table class="heat">
          <thead>
            <tr><th /><th v-for="m in hm.milestones" :key="m.key">{{ m.label || MS_LABEL[m.key] }}</th><th>합계</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in hm.competencies" :key="c.id">
              <th class="rowh" :class="{ on: filter.cid === c.id && !filter.mkey }" scope="row">
                <button type="button" class="rowb" :aria-pressed="filter.cid === c.id && !filter.mkey" @click="toggleComp(c.id)">
                  <span class="cid" :style="{ background: cc(c.id).bg, color: cc(c.id).fg }">{{ c.id }}</span> {{ c.name }}
                </button>
              </th>
              <td v-for="m in hm.milestones" :key="m.key">
                <button
                  class="cellb"
                  :class="{ on: filter.cid === c.id && filter.mkey === m.key }"
                  :style="heat(cellOf(c.id, m.key))"
                  :aria-pressed="filter.cid === c.id && filter.mkey === m.key"
                  :aria-label="`${c.id} ${c.name} · ${m.label || MS_LABEL[m.key]}: 근거 ${cellOf(c.id, m.key).n}건`"
                  @click="toggle(c.id, m.key)"
                >
                  <template v-if="cellOf(c.id, m.key).n">
                    <b>{{ cellOf(c.id, m.key).n }}</b>
                    <i class="sig">
                      <u v-for="s in ['positive', 'neutral', 'risk']" :key="s" v-show="cellOf(c.id, m.key)[s]" :style="{ background: SIGNAL[s].color, flex: cellOf(c.id, m.key)[s] }" />
                    </i>
                  </template>
                  <span v-else class="muted">–</span>
                </button>
              </td>
              <td class="tot">{{ rowTotal(c.id) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="legend small muted">
          <span v-for="(s, k) in SIGNAL" :key="k"><i :style="{ background: s.color }" />{{ s.label }}</span>
          <span>※ 관찰 신호이며 점수·합격 판정이 아니에요</span>
        </div>
      </section>

      <!-- 3. competency summaries (the report) -->
      <section class="card">
        <h2>역량별 요약</h2>
        <p v-if="!comps.length" class="muted small">역량 목록은 분석 스냅숏이 준비되면 보여요.</p>
        <div class="sum">
          <div v-for="c in comps" :key="c.id" class="sc" :style="{ borderTopColor: cc(c.id).fg }">
            <div class="sc-h"><span class="cid" :style="{ background: cc(c.id).bg, color: cc(c.id).fg }">{{ c.id }}</span><b>{{ c.name }}</b></div>
            <div v-if="reportComp(c.id)" class="md sum-t" :class="{ muted: reportComp(c.id).empty }" v-html="renderMarkdown(reportComp(c.id).summary)" />
            <p v-else class="muted">{{ d.status === 'completed' ? '리포트를 생성하는 중이에요.' : '세션이 끝나면 요약이 만들어져요.' }}</p>
          </div>
        </div>
        <template v-if="d.report?.figures || reportCharts.length">
          <h3 class="sub-h">리포트 수치·차트 <small class="muted">리포트를 승인한 시점 기준이에요</small></h3>
          <FigureChips v-if="d.report.figures" :figures="d.report.figures" compact class="rep-figs" />
          <ChartGallery v-if="reportCharts.length" :charts="reportCharts" />
        </template>
        <p v-else-if="d.report?.competencies?.length" class="muted small rep-none">이 리포트에는 분석 수치와 차트가 없어요(분석 도구 도입 전이거나 그때 분석을 못 했어요). ‘리포트 다시 생성’으로 다시 만들면 함께 실려요.</p>
      </section>

      <!-- 4. evidence -->
      <section class="card">
        <h2>
          관찰 근거 <small class="muted">{{ shown.length }}건</small>
          <button v-if="hasFilter" class="btn sm" @click="filter = { cid: null, mkey: null }">필터 해제 ✕</button>
        </h2>
        <p v-if="!shown.length" class="muted">조건에 맞는 근거가 없어요. 관련 행동이 기록되지 않았다는 뜻이며 평가가 아닙니다.</p>
        <article v-for="o in shown" :key="o.id" class="ev" tabindex="0" @click="jump(o)" @keydown.enter="jump(o)">
          <div class="ev-h">
            <span class="cid" :style="{ background: cc(o.competency).bg, color: cc(o.competency).fg }">{{ o.competency }}</span>
            <span class="chip gray">{{ MS_LABEL[o.milestone] }}</span>
            <span class="sg" :style="{ color: SIGNAL[o.signal]?.color }">● {{ SIGNAL[o.signal]?.label || o.signal }}</span>
          </div>
          <div class="beh">{{ o.behavior }}</div>
          <blockquote>“{{ o.quote }}”</blockquote>
          <small class="muted">클릭하면 오른쪽 대화의 해당 위치로 이동 →</small>
        </article>
      </section>

      <!-- 4.5 dialogue ledger (item 6) -->
      <section class="card ledger">
        <h2>대화 장부 <small class="muted">에이전트가 턴마다 정리한 쟁점·약속·입장 · 읽기 전용</small></h2>
        <p v-if="!ledger" class="muted small">기록된 장부가 없어요. 이전 방식으로 진행된 세션이거나(DIALOGUE_HARNESS=0) 아직 대화가 짧아요.</p>
        <template v-else>
          <div v-if="ledger.summary" class="md lsum" v-html="renderMarkdown(ledger.summary)" />
          <div class="two">
            <div>
              <h3>쟁점 <small class="muted">{{ (ledger.issues || []).length }}개</small></h3>
              <ul v-if="ledger.issues?.length" class="lst">
                <li v-for="i in ledger.issues" :key="i.id">
                  <span class="chip" :class="ISSUE[i.status]?.[0] || 'gray'">{{ ISSUE[i.status]?.[1] || i.status }}</span>
                  <b>{{ i.title }}</b>
                  <small class="muted">{{ WHO(i.raised_by) }} 제기<template v-if="i.last_idx != null"> · <a href="#" @click.prevent="jumpMsg(i.last_idx)">#{{ i.last_idx }}</a></template></small>
                </li>
              </ul>
              <p v-else class="muted small">정리된 쟁점이 없어요.</p>
            </div>
            <div>
              <h3>약속 <small class="muted">{{ (ledger.commitments || []).length }}개</small></h3>
              <ul v-if="ledger.commitments?.length" class="lst">
                <li v-for="(c, k) in ledger.commitments" :key="k">
                  <b>{{ WHO(c.who) }}</b> {{ c.what }}
                  <small class="muted"><template v-if="c.due">· {{ c.due }} </template><template v-if="c.idx != null">· <a href="#" @click.prevent="jumpMsg(c.idx)">#{{ c.idx }}</a></template></small>
                </li>
              </ul>
              <p v-else class="muted small">기록된 약속이 없어요.</p>
            </div>
          </div>
          <template v-if="positions.length">
            <h3>입장</h3>
            <div class="pos">
              <div v-for="[w, p] in positions" :key="w" class="pc" :class="w">
                <b>{{ WHO(w) }}</b>
                <p v-if="p.claim">{{ p.claim }}</p>
                <small v-if="p.conceded" class="muted">양보한 점 · {{ p.conceded }}</small>
              </div>
            </div>
          </template>
        </template>
      </section>

      <!-- 5. notes + pain points -->
      <section class="two">
        <div class="card">
          <h2>지원자 노트</h2>
          <pre v-if="d.notes" class="notes">{{ d.notes }}</pre>
          <p v-else class="muted">작성한 노트가 없어요.</p>
        </div>
        <div class="card">
          <h2>시나리오 근거 · 현업 painpoint</h2>
          <p v-if="!an" class="muted small">분석 스냅숏이 준비되면 보여요.</p>
          <p v-else-if="!an.context?.painpoints" class="muted small">직무·산업 맞춤 시나리오는 위 '가치 딜레마'의 데이터 근거로 선정돼요.</p>
          <template v-else>
            <p class="small">{{ an.context.painpoints.summary }}</p>
            <ul class="src">
              <li v-for="p in an.context.painpoints.points" :key="p.source_url + p.title">
                <b>{{ p.title }}</b> <span class="chip gray">{{ SRC[p.source_type] }}</span>
                <div class="small muted">{{ p.finding }}</div>
                <a :href="p.source_url" target="_blank" rel="noopener" class="small">{{ p.source_title }} ↗</a>
              </li>
            </ul>
          </template>
        </div>
      </section>
    </section>

    <aside class="trans card">
      <h3>대화 원문 <small class="muted">{{ d.messages.length }}개</small></h3>
      <div class="tscroll">
        <template v-for="(m, i) in d.messages" :key="m.idx">
          <div v-if="i === 0 || d.messages[i - 1].milestone !== m.milestone" class="div">
            <span>{{ MS_LABEL[m.milestone] }} 단계</span>
          </div>
          <div :id="`m-${m.idx}`">
            <ChatBubble :message="m" :who="whoOf(m.speaker)" :mine="m.speaker === 'user'" :highlight="hl === m.idx" :tag="m.choice ? (dl?.options.find((o) => o.id === m.choice)?.label || '') : ''" :badges="[...new Set((obsByMsg[m.idx] || []).map((o) => o.competency))]" />
          </div>
        </template>
      </div>
    </aside>

    <ArtifactViewer :artifact="openArt" :personas="personas" :checks="checks" :focus-line="viewer.line" @close="viewer = { id: null, line: null }" />
  </main>
  <p v-else class="page muted">{{ error || '불러오는 중…' }}</p>
</template>

<style scoped>
.wrap { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 16px; padding: 20px; max-width: 1480px; margin: 0 auto; align-items: start; }
.main { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.head h1 { margin: 2px 0 0; font-size: 22px; }
.head h1 small { font-size: 14px; font-weight: 500; }
.hr { display: flex; gap: 8px; align-items: center; }
.err { align-self: flex-start; white-space: normal; }
h2 { font-size: 16px; display: flex; gap: 10px; align-items: center; }
h2 small { font-weight: 500; font-size: 12px; }
.cap { margin: -6px 0 10px; }

.snap { display: flex; flex-direction: column; gap: 10px; }
.snap h2 { margin: 0; }
.snap-h { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.note { margin: 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: var(--muted); }
.note.bad, .bad { color: #b91c1c; }
.live { width: 8px; height: 8px; border-radius: 50%; background: var(--brand); animation: blink 1.4s ease-in-out infinite; }
.wait-b { display: grid; grid-template-columns: minmax(0, 1fr) minmax(200px, 280px); gap: 20px; align-items: start; padding: 4px 0; }
.wait-t p { margin: 4px 0 10px; }
.wait-s { padding-top: 2px; }

.tl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.seg { text-align: left; border: 1.5px dashed var(--line); background: var(--panel); border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 8px; color: var(--ink); }
.seg.reached { border-style: solid; border-color: var(--brand-soft); background: color-mix(in srgb, var(--brand-soft) 45%, var(--panel)); }
.seg.on { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
.seg:focus-visible, .cellb:focus-visible, .rowb:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.seg-top { display: flex; justify-content: space-between; align-items: baseline; }
.seg-dots { display: flex; gap: 5px; flex-wrap: wrap; min-height: 14px; align-items: center; }
.d { width: 12px; height: 12px; border-radius: 50%; }

.heat { width: 100%; border-collapse: separate; border-spacing: 5px; }
.heat th { font-size: 12px; color: var(--muted); font-weight: 600; text-align: center; }
.heat .rowh { text-align: left; color: var(--ink); font-size: 13px; padding: 4px 6px; border-radius: 8px; width: 28%; }
.heat .rowh.on { background: var(--brand-soft); }
.rowb { border: 0; background: none; color: inherit; font: inherit; text-align: left; padding: 0; width: 100%; border-radius: 6px; }
.cellb { width: 100%; height: 52px; border: 1.5px solid var(--line); border-radius: 10px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 4px; background: transparent; color: var(--ink); }
.cellb.on { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
.sig { display: flex; width: 70%; height: 5px; border-radius: 3px; overflow: hidden; }
.sig u { display: block; }
.tot { text-align: center; font-weight: 700; width: 48px; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; align-items: center; }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; }
.cid { display: inline-block; font-size: 11px; font-weight: 800; padding: 1px 7px; border-radius: 6px; }

.sum { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.sc { border: 1px solid var(--line); border-top: 3px solid; border-radius: 10px; padding: 12px 14px; }
.sc-h { display: flex; gap: 8px; align-items: center; }
.sc p { margin: 8px 0 0; font-size: 14px; }
.sum-t { margin-top: 8px; font-size: 14px; }
.sub-h { font-size: 14px; margin: 18px 0 6px; display: flex; gap: 8px; align-items: center; }
.sub-h small { font-weight: 500; font-size: 12px; }
.rep-figs { margin-bottom: 10px; }
.rep-none { margin: 14px 0 0; }
.chk-note { margin: 0 0 8px; line-height: 1.55; }
.chk td { vertical-align: top; }
.clk { cursor: pointer; }
.clk:hover td, .clk:focus-visible td { background: var(--bg); }
.clk:focus-visible { outline: 2px solid var(--brand); outline-offset: -2px; }
.ledger h3 { font-size: 14px; margin: 14px 0 8px; }
.lsum { font-size: 14px; padding: 10px 12px; border-radius: 10px; background: var(--bg); }
.lst { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 13.5px; }
.lst li { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
.pos { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.pc { border: 1px solid var(--line); border-left: 4px solid var(--brand); border-radius: 10px; padding: 8px 12px; font-size: 13.5px; }
.pc.lead { border-left-color: #0f766e; }
.pc.peer { border-left-color: #b45309; }
.pc p { margin: 4px 0; }

.ev { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin-top: 10px; cursor: pointer; transition: 0.15s; }
.ev:hover, .ev:focus-visible { border-color: var(--brand); background: var(--bg); outline: none; }
.ev-h { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.sg { font-size: 12px; font-weight: 700; margin-left: auto; }
.beh { font-weight: 600; }
blockquote { margin: 6px 0; padding: 6px 12px; border-left: 3px solid var(--line); color: var(--muted); }

.two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.approve { border-color: var(--warn); }
.ap-figs { margin: 4px 0 2px; }
.ap-charts { margin: 0 0 12px; }
.drafts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
.draft { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
.draft p { margin: 6px 0 0; font-size: 13.5px; }
.decide { display: flex; gap: 8px; flex-wrap: wrap; }
.decide .text { flex: 1; min-width: 160px; }
.dl .q { margin: -4px 0 12px; }
.dl h3 { font-size: 14px; margin: 14px 0 8px; }
.dist { margin-bottom: 6px; }
.dist-lbl { display: flex; justify-content: space-between; gap: 16px; font-size: 13px; margin-bottom: 6px; }
.dist-lbl .r { text-align: right; }
.bar3 { position: relative; display: flex; height: 30px; border-radius: 8px; overflow: visible; margin: 22px 0 6px; font-size: 12px; font-weight: 700; color: #fff; }
.bar3 i { display: grid; place-items: center; font-style: normal; }
.bar3 .pa { background: #2563eb; border-radius: 8px 0 0 8px; }
.bar3 .pt { background: #94a3b8; }
.bar3 .pb { background: #ea580c; border-radius: 0 8px 8px 0; }
.mk { position: absolute; top: -20px; transform: translateX(-50%); color: var(--ink); font-size: 12px; white-space: nowrap; }
.pick blockquote { cursor: pointer; }
.pick blockquote:hover, .pick blockquote:focus-visible { border-left-color: var(--brand); outline: none; }
.opt-l { font-weight: 600; margin: 8px 0 4px; }
.kv { width: 100%; border-collapse: collapse; font-size: 13px; }
.kv th { text-align: left; color: var(--muted); font-weight: 600; padding: 4px 8px 4px 0; width: 42%; }
.kv td { padding: 4px 0; }
.rank { padding-left: 18px; margin: 0; font-size: 13px; }
.rank li { margin: 4px 0; color: var(--muted); }
.rank li.top { color: var(--ink); }
.ext h3 { font-size: 14px; margin: 14px 0 8px; }
.ext-grid { display: grid; grid-template-columns: 300px 1fr; gap: 20px; align-items: start; }
.tki { width: 100%; max-width: 300px; }
.tki .plane { fill: var(--bg); stroke: var(--line); }
.tki .mid { stroke: var(--line); stroke-dasharray: 3 3; }
.tki .q { font-size: 10px; fill: var(--muted); font-weight: 700; }
.tki .ax { font-size: 10px; fill: var(--muted); }
.tki .pm.lead { fill: #0f766e; }
.tki .pm.peer { fill: #b45309; }
.tki .pl { font-size: 10px; font-weight: 700; fill: var(--ink); }
.tki .dot { fill: #94a3b8; opacity: 0.75; cursor: pointer; }
.tki .me { fill: var(--brand); stroke: #fff; stroke-width: 2; }
.tki .me-l { fill: var(--brand); }
.modes { display: flex; gap: 10px; margin-bottom: 6px; }
.mode { flex: 1; border: 1px solid var(--line); border-left: 4px solid; border-radius: 10px; padding: 8px 12px; display: flex; flex-direction: column; }
.mode.lead { border-left-color: #0f766e; }
.mode.peer { border-left-color: #b45309; }
.mode small { color: var(--muted); }
.flag { margin-right: 4px; }
.agree { width: 100%; border-collapse: collapse; font-size: 13px; }
.agree th { text-align: left; color: var(--muted); font-weight: 600; padding: 6px 8px; border-bottom: 1px solid var(--line); }
.agree td { padding: 6px 8px; border-bottom: 1px solid var(--line); }
.agree .tot td { border-bottom: 0; font-weight: 600; }
.dis ul { margin: 6px 0 0; padding-left: 18px; }
.dis li { cursor: pointer; margin: 3px 0; }
.dis li:hover, .dis li:focus-visible { color: var(--brand); outline: none; }
.notes { white-space: pre-wrap; margin: 0; font-family: inherit; }
.src { list-style: none; padding: 0; margin: 10px 0 0; display: flex; flex-direction: column; gap: 12px; }

.trans { position: sticky; top: 73px; max-height: calc(100vh - 93px); display: flex; flex-direction: column; padding: 14px; }
.trans h3 { margin: 0 0 6px; }
.tscroll { overflow-y: auto; padding-right: 4px; }
.div { text-align: center; margin: 14px 0 4px; position: relative; }
.div::before { content: ''; position: absolute; left: 0; right: 0; top: 50%; border-top: 1px dashed var(--line); }
.div span { position: relative; background: var(--panel); padding: 0 10px; font-size: 12px; font-weight: 700; color: var(--brand); }
@keyframes blink { 50% { opacity: 0.35; } }
@media (prefers-reduced-motion: reduce) { .live { animation: none; } .ev { transition: none; } }
@media (max-width: 1100px) { .ext-grid, .wait-b { grid-template-columns: 1fr; } .wrap { grid-template-columns: 1fr; } .trans { position: static; max-height: 70vh; } .two, .sum, .tl, .pos { grid-template-columns: 1fr; } }
</style>
