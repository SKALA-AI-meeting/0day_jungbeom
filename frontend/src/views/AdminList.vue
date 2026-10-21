<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, auth } from '../api'
import { MS_LABEL } from '../constants'

const router = useRouter()
const rows = ref([])
const tasks = ref([])
const invites = ref([])
const me = ref(null)
const error = ref('')
const inv = ref({ alias: '', email: '' })
const created = ref(null)
let timer

async function load() {
  try {
    ;[rows.value, tasks.value, invites.value] = await Promise.all([api.adminList(), api.myTasks(auth.admin()), api.adminInvites()])
    error.value = ''
  } catch (e) {
    if (e.status === 401 || e.status === 403) {
      auth.clearAdmin()
      router.replace('/admin/login')
    } else error.value = e.message || '목록을 불러오지 못했어요.'
  }
}
onMounted(async () => {
  if (!auth.admin()) return router.replace('/admin/login')
  me.value = await api.me().catch(() => null)
  await load()
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
function logout() {
  auth.clearAdmin()
  router.replace('/admin/login')
}

const MS = ['communicate', 'coordinate', 'compromise', 'persuade']
const STATUS = { active: ['blue', '진행 중'], completed: ['green', '완료'] }
const REPORT = { ready: ['green', '리포트 준비됨'], awaiting_approval: ['amber', '승인 대기'], pending: ['blue', '생성 중'], failed: ['red', '실패'], rejected: ['gray', '반려됨'], none: ['gray', '대기'] }
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
    <div class="top"><h1>지원자 목록</h1><span v-if="me" class="muted small">{{ me.company }} · <button class="btn sm" @click="logout">로그아웃</button></span></div>
    <p class="sub">세션별 진행 단계와 관찰 근거를 한눈에 확인합니다. 점수나 합격 표시는 없습니다.</p>
    <p v-if="error" class="chip red">{{ error }}</p>

    <section class="card">
      <p v-if="!rows.length" class="muted">아직 세션이 없어요. 지원자 화면에서 대화를 시작해 보세요.</p>
      <table v-else>
        <thead><tr><th>별칭</th><th>시나리오</th><th>가치 축 · 선택</th><th>진행</th><th>상태</th><th>메시지</th><th>근거</th><th>리포트</th><th>시작</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" @click="$router.push(`/admin/${r.id}`)">
            <td><b>{{ r.alias }}</b></td>
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
            <td><span class="chip" :class="REPORT[r.report_status][0]">{{ REPORT[r.report_status][1] }}</span></td>
            <td class="muted small">{{ fmt(r.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="two">
      <div class="card">
        <h3>지원자 초대</h3>
        <p class="muted small">1회용 링크를 만들어요. 72시간 뒤 만료돼요.</p>
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
        <h3>내 AI 작업 이력</h3>
        <p class="muted small">리포트 생성·승인처럼 내가 요청한 작업이에요. (GET /api/ai/tasks?mine=true)</p>
        <p v-if="!tasks.length" class="muted">아직 요청한 작업이 없어요.</p>
        <table v-else class="tasks">
          <tbody>
            <tr v-for="t in tasks.slice(0, 8)" :key="t.id" @click="t.sessionId && $router.push(`/admin/${t.sessionId}`)">
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
.top { display: flex; justify-content: space-between; align-items: baseline; }
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
tbody tr:hover { background: var(--bg); }
.bar { display: flex; gap: 3px; width: 88px; }
.bar i { flex: 1; height: 6px; border-radius: 3px; background: var(--line); }
.bar i.on { background: var(--brand); }
</style>
