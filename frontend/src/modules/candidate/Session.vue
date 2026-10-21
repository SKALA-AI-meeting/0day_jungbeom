<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, auth, streamTask } from '../../api'
import ArtifactTable from '../../components/ArtifactTable.vue'
import ArtifactViewer from '../../components/ArtifactViewer.vue'
import ChatBubble from '../../components/ChatBubble.vue'
import MilestoneStepper from '../../components/MilestoneStepper.vue'
import { MS_HINT } from '../../constants'
import { MARK, anchorLabel, annRange, normAnnotation, normArtifacts } from '../../utils/artifacts'

const props = defineProps({ id: String })
const route = useRoute()
const meta = ref(null)
const sess = ref(null)
const messages = ref([])
const artifacts = ref([])
const typing = ref(null)
const toolStatus = ref('')
const sending = ref(false)
const draft = ref('')
const notes = ref('')
const noteState = ref('')
const error = ref('')
const chatEl = ref(null)
const draftEl = ref(null)
const pickedOpt = ref(null)
const openId = ref(null)
const focusLine = ref(null)
const stick = ref(true) // follow new lines only while the reader is at the bottom
const unseen = ref(false)
const bgOpen = ref(false) // folded so the team list stays in view; the opening message carries the situation
const restarting = ref(false)

const personas = computed(() => Object.fromEntries((sess.value?.scenario.personas || []).map((p) => [p.id, p])))
const whoOf = (sp) => (sp === 'user' ? { name: sess.value.alias } : personas.value[sp])
const done = computed(() => sess.value?.status === 'completed')
const choosing = computed(() => sess.value?.dilemma && !sess.value.choice && !done.value)
const optLabel = (id) => sess.value?.dilemma?.options.find((o) => o.id === id)?.label || ''
const MS = ['communicate', 'coordinate', 'compromise', 'persuade']
const curMs = computed(() => meta.value?.milestones[Math.min(sess.value?.milestone_idx ?? 0, MS.length - 1)])
const startFailed = computed(() => sess.value?.start_status === 'failed' && !messages.value.length && !sending.value)
const openArt = computed(() => artifacts.value.find((a) => a.id === openId.value) || null)
const markups = computed(() => artifacts.value.reduce((n, a) => n + a.annotations.length, 0))
const recentMarks = computed(() =>
  artifacts.value.flatMap((a) => a.annotations.map((n) => ({ ...n, art: a }))).sort((x, y) => (y.createdAt || 0) - (x.createdAt || 0) || y.id - x.id),
)
// one indicator line under the messages; a persona whose words are already streaming needs no "입력 중"
const indicator = computed(() => {
  if (toolStatus.value) return { key: 'tool', emoji: '📄', text: toolStatus.value }
  if (typing.value && !messages.value.some((m) => m.live && m.speaker === typing.value && m.text)) {
    const p = personas.value[typing.value]
    return { key: `t:${typing.value}`, emoji: p?.emoji, text: `${p?.name || '팀원'} 입력 중` }
  }
  if (sending.value && !messages.value.some((m) => m.live)) return { key: 'wait', emoji: '💬', text: messages.value.length ? '팀원들이 읽는 중' : '팀원들이 채널에 들어오는 중' }
  return null
})

async function refresh() {
  const s = await api.getSession(props.id)
  sess.value = s
  messages.value = s.messages
  artifacts.value = normArtifacts(s.artifacts)
  if (!noteState.value) notes.value = s.notes
  return s
}

async function load() {
  meta.value = await api.meta()
  const s = await refresh()
  scrollDown(true, true)
  // resume a task that is still running (page reload, or the opening line right after start)
  let active = route.query.task
  if (!active && s.busy) {
    const mine = await api.myTasks(auth.candidate())
    active = mine.find((t) => t.sessionId === props.id && ['QUEUED', 'RUNNING'].includes(t.status))?.id
  }
  if (active) follow(active)
}
onMounted(() => load().catch((e) => (error.value = e.message || '세션을 불러오지 못했어요.')))

