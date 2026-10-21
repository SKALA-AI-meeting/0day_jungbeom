<script setup>
// Pick a situation and enter the team channel. Signed-in ACTIVE accounts only; job/industry start from the profile.
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api } from '../../api'

const route = useRoute()
const router = useRouter()
const me = ref(null)
const meta = ref(null)
const mode = ref('dilemma') // 'dilemma' = 직무·산업 맞춤, 'category' = 상황 카테고리
const picked = ref(null)
const job = ref(null)
const industry = ref(null)
const preview = ref(null)
const agreed = ref(false)
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    ;[meta.value, me.value] = await Promise.all([api.meta(), api.me()])
    job.value = me.value.desiredJob
    industry.value = me.value.industry || null
  } catch (e) {
    error.value = e.message || '서버에 연결하지 못했어요.'
  }
})

watch([job, industry], async ([j, i]) => {
  preview.value = null
  if (j && i) preview.value = await api.preview(`dl.${j}.${i}`).catch(() => null)
})

const scenario = computed(() =>
  mode.value === 'dilemma' ? preview.value : meta.value?.scenarios.find((s) => s.id === picked.value),
)
const fromProfile = computed(() => me.value && job.value === me.value.desiredJob && industry.value === (me.value.industry || null))
const ready = computed(() => scenario.value && agreed.value && !busy.value && me.value?.status === 'ACTIVE')
const ICON = { delay: '⏱️', scope: '🔀', conflict: '⚖️', workload: '🤝' }

