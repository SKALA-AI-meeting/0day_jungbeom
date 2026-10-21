<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../../api'
import { MS_LABEL } from '../../constants'

const me = ref(null)
const meta = ref(null)
const sessions = ref([])
const error = ref('')

onMounted(async () => {
  try {
    ;[me.value, meta.value, sessions.value] = await Promise.all([api.me(), api.meta(), api.mySessions()])
  } catch (e) {
    error.value = e.message
  }
})

const STATUS = {
  ACTIVE: ['green', '확인 완료'],
  PENDING_REVIEW: ['blue', '계정 확인 중'],
  REVIEW_ERROR: ['amber', '담당자 확인 중'],
  REJECTED: ['red', '참여 불가'],
}
const label = (list, id) => meta.value?.dilemma[list].find((x) => x.id === id)?.label || id || '–'
const scenarioName = (id) => {
  const [kind, job, ind] = id.split('.')
  if (kind === 'dl') return `${label('jobs', job)} · ${label('industries', ind)}`
  return meta.value?.scenarios.find((s) => s.id === id)?.category || id
}
const MS = ['communicate', 'coordinate', 'compromise', 'persuade']
const active = computed(() => me.value?.status === 'ACTIVE')
const fmt = (t) => new Date(t).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <main class="page">
    <h1>내 평가</h1>
    <p class="sub">계정 상태와 진행한 대화를 볼 수 있어요.</p>
    <p v-if="error" class="chip red">{{ error }}</p>

    <section v-if="me" class="card acct">
      <span class="av">{{ me.nickname.slice(0, 1) }}</span>
      <div class="id">
        <b>{{ me.nickname }}</b>
        <small class="muted">{{ me.email }} · {{ me.company }}</small>
        <small class="muted">{{ label('jobs', me.desiredJob) }}<template v-if="me.industry"> · {{ label('industries', me.industry) }}</template> · 경력 {{ me.experienceYears }}년</small>
      </div>
      <span class="chip" :class="STATUS[me.status][0]">{{ STATUS[me.status][1] }}</span>
      <RouterLink v-if="me.status === 'PENDING_REVIEW'" to="/me/review" class="btn sm">진행 상황 보기</RouterLink>
      <RouterLink v-else-if="active" to="/me/start" class="btn primary">새 평가 시작</RouterLink>
    </section>
    <p v-if="me?.status === 'REJECTED'" class="note red">{{ me.rejectReason }}</p>
    <p v-else-if="me?.status === 'REVIEW_ERROR'" class="note amber">자동 확인을 끝내지 못해 담당자가 직접 확인하고 있어요.</p>

    <section class="card list">
      <h3>진행한 대화</h3>
      <p v-if="!sessions.length" class="muted">{{ active ? '아직 시작한 평가가 없어요.' : '계정 확인이 끝나면 평가를 시작할 수 있어요.' }}</p>
      <TransitionGroup v-else tag="ul" name="row" class="rows">
        <li v-for="s in sessions" :key="s.id">
          <RouterLink :to="`/s/${s.id}`" class="row">
            <b>{{ scenarioName(s.scenarioId) }}</b>
            <span class="bar"><i v-for="(k, i) in MS" :key="k" :class="{ on: i <= s.milestoneIdx || s.status === 'completed' }" /></span>
            <small class="muted">{{ s.status === 'completed' ? '종료' : MS_LABEL[MS[s.milestoneIdx]] + ' 단계' }}</small>
            <span class="chip" :class="s.status === 'completed' ? 'green' : 'blue'">{{ s.status === 'completed' ? '완료' : '진행 중' }}</span>
            <small class="muted">{{ fmt(s.createdAt) }}</small>
          </RouterLink>
        </li>
      </TransitionGroup>
    </section>
  </main>
</template>

<style scoped>
.acct { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.av { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 50%; background: var(--brand); color: #fff; font-weight: 800; font-size: 18px; }
.id { display: flex; flex-direction: column; flex: 1; min-width: 200px; line-height: 1.4; }
.note { margin: 10px 0 0; padding: 10px 14px; border-radius: 10px; font-size: 13px; }
.note.red { background: #fee2e2; color: #991b1b; }
.note.amber { background: #fef3c7; color: #92400e; }
.list { margin-top: 16px; }
.rows { list-style: none; margin: 0; padding: 0; }
.row { display: grid; grid-template-columns: minmax(0, 1fr) 96px 80px 64px 110px; gap: 12px; align-items: center; padding: 12px 8px; border-bottom: 1px solid var(--line); color: var(--ink); border-radius: 8px; transition: background 0.15s; }
.row:hover { background: var(--bg); text-decoration: none; }
.bar { display: flex; gap: 3px; }
.bar i { flex: 1; height: 6px; border-radius: 3px; background: var(--line); transition: background 0.3s; }
.bar i.on { background: var(--brand); }
.row-enter-active { transition: opacity 0.3s, transform 0.3s; }
.row-enter-from { opacity: 0; transform: translateY(4px); }
@media (max-width: 700px) { .row { grid-template-columns: 1fr auto; } .row .bar, .row small:last-child { display: none; } }
</style>
