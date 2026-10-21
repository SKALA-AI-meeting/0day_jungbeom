<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api, sendMessage } from '../api'
import ChatBubble from '../components/ChatBubble.vue'
import MilestoneStepper from '../components/MilestoneStepper.vue'

const props = defineProps({ id: String })
const meta = ref(null)
const sess = ref(null)
const messages = ref([])
const typing = ref(null)
const sending = ref(false)
const draft = ref('')
const notes = ref('')
const noteState = ref('')
const error = ref('')
const chatEl = ref(null)
const pickedOpt = ref(null)

const personas = computed(() => Object.fromEntries((sess.value?.scenario.personas || []).map((p) => [p.id, p])))
const whoOf = (sp) => (sp === 'user' ? { name: sess.value.alias } : personas.value[sp])
const done = computed(() => sess.value?.status === 'completed')
const choosing = computed(() => sess.value?.dilemma && !sess.value.choice && !done.value)
const optLabel = (id) => sess.value?.dilemma?.options.find((o) => o.id === id)?.label || ''

async function load() {
  const [m, s] = await Promise.all([api.meta(), api.getSession(props.id)])
  meta.value = m
  sess.value = s
  messages.value = s.messages
  notes.value = s.notes
  scrollDown()
}
onMounted(() => load().catch(() => (error.value = '세션을 불러오지 못했어요.')))

function scrollDown() {
  nextTick(() => chatEl.value && (chatEl.value.scrollTop = chatEl.value.scrollHeight))
}
watch(() => [messages.value.length, typing.value], scrollDown)

async function send() {
  const text = draft.value.trim()
  if (!text || sending.value || done.value) return
  const choiceId = choosing.value ? pickedOpt.value : null
  draft.value = ''
  sending.value = true
  error.value = ''
  try {
    await sendMessage(props.id, text, (ev) => {
      if (ev.type === 'user_message') {
        messages.value.push(ev.message)
        if (ev.message.choice) sess.value.choice = { option: ev.message.choice } // close the choice panel right away
      }
      else if (ev.type === 'typing') typing.value = ev.speaker
      else if (ev.type === 'message') {
        typing.value = null
        messages.value.push(ev.message)
      } else if (ev.type === 'state') {
        sess.value.milestone_idx = ev.milestone_idx
        sess.value.status = ev.status
        if (ev.choice) sess.value.choice = ev.choice
      } else if (ev.type === 'dilemma') sess.value.dilemma = ev.dilemma
      else if (ev.type === 'error') error.value = ev.message
    }, choiceId)
    if (choiceId) pickedOpt.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    typing.value = null
    sending.value = false
    if (sess.value.status === 'completed') sess.value = await api.getSession(props.id)
  }
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

let timer
watch(notes, (v) => {
  if (!sess.value || v === sess.value.notes) return
  noteState.value = '저장 중…'
  clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      await api.saveNotes(props.id, v)
      sess.value.notes = v
      noteState.value = '자동 저장됨'
    } catch {
      noteState.value = '저장 실패'
    }
  }, 700)
})

function addTemplate(h) {
  notes.value += (notes.value && !notes.value.endsWith('\n') ? '\n' : '') + `${h}: `
}

async function finish() {
  if (!confirm('대화를 마무리할까요? 종료하면 더 이상 메시지를 보낼 수 없어요.')) return
  sess.value = await api.finish(props.id)
}
</script>

