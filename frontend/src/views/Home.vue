<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const meta = ref(null)
const alias = ref(localStorage.getItem('dz_alias') || '')
const picked = ref(null)
const agreed = ref(false)
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    meta.value = await api.meta()
  } catch (e) {
    error.value = '서버에 연결하지 못했어요. 백엔드가 실행 중인지 확인해 주세요.'
  }
})

const scenario = computed(() => meta.value?.scenarios.find((s) => s.id === picked.value))
const ready = computed(() => alias.value.trim() && scenario.value && agreed.value && !busy.value)
const ICON = { delay: '⏱️', scope: '🔀', conflict: '⚖️', workload: '🤝' }

async function start() {
  busy.value = true
  error.value = ''
  try {
    localStorage.setItem('dz_alias', alias.value.trim())
    const s = await api.createSession(alias.value.trim(), picked.value)
    router.push(`/s/${s.id}`)
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

    <section class="card step">
      <div class="step-h"><b>1</b> 사용할 별칭</div>
      <input class="text" v-model="alias" maxlength="20" placeholder="예: 지원자A (실명 대신 별칭을 써 주세요)" />
    </section>

    <section class="card step">
      <div class="step-h"><b>2</b> 상황 카테고리 선택</div>
      <div class="cats">
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
      <div class="step-h"><b>3</b> 오늘의 상황</div>
      <h3 class="st">{{ scenario.title }}</h3>
      <p class="bg">{{ scenario.background }}</p>
      <p class="muted small">{{ scenario.brief }}</p>
      <div class="people">
        <div class="person"><span class="av me">나</span><div><b>{{ alias || '지원자' }}</b><small>같은 팀 기획자 (오늘 합류)</small></div></div>
        <div v-for="p in scenario.personas" :key="p.id" class="person">
          <span class="av">{{ p.emoji }}</span><div><b>{{ p.name }}</b><small>{{ p.role }} · AI</small></div>
        </div>
      </div>
      <p class="muted small flow">
        진행 방식: <b>소통 → 조율 → 타협 → 설득</b> 네 단계로 대화가 이어지고, 왼쪽에서 현재 단계를 볼 수 있어요. 오른쪽 노트에 생각을 정리해도 좋아요.
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
.st { margin: 0 0 6px; }
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