async function start() {
  busy.value = true
  error.value = ''
  try {
    const s = await api.startSession(scenario.value.id, route.query.invite)
    router.push({ path: `/s/${s.sessionId}`, query: { task: s.startTaskId } })
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}
</script>

<template>
  <main class="page">
    <h1>팀 채널에 합류해 볼까요?</h1>
    <p class="sub">AI 팀원 두 명과 3자 대화방에서 진행 중인 일을 함께 풀어 갑니다. 정답은 없고, 평소 하던 대로 대화하면 돼요.</p>
    <p v-if="error" class="chip red">{{ error }}</p>
    <p v-if="me && me.status !== 'ACTIVE'" class="chip amber">
      계정 확인이 끝나야 시작할 수 있어요. <RouterLink to="/me/review">진행 상황 보기</RouterLink>
    </p>

    <section class="card step">
      <div class="step-h">
        <b>1</b> 상황 고르기
        <div class="tabs">
          <button :class="{ on: mode === 'dilemma' }" @click="mode = 'dilemma'">직무·산업 맞춤</button>
          <button :class="{ on: mode === 'category' }" @click="mode = 'category'">상황 카테고리</button>
        </div>
      </div>
      <template v-if="mode === 'dilemma'">
        <p class="muted small hint">
          지원하는 직무와 산업을 고르면, 그 일에서 자주 생기는 상황이 주어져요.
          <span v-if="fromProfile" class="chip gray">가입할 때 고른 값으로 맞춰 두었어요</span>
        </p>
        <div class="lbl">직무</div>
        <div class="pills">
          <button v-for="j in meta?.dilemma.jobs" :key="j.id" class="pill" :class="{ on: job === j.id }" @click="job = j.id">{{ j.label }}</button>
        </div>
        <div class="lbl">산업</div>
        <div class="pills">
          <button v-for="i in meta?.dilemma.industries" :key="i.id" class="pill" :class="{ on: industry === i.id }" @click="industry = i.id">
            {{ i.label }} <small>{{ i.service }}</small>
          </button>
        </div>
      </template>
      <div v-else class="cats">
        <button
          v-for="s in meta?.scenarios"
          :key="s.id"
          class="cat"
          :class="{ on: picked === s.id }"
          @click="picked = s.id"
        >
          <span class="ic">{{ ICON[s.id] }}</span>
          <b>{{ s.category }}</b>
          <small>{{ s.tagline }}</small>
        </button>
      </div>
    </section>

    <section v-if="scenario" class="card step">
      <div class="step-h"><b>2</b> 오늘의 상황</div>
      <span v-if="scenario.kind === 'dilemma'" class="chip blue">{{ scenario.category }}</span>
      <h3 class="st">{{ scenario.title }}</h3>
      <p class="bg">{{ scenario.background }}</p>
      <p class="muted small">{{ scenario.brief }}</p>
      <div class="people">
        <div class="person"><span class="av me">나</span><div><b>{{ me?.nickname || '지원자' }}</b><small>같은 팀원 (오늘 합류)</small></div></div>
        <div v-for="p in scenario.personas" :key="p.id" class="person">
          <span class="av">{{ p.emoji }}</span><div><b>{{ p.name }}</b><small>{{ p.role }} · AI</small></div>
        </div>
      </div>
      <p class="muted small flow">
        진행 방식: <b>소통 → 조율 → 타협 → 설득</b> 네 단계로 대화가 이어지고, 왼쪽에서 현재 단계를 볼 수 있어요.
        <template v-if="scenario.kind === 'dilemma'"> 타협 단계에서는 <b>선택지 중 하나를 고르고 이유를 적는</b> 순간이 있어요.</template>
        오른쪽 노트에 생각을 정리해도 좋아요.
      </p>
      <label class="consent">
        <input type="checkbox" v-model="agreed" />
        <span>
          AI 팀원 두 명(AI)과 대화하는 평가이며, 대화와 노트가 기록되어 <b>소통·협업·책임 이행·변화 대응</b> 관찰에 쓰인다는 점,
          AI는 관찰·기록만 하고 <b>최종 판단은 사람이</b> 한다는 점을 확인했습니다. (구체적인 돌발 상황은 종료 후 안내됩니다.)
        </span>
      </label>
      <button class="btn primary go" :disabled="!ready" @click="start">{{ busy ? '입장 중…' : '대화방 입장' }}</button>
    </section>
  </main>
</template>

<style scoped>
.step { margin-top: 16px; }
.step-h { display: flex; align-items: center; gap: 10px; font-weight: 700; margin-bottom: 12px; }
.step-h b { width: 24px; height: 24px; display: grid; place-items: center; border-radius: 50%; background: var(--brand); color: #fff; font-size: 13px; }
.cats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.cat { display: flex; flex-direction: column; gap: 4px; text-align: left; padding: 16px; border: 1.5px solid var(--line); border-radius: 12px; background: var(--panel); color: var(--ink); transition: 0.15s; }
.cat:hover { border-color: var(--brand); }
.cat.on { border-color: var(--brand); background: var(--brand-soft); box-shadow: 0 0 0 3px var(--brand-soft); }
.cat .ic { font-size: 26px; }
.cat small { color: var(--muted); }
.st { margin: 6px 0 6px; }
.step-h .tabs { margin-left: auto; display: flex; background: var(--bg); border-radius: 10px; padding: 3px; }
.tabs button { border: 0; background: transparent; padding: 6px 12px; border-radius: 8px; font-weight: 600; color: var(--muted); }
.tabs button.on { background: var(--panel); color: var(--brand); box-shadow: var(--shadow); }
.hint { margin: -4px 0 10px; }
.lbl { font-size: 12px; font-weight: 700; color: var(--muted); margin: 10px 0 6px; }
.bg { margin: 0 0 8px; }
.people { display: flex; gap: 14px; flex-wrap: wrap; margin: 14px 0; }
.person { display: flex; align-items: center; gap: 10px; padding: 8px 14px 8px 8px; border: 1px solid var(--line); border-radius: 999px; }
.person div { display: flex; flex-direction: column; line-height: 1.25; }
.person small { color: var(--muted); font-size: 12px; }
.av { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; background: var(--line); font-size: 18px; }
.av.me { background: var(--brand); color: #fff; font-size: 13px; font-weight: 700; }
.flow { margin: 4px 0 14px; }
.consent { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border-radius: 10px; background: var(--bg); font-size: 13px; cursor: pointer; }
.consent input { margin-top: 3px; }
.go { margin-top: 14px; width: 100%; padding: 13px; font-size: 16px; }
@media (max-width: 800px) { .cats { grid-template-columns: repeat(2, 1fr); } }
</style>
