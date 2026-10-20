<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { api } from '../api'
import ChatBubble from '../components/ChatBubble.vue'
import { COMP_COLOR, MS_LABEL, SIGNAL } from '../constants'

const props = defineProps({ id: String })
const d = ref(null)
const meta = ref(null)
const error = ref('')
const filter = ref({ cid: null, mkey: null })
const hl = ref(null)
const regen = ref(false)

async function load() {
  try {
    const [doc, m] = await Promise.all([api.adminGet(props.id), api.meta()])
    d.value = doc
    meta.value = m
  } catch (e) {
    error.value = e.status === 401 ? '관리자 토큰이 필요해요. 목록 화면에서 입력해 주세요.' : '불러오지 못했어요.'
  }
}
onMounted(load)

const comps = computed(() => meta.value?.competencies || [])
const mss = computed(() => meta.value?.milestones || [])
const personas = computed(() => d.value?.scenario.personas || {})
const whoOf = (sp) => (sp === 'user' ? { name: d.value.alias } : personas.value[sp])

const obsByMsg = computed(() => {
  const m = {}
  for (const o of d.value?.observations || []) (m[o.msg_idx] ||= []).push(o)
  return m
})
const cell = (cid, mk) => {
  const os = (d.value?.observations || []).filter((o) => o.competency === cid && o.milestone === mk)
  return { n: os.length, positive: os.filter((o) => o.signal === 'positive').length, neutral: os.filter((o) => o.signal === 'neutral').length, risk: os.filter((o) => o.signal === 'risk').length }
}
const shown = computed(() =>
  (d.value?.observations || []).filter(
    (o) => (!filter.value.cid || o.competency === filter.value.cid) && (!filter.value.mkey || o.milestone === filter.value.mkey),
  ),
)
const msCount = (mk) => d.value.messages.filter((m) => m.milestone === mk).length
const msObs = (mk) => d.value.observations.filter((o) => o.milestone === mk)
const entered = (mk) => {
  const e = d.value.milestone_log.find((x) => x.key === mk)
  if (!e) return null
  const s = Math.max(0, Math.round(e.ts - d.value.created_at))
  return `+${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
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
  document.getElementById(`m-${o.msg_idx}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  setTimeout(() => (hl.value = null), 2500)
}
async function regenerate() {
  regen.value = true
  try {
    d.value = await api.adminRegenerate(props.id)
  } finally {
    regen.value = false
  }
}
const heat = (c) => {
  if (!c.n) return {}
  const a = Math.min(0.15 + c.n * 0.17, 0.85)
  return { background: `color-mix(in srgb, var(--brand) ${Math.round(a * 100)}%, transparent)` }
}
const SRC = { survey: '설문', article: '기사', paper: '논문', report: '보고서' }
const pct = (x) => `${Math.round(x * 100)}%`
const FACET_ROLE = { lead: '팀장이', peer: '동료가' }
const dl = computed(() => d.value?.dilemma)
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
function jumpMsg(idx) {
  jump({ msg_idx: idx })
}
</script>