const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
function onScroll() {
  const el = chatEl.value
  stick.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  if (stick.value) unseen.value = false
}
function scrollDown(force = false, instant = false) {
  nextTick(() => {
    const el = chatEl.value
    if (!el) return
    if (!force && !stick.value) return void (unseen.value = true)
    el.scrollTo({ top: el.scrollHeight, behavior: instant || reduced() ? 'auto' : 'smooth' })
    stick.value = true
    unseen.value = false
  })
}
watch(() => messages.value.length, () => scrollDown())
watch(() => [messages.value.at(-1)?.text, indicator.value?.key], () => scrollDown(false, true))

/** Apply streamed TOKEN deltas to a live bubble; DONE / FAILED re-read the authoritative state from Spring. */
async function follow(taskId) {
  sending.value = true
  try {
    await streamTask(taskId, auth.candidate(), (ev) => {
      const d = ev.data || {}
      if (ev.type === 'TOKEN') {
        let m = messages.value.find((x) => x.idx === d.idx)
        if (!m) {
          messages.value.forEach((x) => (x.live = false)) // the caret moves to the newest speaker
          m = { idx: d.idx, speaker: d.speaker, text: '', milestone: d.milestone, live: true }
          messages.value.push(m)
        }
        if (d.reset) m.text = ''
        m.text += d.delta || ''
        typing.value = d.speaker
        const mi = MS.indexOf(d.milestone)
        if (sess.value && mi > sess.value.milestone_idx) sess.value.milestone_idx = mi
      } else if (ev.type === 'TOOL_START' && String(d.tool).startsWith('rag.')) {
        toolStatus.value = '회사 문서를 확인하는 중'
      } else if (ev.type === 'TOOL_START' && String(d.tool).includes('artifact')) {
        toolStatus.value = '같이 보는 과제를 확인하는 중'
      } else if (ev.type === 'TOOL_END') {
        toolStatus.value = ''
      } else if (ev.type === 'FAILED' && messages.value.length) {
        error.value = '팀원들의 응답을 만들지 못했어요. 같은 내용을 한 번 더 보내 주세요.'
      }
    })
  } catch (e) {
    error.value = e.message
  } finally {
    typing.value = null
    toolStatus.value = ''
    sending.value = false
    await refresh().catch(() => {})
  }
}

async function send() {
  const text = draft.value.trim()
  if (!text || sending.value || done.value) return
  const choiceId = choosing.value ? pickedOpt.value : null
  error.value = ''
  sending.value = true
  try {
    const r = await api.submitTurn(props.id, text, choiceId)
    draft.value = ''
    messages.value.push(r.userMessage)
    scrollDown(true)
    if (choiceId) {
      sess.value.choice = { option: choiceId } // close the choice panel right away
      pickedOpt.value = null
    }
    await follow(r.taskId)
  } catch (e) {
    error.value = e.message
    sending.value = false
  }
}