<template>
  <main v-if="sess && meta" class="wrap">
    <aside class="left">
      <div class="card">
        <h3>진행 단계</h3>
        <MilestoneStepper :milestones="meta.milestones" :current="sess.milestone_idx" :done="done" />
      </div>
      <div class="card ctx">
        <h3>{{ sess.scenario.category }}</h3>
        <b>{{ sess.scenario.title }}</b>
        <p class="muted small">{{ sess.scenario.background }}</p>
      </div>
    </aside>

    <section class="chat card">
      <header>
        <div>
          <b># 팀 채널</b>
          <span class="muted small">
            · {{ sess.alias }}, <template v-for="(p, i) in sess.scenario.personas" :key="p.id">{{ p.emoji }} {{ p.name }}<template v-if="i === 0">, </template></template>
          </span>
        </div>
        <button v-if="!done" class="btn sm" @click="finish">대화 마무리</button>
        <span v-else class="chip green">종료됨</span>
      </header>

      <div ref="chatEl" class="msgs">
        <template v-for="m in messages" :key="m.idx">
          <ChatBubble :message="m" :who="whoOf(m.speaker)" :mine="m.speaker === 'user'" :tag="m.choice ? optLabel(m.choice) : ''" />
        </template>
        <div v-if="typing" class="typing">{{ personas[typing]?.emoji }} {{ personas[typing]?.name }} 입력 중…</div>

        <div v-if="done && sess.debrief" class="debrief card">
          <h3>디브리핑 · 이번 대화에서 준비된 상황</h3>
          <p class="muted small">AI는 관찰·기록만 하고, 최종 판단은 채용 담당자가 합니다. 대화에 아래 상황이 단계별로 준비돼 있었어요.</p>
          <ol>
            <li v-for="d in sess.debrief" :key="d.key"><b>{{ d.label }}</b> — {{ d.situation }}</li>
          </ol>
        </div>
      </div>

      <div v-if="choosing" class="choice">
        <div class="choice-h"><b>결정이 필요해요</b><span class="muted small">{{ sess.dilemma.prompt }}</span></div>
        <div class="opts">
          <button v-for="o in sess.dilemma.options" :key="o.id" class="opt" :class="{ on: pickedOpt === o.id }" @click="pickedOpt = pickedOpt === o.id ? null : o.id">
            <span class="radio" />{{ o.label }}
          </button>
        </div>
        <small class="muted">{{ pickedOpt ? '아래에 이유를 적고 보내면 선택이 함께 전달돼요.' : '선택하지 않고 대화만 이어가도 돼요. 선택은 한 번만 할 수 있어요.' }}</small>
      </div>
      <p v-if="error" class="chip red err">{{ error }}</p>
      <footer>
        <textarea
          v-model="draft"
          rows="2"
          :disabled="sending || done"
          :placeholder="done ? '종료된 대화예요' : pickedOpt ? '이 선택을 한 이유를 적어 주세요' : 'Enter로 전송, Shift+Enter로 줄바꿈'"
          @keydown="onKey"
        />
        <button class="btn primary" :disabled="sending || done || !draft.trim()" @click="send">{{ pickedOpt ? '선택과 함께 보내기' : '보내기' }}</button>
      </footer>
    </section>

    <aside class="right">
      <div class="card notes">
        <h3>내 노트 <small class="muted">{{ noteState }}</small></h3>
        <div class="tpl">
          <button v-for="h in ['쟁점', '합의된 것', '내 제안', '다음 할 일']" :key="h" class="btn sm" @click="addTemplate(h)">+ {{ h }}</button>
        </div>
        <textarea v-model="notes" :disabled="done" placeholder="대화를 정리해 두세요. 쟁점, 합의한 내용, 해야 할 일 등 자유롭게." />
      </div>
    </aside>
  </main>
  <p v-else class="page muted">{{ error || '불러오는 중…' }}</p>
</template>

<style scoped>
.wrap { display: grid; grid-template-columns: 250px minmax(0, 1fr) 300px; gap: 16px; padding: 16px 20px; height: calc(100vh - 57px); }
.left, .right { display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.ctx p { margin: 6px 0 0; }
.chat { display: flex; flex-direction: column; padding: 0; min-height: 0; }
.chat header { display: flex; justify-content: space-between; align-items: center; padding: 12px 18px; border-bottom: 1px solid var(--line); }
.msgs { flex: 1; overflow-y: auto; padding: 8px 18px 16px; }
.typing { color: var(--muted); font-size: 13px; padding: 4px 8px; animation: pulse 1.2s infinite; }
@keyframes pulse { 50% { opacity: 0.4; } }
.chat footer { display: flex; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--line); }
.chat textarea { flex: 1; resize: none; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }
.err { margin: 0 16px 8px; }
.choice { margin: 0 16px 8px; padding: 12px 14px; border: 1.5px solid var(--brand); border-radius: 12px; background: color-mix(in srgb, var(--brand-soft) 50%, var(--panel)); }
.choice-h { display: flex; gap: 10px; align-items: baseline; margin-bottom: 8px; flex-wrap: wrap; }
.opts { display: flex; flex-direction: column; gap: 6px; margin-bottom: 6px; }
.opt { display: flex; gap: 10px; align-items: center; text-align: left; padding: 9px 12px; border: 1.5px solid var(--line); border-radius: 10px; background: var(--panel); color: var(--ink); }
.opt:hover { border-color: var(--brand); }
.opt.on { border-color: var(--brand); background: var(--brand-soft); font-weight: 600; }
.radio { width: 14px; height: 14px; flex: none; border-radius: 50%; border: 2px solid var(--line); }
.opt.on .radio { border: 4px solid var(--brand); }
.notes { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.notes h3 { display: flex; justify-content: space-between; align-items: baseline; }
.notes textarea { flex: 1; resize: none; margin-top: 10px; padding: 10px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); line-height: 1.6; }
.tpl { display: flex; flex-wrap: wrap; gap: 6px; }
.debrief { margin: 16px 0 4px; background: var(--brand-soft); border-color: transparent; }
.debrief ol { padding-left: 18px; margin: 8px 0 0; }
.debrief li { margin: 6px 0; }
@media (max-width: 1000px) {
  .wrap { grid-template-columns: 1fr; height: auto; }
  .chat { height: 70vh; }
}
</style>