<template>
  <main v-if="d && meta" class="wrap">
    <section class="main">
      <header class="head">
        <div>
          <RouterLink to="/admin" class="small">← 목록</RouterLink>
          <h1>{{ d.alias }} <small class="muted">· {{ d.scenario.category }} — {{ d.scenario.title }}</small></h1>
        </div>
        <div class="hr">
          <span class="chip" :class="d.status === 'completed' ? 'green' : 'blue'">{{ d.status === 'completed' ? '완료' : '진행 중' }}</span>
          <span class="chip" :class="d.report?.status === 'ready' ? 'green' : d.report?.status === 'failed' ? 'red' : 'gray'">
            리포트 {{ d.report?.status === 'ready' ? '준비됨' : d.report?.status === 'failed' ? '실패' : '대기' }}
          </span>
          <button v-if="d.status === 'completed'" class="btn sm" :disabled="regen" @click="regenerate">{{ regen ? '생성 중…' : '리포트 다시 생성' }}</button>
          <button class="btn sm" @click="load">새로고침</button>
        </div>
      </header>

      <!-- 1. milestone timeline -->
      <section class="card">
        <h2>논의 마일스톤 타임라인</h2>
        <div class="tl">
          <button v-for="(m, i) in mss" :key="m.key" class="seg" :class="{ reached: i <= d.milestone_idx, on: filter.mkey === m.key && !filter.cid }" @click="toggleMs(m.key)">
            <div class="seg-top"><b>{{ m.label }}</b><small class="muted">{{ entered(m.key) || '미도달' }}</small></div>
            <div class="seg-dots">
              <span v-for="o in msObs(m.key)" :key="o.id" class="d" :style="{ background: COMP_COLOR[o.competency].fg }" :title="`${o.competency} ${o.behavior}`" />
              <small v-if="!msObs(m.key).length" class="muted">근거 없음</small>
            </div>
            <small class="muted">메시지 {{ msCount(m.key) }}개 · 근거 {{ msObs(m.key).length }}건</small>
          </button>
        </div>
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
              <blockquote @click="jumpMsg(dl.choice.msg_idx)">“{{ dl.choice.rationale }}” <small>→ 대화에서 보기</small></blockquote>
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

      <!-- 2. competency x milestone heatmap -->
      <section class="card">
        <h2>역량 × 단계 관찰 지도 <small class="muted">셀을 누르면 근거가 필터돼요</small></h2>
        <table class="heat">
          <thead>
            <tr><th /><th v-for="m in mss" :key="m.key">{{ m.label }}</th><th>합계</th></tr>
          </thead>
          <tbody>
            <tr v-for="c in comps" :key="c.id">
              <th class="rowh" :class="{ on: filter.cid === c.id && !filter.mkey }" @click="toggleComp(c.id)">
                <span class="cid" :style="{ background: COMP_COLOR[c.id].bg, color: COMP_COLOR[c.id].fg }">{{ c.id }}</span> {{ c.name }}
              </th>
              <td v-for="m in mss" :key="m.key">
                <button class="cellb" :class="{ on: filter.cid === c.id && filter.mkey === m.key }" :style="heat(cell(c.id, m.key))" @click="toggle(c.id, m.key)">
                  <template v-if="cell(c.id, m.key).n">
                    <b>{{ cell(c.id, m.key).n }}</b>
                    <i class="sig">
                      <u v-for="s in ['positive', 'neutral', 'risk']" :key="s" v-show="cell(c.id, m.key)[s]" :style="{ background: SIGNAL[s].color, flex: cell(c.id, m.key)[s] }" />
                    </i>
                  </template>
                  <span v-else class="muted">–</span>
                </button>
              </td>
              <td class="tot">{{ reportComp(c.id)?.count ?? d.observations.filter((o) => o.competency === c.id).length }}</td>
            </tr>
          </tbody>
        </table>
        <div class="legend small muted">
          <span v-for="(s, k) in SIGNAL" :key="k"><i :style="{ background: s.color }" />{{ s.label }}</span>
          <span>※ 관찰 신호이며 점수·합격 판정이 아니에요</span>
        </div>
      </section>

      <!-- 3. competency summaries -->
      <section class="card">
        <h2>역량별 요약</h2>
        <div class="sum">
          <div v-for="c in comps" :key="c.id" class="sc" :style="{ borderTopColor: COMP_COLOR[c.id].fg }">
            <div class="sc-h"><span class="cid" :style="{ background: COMP_COLOR[c.id].bg, color: COMP_COLOR[c.id].fg }">{{ c.id }}</span><b>{{ c.name }}</b></div>
            <p v-if="reportComp(c.id)" :class="{ muted: reportComp(c.id).empty }">{{ reportComp(c.id).summary }}</p>
            <p v-else class="muted">{{ d.status === 'completed' ? '리포트를 생성하는 중이에요.' : '세션이 끝나면 요약이 만들어져요.' }}</p>
          </div>
        </div>
      </section>

      <!-- 4. evidence -->
      <section class="card">
        <h2>
          관찰 근거 <small class="muted">{{ shown.length }}건</small>
          <button v-if="hasFilter" class="btn sm" @click="filter = { cid: null, mkey: null }">필터 해제 ✕</button>
        </h2>
        <p v-if="!shown.length" class="muted">조건에 맞는 근거가 없어요. 관련 행동이 기록되지 않았다는 뜻이며 평가가 아닙니다.</p>
        <article v-for="o in shown" :key="o.id" class="ev" @click="jump(o)">
          <div class="ev-h">
            <span class="cid" :style="{ background: COMP_COLOR[o.competency].bg, color: COMP_COLOR[o.competency].fg }">{{ o.competency }}</span>
            <span class="chip gray">{{ MS_LABEL[o.milestone] }}</span>
            <span class="sg" :style="{ color: SIGNAL[o.signal].color }">● {{ SIGNAL[o.signal].label }}</span>
          </div>
          <div class="beh">{{ o.behavior }}</div>
          <blockquote>“{{ o.quote }}”</blockquote>
          <small class="muted">클릭하면 오른쪽 대화의 해당 위치로 이동 →</small>
        </article>
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
          <p v-if="!d.painpoints" class="muted small">직무·산업 맞춤 시나리오는 위 '가치 딜레마'의 데이터 근거로 선정돼요.</p>
          <template v-if="d.painpoints">
            <p class="small">{{ d.painpoints.summary }}</p>
            <ul class="src">
              <li v-for="p in d.painpoints.points" :key="p.source_url + p.title">
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
h2 { font-size: 16px; display: flex; gap: 10px; align-items: center; }
h2 small { font-weight: 500; font-size: 12px; }

