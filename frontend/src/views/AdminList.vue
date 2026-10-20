<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import { MS_LABEL } from '../constants'

const rows = ref([])
const needToken = ref(false)
const token = ref(localStorage.getItem('dz_admin_token') || '')
const error = ref('')
let timer

async function load() {
  try {
    rows.value = await api.adminList()
    needToken.value = false
    error.value = ''
  } catch (e) {
    if (e.status === 401) needToken.value = true
    else error.value = '목록을 불러오지 못했어요.'
  }
}
function saveToken() {
  localStorage.setItem('dz_admin_token', token.value)
  load()
}
onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})
onBeforeUnmount(() => clearInterval(timer))

const MS = ['communicate', 'coordinate', 'compromise', 'persuade']
const STATUS = { active: ['blue', '진행 중'], completed: ['green', '완료'] }
const REPORT = { ready: ['green', '리포트 준비됨'], failed: ['red', '실패'], none: ['gray', '대기'] }
const fmt = (t) => new Date(t * 1000).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <main class="page">
    <h1>지원자 목록</h1>
    <p class="sub">세션별 진행 단계와 관찰 근거를 한눈에 확인합니다. 점수나 합격 표시는 없습니다.</p>

    <section v-if="needToken" class="card tok">
      <b>관리자 토큰이 필요해요</b>
      <input class="text" type="password" v-model="token" placeholder="ADMIN_TOKEN" @keyup.enter="saveToken" />
      <button class="btn primary" @click="saveToken">확인</button>
    </section>
    <p v-if="error" class="chip red">{{ error }}</p>

    <section v-if="!needToken" class="card">
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
  </main>
</template>

<style scoped>
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