/** The opening lines failed (START task FAILED, no messages yet): ask Spring for a new START and follow it. */
async function restart() {
  restarting.value = true
  error.value = ''
  try {
    const r = await api.restartSession(props.id)
    sess.value.start_status = 'running'
    await follow(r.taskId)
  } catch (e) {
    error.value = e.status === 409 ? '이미 다시 준비하고 있어요. 잠시 뒤 새로고침해 주세요.' : e.message
    await refresh().catch(() => {})
  } finally {
    restarting.value = false
  }
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

// error chips float over the bottom of the chat; they never push the composer around
let errTimer
watch(error, (v) => {
  clearTimeout(errTimer)
  if (v && sess.value) errTimer = setTimeout(() => (error.value = ''), 9000) // a load error stays on the page
})

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
onBeforeUnmount(() => { clearTimeout(timer); clearTimeout(errTimer) })

function addTemplate(h) {
  notes.value += (notes.value && !notes.value.endsWith('\n') ? '\n' : '') + `${h}: `
}

// ---------------------------------------------------------------- shared artifacts + markups
async function saveMarkup({ artifactId, anchor, kind, text }) {
  const n = normAnnotation(await api.addAnnotation(props.id, artifactId, anchor, kind, text))
  artifacts.value.find((a) => a.id === artifactId)?.annotations.push(n)
  return n
}
async function removeMarkup(n) {
  await api.deleteAnnotation(props.id, n.id)
  const a = artifacts.value.find((x) => x.id === n.artifactId)
  if (a) a.annotations = a.annotations.filter((x) => x.id !== n.id)
}
function openAt(a, line = null) {
  focusLine.value = line
  openId.value = a.id
}
/** "대화에 인용": put a short reference like [기획안 L12-14] into the draft and hand the cursor back to the chat. */
function cite(refText) {
  const d = draft.value
  draft.value = `${d}${d && !/\s$/.test(d) ? ' ' : ''}${refText} `
  openId.value = null
  setTimeout(() => {
    const el = draftEl.value
    if (!el) return
    el.focus()
    el.setSelectionRange(el.value.length, el.value.length)
  }, 240)
}

const confirmFinish = ref(false)
async function finish() {
  if (!confirmFinish.value) {
    confirmFinish.value = true
    return
  }
  confirmFinish.value = false
  sess.value = await api.finish(props.id)
  if (sess.value.artifacts) artifacts.value = normArtifacts(sess.value.artifacts)
}
</script>

<template>
  <main v-if="sess && meta" class="wrap">
    <aside class="left">
      <div class="card">
        <h3>진행 단계</h3>
        <MilestoneStepper :milestones="meta.milestones" :current="sess.milestone_idx" :done="done" />
      </div>

      <div class="card situ">
        <span class="chip blue cat">{{ sess.scenario.category }}</span>
        <h3 class="st">{{ sess.scenario.title }}</h3>
        <p v-if="sess.scenario.brief" class="brief">{{ sess.scenario.brief }}</p>

        <Transition name="swap" mode="out-in">
          <section v-if="!done && curMs" :key="curMs.key" class="ask">
            <small>지금 단계 · {{ curMs.label }}</small>
            <p>{{ MS_HINT[curMs.key] || curMs.desc }}</p>
          </section>
        </Transition>

        <button type="button" class="fold" :aria-expanded="bgOpen" aria-controls="situ-bg" @click="bgOpen = !bgOpen">
          <span>상황 배경</span><i :class="{ up: bgOpen }" aria-hidden="true">⌄</i>
        </button>
        <div id="situ-bg" class="collapse" :class="{ open: bgOpen }">
          <div><p class="bg">{{ sess.scenario.background }}</p></div>
        </div>

        <h4>팀원</h4>
        <ul class="team">
          <li v-for="p in sess.scenario.personas" :key="p.id"><span class="av">{{ p.emoji }}</span><b>{{ p.name }}</b><small>{{ p.role }}</small></li>
          <li><span class="av me">나</span><b>{{ sess.alias }}</b><small>지원자</small></li>
        </ul>
      </div>
    </aside>

    <section class="chat card">
      <header>
        <div class="ch">
          <b># 팀 채널</b>
          <span class="muted small">
            {{ sess.alias }}, <template v-for="(p, i) in sess.scenario.personas" :key="p.id">{{ p.emoji }} {{ p.name }}<template v-if="i < sess.scenario.personas.length - 1">, </template></template>
          </span>
        </div>
        <button v-if="!done" class="btn sm" :class="{ warn: confirmFinish }" @click="finish">{{ confirmFinish ? '한 번 더 누르면 종료돼요' : '대화 마무리' }}</button>
        <span v-else class="chip green">종료됨</span>
      </header>

      <div class="stage">
        <div ref="chatEl" class="msgs" @scroll.passive="onScroll">
          <TransitionGroup name="msg">
            <ChatBubble
              v-for="m in messages"
              :key="m.idx"
              :message="m"
              :who="whoOf(m.speaker)"
              :mine="m.speaker === 'user'"
              :tag="m.choice ? optLabel(m.choice) : ''"
              :sources="m.sources || []"
            />
          </TransitionGroup>

          <Transition name="fade" mode="out-in">
            <div v-if="indicator" :key="indicator.key" class="typing" role="status">
              <span class="av">{{ indicator.emoji }}</span>
              <span class="dots" aria-hidden="true"><i /><i /><i /></span>
              <span>{{ indicator.text }}…</span>
            </div>
          </Transition>

          <Transition name="fade">
            <div v-if="startFailed" class="restart">
              <b>팀원들이 대화를 시작하지 못했어요</b>
              <p>첫 메시지를 준비하다가 문제가 생겼어요. 다시 시작하면 팀원들이 처음부터 다시 들어와요. 지금까지 쓴 노트는 그대로예요.</p>
              <button class="btn primary" :disabled="restarting" @click="restart">{{ restarting ? '다시 준비하는 중…' : '다시 시작하기' }}</button>
            </div>
          </Transition>

          <div v-if="done && sess.debrief" class="debrief card">
            <h3>디브리핑 · 이번 대화에서 준비된 상황</h3>
            <p class="muted small">AI는 관찰·기록만 하고, 최종 판단은 채용 담당자가 합니다. 대화에 아래 상황이 단계별로 준비돼 있었어요.</p>
            <ol>
              <li v-for="d in sess.debrief" :key="d.key"><b>{{ d.label }}</b> — {{ d.situation }}</li>
            </ol>
          </div>
        </div>

        <Transition name="fade">
          <button v-if="unseen" type="button" class="jump-new" @click="scrollDown(true)">새 메시지 ↓</button>
        </Transition>
        <Transition name="toast">
          <div v-if="error" class="toast" role="alert">
            <span>{{ error }}</span>
            <button type="button" aria-label="닫기" @click="error = ''">✕</button>
          </div>
        </Transition>
      </div>

      <Transition name="unfold">
        <div v-if="choosing" class="choice-wrap">
          <div class="clip"><div class="choice">
            <div class="choice-h"><b>결정이 필요해요</b><span class="muted small">{{ sess.dilemma.prompt }}</span></div>
            <div class="opts" role="radiogroup" aria-label="선택지">
              <button v-for="o in sess.dilemma.options" :key="o.id" type="button" role="radio" :aria-checked="pickedOpt === o.id" class="opt" :class="{ on: pickedOpt === o.id }" @click="pickedOpt = pickedOpt === o.id ? null : o.id">
                <span class="radio" />{{ o.label }}
              </button>
            </div>
            <small class="muted">{{ pickedOpt ? '아래에 이유를 적고 보내면 선택이 함께 전달돼요.' : '선택하지 않고 대화만 이어가도 돼요. 선택은 한 번만 할 수 있어요.' }}</small>
          </div></div>
        </div>
      </Transition>
      <footer>
        <textarea
          ref="draftEl"
          v-model="draft"
          rows="2"
          :disabled="sending || done"
          :placeholder="done ? '종료된 대화예요' : pickedOpt ? '이 선택을 한 이유를 적어 주세요' : 'Enter로 전송, Shift+Enter로 줄바꿈 · **굵게**, $수식$ 지원'"
          @keydown="onKey"
        />
        <button class="btn primary" :disabled="sending || done || !draft.trim()" @click="send">{{ pickedOpt ? '선택과 함께 보내기' : '보내기' }}</button>
      </footer>
    </section>

    <aside class="right">
      <div class="card arts">
        <h3>같이 확인할 과제 <small class="muted">마크업 {{ markups }}개</small></h3>
        <template v-if="artifacts.length">
          <ArtifactTable :artifacts="artifacts" :personas="personas" :active="openId" @open="(a) => openAt(a)" />
          <p v-if="!recentMarks.length" class="tip">과제를 열어 줄이나 문장을 고르면 질문·우려·제안을 마크업으로 남길 수 있어요. <b>팀원도 마크업을 볼 수 있어요.</b></p>
          <template v-else>
            <h4 class="mh">내 마크업 <small class="muted">팀원도 볼 수 있어요</small></h4>
            <TransitionGroup tag="ul" name="mk" class="mine">
              <li v-for="n in recentMarks" :key="n.id">
                <button type="button" :style="{ '--c': MARK[n.kind]?.color }" @click="openAt(n.art, annRange(n, n.art.body)?.[0] ?? null)">
                  <span class="mk-h"><i>{{ MARK[n.kind]?.label || n.kind }}</i><b>{{ n.art.title }}</b><small>{{ anchorLabel(n) }}</small></span>
                  <span class="mk-t">{{ n.text }}</span>
                </button>
              </li>
            </TransitionGroup>
          </template>
        </template>
        <p v-else class="muted small empty">이번 대화에는 같이 볼 과제가 없어요.</p>
      </div>

      <div class="card notes">
        <h3>내 노트 <small class="muted">{{ noteState }}</small></h3>
        <div class="tpl">
          <button v-for="h in ['쟁점', '합의된 것', '내 제안', '다음 할 일']" :key="h" class="btn sm" :disabled="done" @click="addTemplate(h)">+ {{ h }}</button>
        </div>
        <textarea v-model="notes" :disabled="done" placeholder="대화를 정리해 두세요. 쟁점, 합의한 내용, 해야 할 일 등 자유롭게." />
      </div>
    </aside>

    <ArtifactViewer
      :artifact="openArt"
      :personas="personas"
      :focus-line="focusLine"
      :editable="!done"
      :can-cite="!done"
      :save="saveMarkup"
      :remove="removeMarkup"
      @close="openId = null"
      @cite="cite"
    />
  </main>
  <p v-else class="page muted">{{ error || '불러오는 중…' }}</p>
</template>

<style scoped>
.wrap { display: grid; grid-template-columns: 264px minmax(0, 1fr) clamp(340px, 34vw, 540px); gap: 16px; padding: 16px 20px; height: calc(100dvh - var(--topbar-h)); }
.left, .right { display: flex; flex-direction: column; gap: 16px; min-height: 0; }
.left { overflow-y: auto; scrollbar-gutter: stable; margin-right: -6px; padding-right: 6px; }
.left > .card { flex: none; }

/* situation: title, what this step asks, foldable background, who is who */
.situ { display: flex; flex-direction: column; padding: 18px; }
.cat { align-self: flex-start; }
.situ .st { margin: 8px 0 0; font-size: 16px; line-height: 1.4; }
.brief { margin: 6px 0 0; font-size: 14px; line-height: 1.65; }
.ask { margin-top: 14px; padding: 10px 12px; border-radius: 10px; background: var(--brand-soft); border-left: 3px solid var(--brand); }
.ask small { display: block; font-size: 12px; font-weight: 700; color: var(--brand); margin-bottom: 2px; }
.ask p { margin: 0; font-size: 13.5px; line-height: 1.65; }
.fold { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; padding: 6px 0; border: 0; border-top: 1px solid var(--line); background: none; color: var(--ink); font-size: 13px; font-weight: 700; }
.fold i { font-style: normal; color: var(--muted); transition: transform 0.25s; }
.fold i.up { transform: rotate(180deg); }
.collapse { display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.3s ease; }
.collapse.open { grid-template-rows: 1fr; }
.collapse > div { overflow: hidden; }
.bg { margin: 2px 0 4px; font-size: 13.5px; line-height: 1.75; color: var(--ink); opacity: 0.88; }
.situ h4 { margin: 12px 0 6px; padding-top: 10px; border-top: 1px solid var(--line); font-size: 13px; }
.team { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.team li { display: grid; grid-template-columns: 28px auto 1fr; gap: 8px; align-items: center; font-size: 13.5px; }
.team .av { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: var(--line); font-size: 15px; }
.team .av.me { background: var(--brand); color: #fff; font-size: 11px; font-weight: 800; }
.team small { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.chat { display: flex; flex-direction: column; padding: 0; min-height: 0; min-width: 0; }
.chat header { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 18px; border-bottom: 1px solid var(--line); }
.ch { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ch .small { margin-left: 6px; }
.stage { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.msgs { flex: 1; overflow-y: auto; padding: 8px 18px 16px; overscroll-behavior: contain; }
.typing { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 13px; padding: 6px 2px; }
.typing .av { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: var(--line); font-size: 15px; }
.dots { display: inline-flex; gap: 3px; padding: 8px 10px; border-radius: 12px; background: var(--panel); border: 1px solid var(--line); }
.dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: bounce 1.2s ease-in-out infinite; }
.dots i:nth-child(2) { animation-delay: 0.15s; }
.dots i:nth-child(3) { animation-delay: 0.3s; }
.restart { margin: 24px auto; max-width: 440px; padding: 18px 20px; border-radius: 14px; border: 1.5px solid #fca5a5; background: color-mix(in srgb, #fee2e2 55%, var(--panel)); display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.restart p { margin: 0; font-size: 13.5px; line-height: 1.6; }
.jump-new { position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%); padding: 6px 14px; border-radius: 999px; border: 1px solid var(--brand); background: var(--panel); color: var(--brand); font-size: 12.5px; font-weight: 700; box-shadow: var(--shadow); }
.toast { position: absolute; left: 16px; right: 16px; bottom: 12px; display: flex; gap: 10px; align-items: center; padding: 9px 12px; border-radius: 10px; background: #fee2e2; color: #991b1b; font-size: 13px; font-weight: 600; box-shadow: 0 6px 20px rgba(15, 23, 42, 0.14); z-index: 2; }
.toast span { flex: 1; }
.toast button { border: 0; background: none; color: inherit; font-size: 12px; }
.chat footer { display: flex; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--line); }
.chat textarea { flex: 1; resize: none; padding: 10px 12px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); line-height: 1.5; }
.btn.warn { border-color: var(--warn); color: var(--warn); }
.choice-wrap { display: grid; grid-template-rows: 1fr; padding: 0 16px; }
.clip { overflow: hidden; min-height: 0; }
.clip > .choice { margin-bottom: 8px; }
.choice { padding: 12px 14px; border: 1.5px solid var(--brand); border-radius: 12px; background: color-mix(in srgb, var(--brand-soft) 50%, var(--panel)); }
.choice-h { display: flex; gap: 10px; align-items: baseline; margin-bottom: 8px; flex-wrap: wrap; }
.opts { display: flex; flex-direction: column; gap: 6px; margin-bottom: 6px; }
.opt { display: flex; gap: 10px; align-items: center; text-align: left; padding: 9px 12px; border: 1.5px solid var(--line); border-radius: 10px; background: var(--panel); color: var(--ink); transition: border-color 0.15s, background 0.15s; }
.opt:hover { border-color: var(--brand); }
.opt.on { border-color: var(--brand); background: var(--brand-soft); font-weight: 600; }
.radio { width: 14px; height: 14px; flex: none; border-radius: 50%; border: 2px solid var(--line); transition: border 0.15s; }
.opt.on .radio { border: 4px solid var(--brand); }

.right { min-width: 0; }
.arts { flex: 1 1 auto; min-height: 160px; overflow-y: auto; padding: 16px 16px 12px; }
.arts h3, .notes h3 { display: flex; justify-content: space-between; align-items: baseline; font-size: 15px; }
.arts h3 small, .notes h3 small { font-size: 12px; font-weight: 500; }
.tip { margin: 10px 0 0; font-size: 12.5px; line-height: 1.6; color: var(--muted); }
.tip b { color: var(--ink); font-weight: 600; }
.mh { display: flex; justify-content: space-between; align-items: baseline; margin: 16px 0 8px; font-size: 13px; }
.mh small { font-size: 11.5px; font-weight: 500; }
.mine { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.mine button { width: 100%; display: flex; flex-direction: column; gap: 3px; padding: 8px 10px; border: 1px solid var(--line); border-left: 3px solid var(--c); border-radius: 9px; background: var(--panel); color: var(--ink); text-align: left; transition: background 0.15s, border-color 0.15s; }
.mine button:hover { background: var(--bg); }
.mk-h { display: flex; align-items: baseline; gap: 6px; min-width: 0; font-size: 12px; }
.mk-h i { font-style: normal; flex: none; font-size: 11px; font-weight: 800; padding: 0 7px; border-radius: 999px; background: color-mix(in srgb, var(--c) 15%, transparent); color: var(--c); }
.mk-h b { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.mk-h small { flex: none; color: var(--muted); font-variant-numeric: tabular-nums; }
.mk-t { font-size: 13px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.mk-enter-active { transition: opacity 0.3s, transform 0.3s; }
.mk-enter-from { opacity: 0; transform: translateY(-4px); }
.empty { margin: 0; }
.notes { flex: none; display: flex; flex-direction: column; padding: 16px; }
.notes h3 { margin-bottom: 8px; }
.notes textarea { height: 132px; resize: vertical; margin-top: 8px; padding: 10px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); line-height: 1.6; font-size: 14px; }
.tpl { display: flex; flex-wrap: wrap; gap: 6px; }
.debrief { margin: 16px 0 4px; background: var(--brand-soft); border-color: transparent; }
.debrief ol { padding-left: 18px; margin: 8px 0 0; }
.debrief li { margin: 6px 0; }

.msg-enter-active { transition: opacity 0.32s ease, transform 0.32s cubic-bezier(0.2, 0.9, 0.3, 1); }
.msg-enter-from { opacity: 0; transform: translateY(10px) scale(0.98); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.swap-enter-active, .swap-leave-active { transition: opacity 0.25s, transform 0.25s; }
.swap-enter-from { opacity: 0; transform: translateY(4px); }
.swap-leave-to { opacity: 0; transform: translateY(-4px); }
.toast-enter-active, .toast-leave-active { transition: opacity 0.22s, transform 0.22s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(8px); }
.unfold-enter-active, .unfold-leave-active { transition: grid-template-rows 0.3s ease, opacity 0.3s ease; }
.unfold-enter-from, .unfold-leave-to { grid-template-rows: 0fr; opacity: 0; }
@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); opacity: 0.5; } 30% { transform: translateY(-4px); opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
  .dots i { animation: none; }
  .msg-enter-active, .swap-enter-active, .swap-leave-active, .unfold-enter-active, .unfold-leave-active, .collapse { transition: none; }
}
@media (max-width: 1180px) {
  .wrap { grid-template-columns: 232px minmax(0, 1fr) 336px; gap: 12px; padding: 12px 14px; }
}
@media (max-width: 980px) {
  .wrap { grid-template-columns: minmax(0, 1fr) 320px; height: auto; min-height: calc(100dvh - var(--topbar-h)); }
  .left { grid-column: 1 / -1; flex-direction: row; align-items: flex-start; overflow: visible; margin-right: 0; padding-right: 0; }
  .left > .card { flex: 1 1 0; min-width: 0; }
  .chat { height: calc(100dvh - var(--topbar-h) - 24px); }
  .right { max-height: calc(100dvh - var(--topbar-h) - 24px); }
}
@media (max-width: 720px) {
  .wrap { grid-template-columns: 1fr; padding: 12px 16px; }
  .left { flex-direction: column; align-items: stretch; }
  .chat { height: 72vh; }
  .right { max-height: none; }
}
</style>