.tl { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.seg { text-align: left; border: 1.5px dashed var(--line); background: var(--panel); border-radius: 12px; padding: 12px; display: flex; flex-direction: column; gap: 8px; color: var(--ink); }
.seg.reached { border-style: solid; border-color: var(--brand-soft); background: color-mix(in srgb, var(--brand-soft) 45%, var(--panel)); }
.seg.on { border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
.seg-top { display: flex; justify-content: space-between; align-items: baseline; }
.seg-dots { display: flex; gap: 5px; flex-wrap: wrap; min-height: 14px; align-items: center; }
.d { width: 12px; height: 12px; border-radius: 50%; }

.heat { width: 100%; border-collapse: separate; border-spacing: 5px; }
.heat th { font-size: 12px; color: var(--muted); font-weight: 600; text-align: center; }
.heat .rowh { text-align: left; color: var(--ink); font-size: 13px; cursor: pointer; padding: 4px 6px; border-radius: 8px; width: 28%; }
.heat .rowh.on { background: var(--brand-soft); }
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

.ev { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin-top: 10px; cursor: pointer; transition: 0.15s; }
.ev:hover { border-color: var(--brand); background: var(--bg); }
.ev-h { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.sg { font-size: 12px; font-weight: 700; margin-left: auto; }
.beh { font-weight: 600; }
blockquote { margin: 6px 0; padding: 6px 12px; border-left: 3px solid var(--line); color: var(--muted); }

.two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
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
.pick blockquote:hover { border-left-color: var(--brand); }
.opt-l { font-weight: 600; margin: 8px 0 4px; }
.kv { width: 100%; border-collapse: collapse; font-size: 13px; }
.kv th { text-align: left; color: var(--muted); font-weight: 600; padding: 4px 8px 4px 0; width: 42%; }
.kv td { padding: 4px 0; }
.rank { padding-left: 18px; margin: 0; font-size: 13px; }
.rank li { margin: 4px 0; color: var(--muted); }
.rank li.top { color: var(--ink); }
.notes { white-space: pre-wrap; margin: 0; font-family: inherit; }
.src { list-style: none; padding: 0; margin: 10px 0 0; display: flex; flex-direction: column; gap: 12px; }

.trans { position: sticky; top: 73px; max-height: calc(100vh - 93px); display: flex; flex-direction: column; padding: 14px; }
.trans h3 { margin: 0 0 6px; }
.tscroll { overflow-y: auto; padding-right: 4px; }
.div { text-align: center; margin: 14px 0 4px; position: relative; }
.div::before { content: ''; position: absolute; left: 0; right: 0; top: 50%; border-top: 1px dashed var(--line); }
.div span { position: relative; background: var(--panel); padding: 0 10px; font-size: 12px; font-weight: 700; color: var(--brand); }
@media (max-width: 1100px) { .wrap { grid-template-columns: 1fr; } .trans { position: static; max-height: 70vh; } .two, .sum, .tl { grid-template-columns: 1fr; } }
</style>
