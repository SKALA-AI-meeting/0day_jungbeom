<script setup>
// Drawer for one shared artifact. Design/result read as Markdown (+KaTeX) or as numbered source; code always numbered.
// Candidate: click a line (Shift+click for a range) or drag over text, then leave a markup the team can see.
// Admin: read-only, with the planted checkpoints (spotted / missed) next to the candidate's markups.
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { renderMarkdown } from '../utils/markdown'
import { KIND, MARK, MARK_KINDS, OWNER_TEAM, anchorLabel, annRange, citeRef, rangeLabel } from '../utils/artifacts'

const props = defineProps({
  artifact: { type: Object, default: null }, // normArtifacts() item; null = closed
  personas: { type: Object, default: () => ({}) },
  editable: Boolean, // candidate, session still active
  canCite: Boolean, // "대화에 인용" into the chat draft
  checks: { type: Array, default: null }, // admin: normCheck() items of this session
  focusLine: { type: Number, default: null }, // scroll here when opened
  save: { type: Function, default: null }, // async ({ artifactId, anchor, kind, text }) -> annotation
  remove: { type: Function, default: null }, // async (annotation)
})
const emit = defineEmits(['close', 'cite'])

// keep rendering the last artifact while the drawer slides out
const art = ref(null)
const view = ref('read')
const sel = ref(null) // { start, end, quote }
const pivot = ref(null) // [start, end] Shift+click extends from here
const cursor = ref(null) // keyboard position: a line (lines view) or a block index (read view)
const hover = ref(null) // annotation id under the pointer in the list
const flashId = ref(null)
const confirmDel = ref(null)
const railError = ref('')
const live = ref('') // screen-reader announcements
const form = reactive({ kind: 'question', text: '', saving: false, error: '' })
const panelEl = ref(null)
const bodyEl = ref(null)
const docEl = ref(null)
const popEl = ref(null)
const textEl = ref(null)
let opener = null

const open = computed(() => !!props.artifact)
const body = computed(() => art.value?.body || '')
const lines = computed(() => body.value.split('\n'))
const owner = computed(() => (art.value?.owner === 'team' || !props.personas[art.value?.owner] ? OWNER_TEAM : props.personas[art.value.owner]))
const html = computed(() => (art.value && art.value.kind !== 'code' ? renderMarkdown(body.value, { lines: true }) : ''))
const anns = computed(() => (art.value?.annotations || []).map((n) => ({ ...n, range: annRange(n, body.value) })))
const sorted = computed(() => [...anns.value].sort((a, b) => (a.range?.[0] ?? 1e9) - (b.range?.[0] ?? 1e9) || a.id - b.id))
const myChecks = computed(() => (props.checks || []).filter((c) => c.artifactId === art.value?.id).sort((a, b) => a.line - b.line))
const hoverRange = computed(() => anns.value.find((n) => n.id === hover.value)?.range || null)

// per line: markups covering it and a planted checkpoint (admin)
const lineInfo = computed(() => {
  const info = lines.value.map(() => ({ marks: [], check: null }))
  for (const n of anns.value) if (n.range) for (let l = n.range[0]; l <= Math.min(n.range[1], info.length); l++) info[l - 1].marks.push(n)
  for (const c of myChecks.value) if (info[c.line - 1]) info[c.line - 1].check = c
  return info
})
const within = (r, l) => !!r && r[0] <= l && l <= r[1]
const overlaps = (r, s, e) => !!r && r[0] <= e && s <= r[1]
const selRange = computed(() => (sel.value?.start ? [sel.value.start, sel.value.end] : null))

watch(
  () => props.artifact,
  (a, prev) => {
    if (a) {
      const fresh = !art.value || art.value.id !== a.id || !prev
      art.value = a
      if (fresh) reset(a)
    }
  },
  { immediate: true },
)
watch(open, (on) => {
  if (on) {
    opener = document.activeElement
    lockScroll(true)
    nextTick(() => {
      panelEl.value?.querySelector('.x')?.focus({ preventScroll: true })
      if (props.focusLine) {
        const at = props.focusLine
        if (view.value === 'lines') cursor.value = at
        setTimeout(() => {
          scrollToLines([at, at])
          flash(anns.value.find((n) => within(n.range, at))?.id) // opened from a markup: point at it
        }, 260)
      }
    })
  } else {
    lockScroll(false)
    opener?.focus?.({ preventScroll: true })
  }
})
onBeforeUnmount(() => lockScroll(false))

function reset(a) {
  view.value = a.kind === 'code' || props.checks ? 'lines' : 'read'
  sel.value = null
  pivot.value = null
  cursor.value = null
  form.text = ''
  form.error = ''
  confirmDel.value = null
  railError.value = ''
}
function lockScroll(on) {
  document.documentElement.style.overflow = on ? 'hidden' : ''
}
function close() {
  emit('close')
}

// ---------------------------------------------------------------- read view: blocks carry data-ls / data-le
let leaves = []
const blockRange = (el) => [Number(el.dataset.ls), Number(el.dataset.le)]
function collectLeaves() {
  leaves = docEl.value ? [...docEl.value.querySelectorAll('[data-ls]')].filter((el) => !el.querySelector('[data-ls]')) : []
}
function paint() {
  if (view.value !== 'read') return
  const s = selRange.value
  leaves.forEach((el, i) => {
    const [ls, le] = blockRange(el)
    const marks = anns.value.filter((n) => overlaps(n.range, ls, le))
    const chk = myChecks.value.find((c) => ls <= c.line && c.line <= le)
    el.classList.toggle('is-sel', !!s && overlaps(s, ls, le))
    el.classList.toggle('is-cur', cursor.value === i)
    el.classList.toggle('is-hov', overlaps(hoverRange.value, ls, le))
    el.classList.toggle('is-flash', flashId.value != null && marks.some((n) => n.id === flashId.value))
    el.classList.toggle('is-chk', !!chk)
    el.classList.toggle('is-spotted', !!chk?.spotted)
    if (marks.length) el.dataset.mk = marks[0].kind
    else delete el.dataset.mk
    const tip = [...marks.map((n) => `${MARK[n.kind]?.label} · ${n.text}`), ...(chk ? [`확인 지점 · ${chk.issue}`] : [])]
    if (tip.length) el.title = tip.join('\n')
    else el.removeAttribute('title')
  })
}
watch([html, view, open], () => nextTick(() => { collectLeaves(); paint() }), { flush: 'post', immediate: true })
watch([selRange, anns, hoverRange, cursor, flashId, myChecks], paint, { flush: 'post' })

// ---------------------------------------------------------------- selecting
function setSel(start, end, quote = null) {
  sel.value = { start, end, quote }
  form.error = ''
  live.value = `${rangeLabel(start, end) || '인용'} 선택됨`
  nextTick(keepVisible)
}
function clearSel() {
  sel.value = null
  pivot.value = null
}
const textSelected = () => {
  const s = window.getSelection()
  return s && !s.isCollapsed && bodyEl.value?.contains(s.anchorNode)
}
function onDown(e) {
  if (!e.shiftKey || !props.editable) return
  e.preventDefault() // Shift+click extends the line range, not a text selection
  window.getSelection()?.removeAllRanges()
}
function onLineClick(n, e) {
  if (!props.editable || textSelected()) return
  cursor.value = n
  pick([n, n], e.shiftKey)
}
function onDocClick(e) {
  if (!props.editable || textSelected() || e.target.closest('a')) return
  const el = e.target.closest('[data-ls]')
  if (!el || !docEl.value.contains(el)) return
  cursor.value = leaves.indexOf(el)
  pick(blockRange(el), e.shiftKey)
}
function pick(r, extend, toggle = true) {
  if (extend && pivot.value) return setSel(Math.min(pivot.value[0], r[0]), Math.max(pivot.value[1], r[1]))
  const s = sel.value
  if (toggle && s && !s.quote && s.start === r[0] && s.end === r[1]) return clearSel() // a second click on the same line lets go
  pivot.value = r
  setSel(r[0], r[1])
}
/** Drag over text: the quote (when it is literally in the source) plus the lines it spans. */
function onUp() {
  if (!props.editable || !textSelected()) return
  const s = window.getSelection()
  const raw = s.toString().trim()
  if (!raw) return
  const lineOf = (node) => {
    const el = (node.nodeType === 1 ? node : node.parentElement)?.closest(view.value === 'lines' ? '[data-line]' : '[data-ls]')
    if (!el) return null
    return view.value === 'lines' ? [Number(el.dataset.line), Number(el.dataset.line)] : blockRange(el)
  }
  const a = lineOf(s.anchorNode)
  const b = lineOf(s.focusNode)
  const r = a && b ? [Math.min(a[0], b[0]), Math.max(a[1], b[1])] : a || b
  const quote = raw.length <= 300 && body.value.includes(raw) ? raw : null
  if (!r && !quote) return
  pivot.value = r
  setSel(r?.[0] ?? null, r?.[1] ?? null, quote)
}

function anchorEl() {
  const s = window.getSelection()
  if (sel.value?.quote && s && !s.isCollapsed && bodyEl.value?.contains(s.anchorNode)) return s.getRangeAt(0)
  const end = sel.value?.end
  if (!end) return null
  if (view.value === 'lines') return bodyEl.value?.querySelector(`[data-line="${end}"]`)
  return [...leaves].reverse().find((el) => overlaps(blockRange(el), sel.value.start, end)) || null
}
/** The composer docks at the bottom of the body (sticky) so it never covers the lines below a selection; keep the selection above it. */
function keepVisible() {
  const el = anchorEl()
  const p = popEl.value
  if (!el || !p) return
  const over = el.getBoundingClientRect().bottom + 10 - p.getBoundingClientRect().top
  let box = p.parentElement
  while (box && !(/(auto|scroll)/.test(getComputedStyle(box).overflowY) && box.scrollHeight > box.clientHeight)) box = box.parentElement
  if (over > 0 && box) box.scrollBy({ top: over, behavior: reduced() ? 'auto' : 'smooth' })
}
const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// ---------------------------------------------------------------- keyboard: arrows move, Shift+arrows extend, Enter writes
function onBodyKey(e) {
  if (e.target !== bodyEl.value || !props.editable || !['ArrowDown', 'ArrowUp', 'Enter'].includes(e.key)) return
  if (e.key === 'Enter') {
    if (!sel.value && cursor.value != null) moveTo(cursor.value, false)
    if (sel.value) { e.preventDefault(); focusForm() }
    return
  }
  e.preventDefault()
  const max = view.value === 'lines' ? lines.value.length : leaves.length - 1
  const min = view.value === 'lines' ? 1 : 0
  const cur = cursor.value ?? (e.key === 'ArrowDown' ? min - 1 : max + 1)
  moveTo(Math.min(max, Math.max(min, cur + (e.key === 'ArrowDown' ? 1 : -1))), e.shiftKey)
}
function moveTo(c, extend) {
  cursor.value = c
  const r = view.value === 'lines' ? [c, c] : leaves[c] && blockRange(leaves[c])
  if (!r) return
  pick(r, extend, false)
  const el = view.value === 'lines' ? bodyEl.value?.querySelector(`[data-line="${c}"]`) : leaves[c]
  el?.scrollIntoView({ block: 'nearest' })
}

function focusForm(tries = 4) {
  // the popover mounts a frame or two after the selection
  if (textEl.value) textEl.value.focus()
  else if (tries) requestAnimationFrame(() => focusForm(tries - 1))
}

function onPanelKey(e) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    if (sel.value) { clearSel(); bodyEl.value?.focus({ preventScroll: true }) } else close()
    return
  }
  if (e.key !== 'Tab') return
  // focus stays inside the drawer
  const f = [...panelEl.value.querySelectorAll('button, [href], textarea, input, [tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled && x.offsetParent !== null)
  if (!f.length) return
  const i = f.indexOf(document.activeElement)
  if (e.shiftKey && i <= 0) { e.preventDefault(); f.at(-1).focus() }
  else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus() }
}

// ---------------------------------------------------------------- markups
async function submit() {
  const text = form.text.trim()
  if (!text || form.saving || !sel.value) return
  const { start, end, quote } = sel.value
  const anchor = { ...(start ? { lineStart: start, lineEnd: end } : {}), ...(quote ? { quote } : {}) }
  form.saving = true
  form.error = ''
  try {
    const n = await props.save({ artifactId: art.value.id, anchor, kind: form.kind, text })
    form.text = ''
    clearSel()
    window.getSelection()?.removeAllRanges()
    flash(n?.id)
    live.value = '마크업을 남겼어요. 팀원도 볼 수 있어요.'
    bodyEl.value?.focus({ preventScroll: true })
  } catch (e) {
    form.error = e.message || '마크업을 남기지 못했어요.'
  } finally {
    form.saving = false
  }
}
function onFormKey(e) {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.isComposing) { e.preventDefault(); submit() }
}
async function del(n) {
  if (confirmDel.value !== n.id) {
    confirmDel.value = n.id
    setTimeout(() => confirmDel.value === n.id && (confirmDel.value = null), 3500)
    return
  }
  confirmDel.value = null
  railError.value = ''
  try {
    await props.remove(n)
    live.value = '마크업을 지웠어요.'
  } catch (e) {
    railError.value = e.message || '지우지 못했어요.'
  }
}
function flash(id) {
  if (id == null) return
  flashId.value = id
  setTimeout(() => flashId.value === id && (flashId.value = null), 1600)
}
function cite(s, e) {
  emit('cite', citeRef(art.value, s, e))
}
function scrollToLines(r) {
  if (!r) return
  const el = view.value === 'lines'
    ? bodyEl.value?.querySelector(`[data-line="${r[0]}"]`)
    : leaves.find((x) => overlaps(blockRange(x), r[0], r[1]))
  el?.scrollIntoView({ block: 'center', behavior: reduced() ? 'auto' : 'smooth' })
}
function jump(n) {
  scrollToLines(n.range)
  flash(n.id)
}
function switchView(v) {
  if (view.value === v) return
  view.value = v
  clearSel()
  cursor.value = null
}
const lineTitle = (i) => {
  const { marks, check } = lineInfo.value[i]
  const t = [...marks.map((n) => `${MARK[n.kind]?.label} · ${n.text}`), ...(check ? [`확인 지점 · ${check.issue}`] : [])]
  return t.length ? t.join('\n') : undefined
}
const when = (t) => (t ? new Date(t).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : '')
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer" :duration="{ enter: 320, leave: 220 }">
      <div v-if="open && art" class="layer" @keydown="onPanelKey">
        <div class="scrim" aria-hidden="true" @click="close" />
        <section ref="panelEl" class="panel" role="dialog" aria-modal="true" :aria-labelledby="`art-t-${art.id}`">
          <header class="hd">
            <i class="kind" :class="art.kind">{{ KIND[art.kind]?.label || art.kind }}</i>
            <div class="ttl">
              <h2 :id="`art-t-${art.id}`">{{ art.title }}</h2>
              <small>{{ owner.emoji }} {{ owner.name }} · {{ art.status }}<template v-if="art.lang"> · {{ art.lang }}</template> · {{ lines.length }}줄</small>
            </div>
            <div v-if="art.kind !== 'code'" class="seg" role="group" aria-label="보기 방식">
              <button type="button" :class="{ on: view === 'read' }" :aria-pressed="view === 'read'" @click="switchView('read')">읽기</button>
              <button type="button" :class="{ on: view === 'lines' }" :aria-pressed="view === 'lines'" @click="switchView('lines')">줄 번호</button>
            </div>
            <button type="button" class="x" aria-label="닫기 (Esc)" @click="close">✕</button>
          </header>
          <p v-if="art.summary" class="summary">{{ art.summary }}</p>
          <p v-if="editable" class="hint">
            <b>마크업은 팀원(팀장·동료)도 볼 수 있어요.</b>
            줄을 누르면 선택, <kbd>Shift</kbd>+클릭으로 범위를 넓혀요. 문장을 드래그하면 그 부분을 인용해요. 키보드는 <kbd>↑</kbd><kbd>↓</kbd>·<kbd>Enter</kbd>.
          </p>

          <div class="content">
            <div
              ref="bodyEl"
              class="body"
              tabindex="0"
              :aria-label="editable ? `${art.title} 본문. 화살표로 줄을 고르고 Enter로 마크업을 남겨요` : `${art.title} 본문`"
              @keydown="onBodyKey"
              @mouseup="onUp"
            >
              <div v-if="view === 'lines'" class="numbered" :class="{ pick: editable }">
                <div class="numbered-in">
                  <div
                    v-for="(l, i) in lines"
                    :key="i"
                    class="ln"
                    :data-line="i + 1"
                    :data-no="i + 1"
                    :class="{
                      sel: within(selRange, i + 1),
                      cur: cursor === i + 1,
                      mk: lineInfo[i].marks.length,
                      hov: within(hoverRange, i + 1),
                      flash: flashId != null && lineInfo[i].marks.some((n) => n.id === flashId),
                      chk: lineInfo[i].check,
                      spotted: lineInfo[i].check?.spotted,
                    }"
                    :style="lineInfo[i].marks.length ? { '--mk': MARK[lineInfo[i].marks[0].kind]?.color } : null"
                    :title="lineTitle(i)"
                    @mousedown="onDown"
                    @click="onLineClick(i + 1, $event)"
                  >
                    <span class="gut" aria-hidden="true"><i v-for="n in lineInfo[i].marks.slice(0, 3)" :key="n.id" :style="{ background: MARK[n.kind]?.color }" /></span>
                    <code>{{ l }}</code>
                  </div>
                </div>
              </div>
              <div v-else ref="docEl" class="doc md" :class="{ pick: editable }" @mousedown="onDown" @click="onDocClick" v-html="html" />

              <Transition name="pop">
                <div v-if="editable && sel" ref="popEl" class="pop" role="group" aria-label="마크업 남기기" @mouseup.stop @click.stop>
                  <div class="pop-h">
                    <b>{{ rangeLabel(sel.start, sel.end) || '인용' }}</b>
                    <span v-if="sel.quote" class="q">“{{ sel.quote }}”</span>
                    <button type="button" class="x sm" aria-label="선택 취소" @click="clearSel">✕</button>
                  </div>
                  <div class="kinds" role="radiogroup" aria-label="마크업 종류">
                    <button
                      v-for="k in MARK_KINDS"
                      :key="k"
                      type="button"
                      role="radio"
                      :aria-checked="form.kind === k"
                      :class="{ on: form.kind === k }"
                      :style="{ '--c': MARK[k].color }"
                      @click="form.kind = k"
                    >{{ MARK[k].label }}</button>
                  </div>
                  <textarea ref="textEl" v-model="form.text" rows="3" maxlength="500" :placeholder="`${MARK[form.kind].label} 내용을 적어 주세요. 팀원도 이 코멘트를 봐요.`" @keydown="onFormKey" />
                  <div class="pop-f">
                    <small class="muted">{{ form.text.length }}/500 · <kbd>⌘/Ctrl</kbd>+<kbd>Enter</kbd></small>
                    <button v-if="canCite && sel.start" type="button" class="btn sm" @click="cite(sel.start, sel.end)">대화에 인용만</button>
                    <button type="button" class="btn sm primary" :disabled="!form.text.trim() || form.saving" @click="submit">{{ form.saving ? '남기는 중…' : '마크업 남기기' }}</button>
                  </div>
                  <p v-if="form.error" class="bad">{{ form.error }}</p>
                </div>
              </Transition>
            </div>

            <aside class="rail" aria-label="마크업 목록">
              <h3>마크업 <span class="n">{{ anns.length }}</span><small v-if="!checks">팀원도 볼 수 있어요</small></h3>
              <p v-if="railError" class="bad">{{ railError }}</p>
              <TransitionGroup tag="ul" name="mk" class="marks">
                <li
                  v-for="n in sorted"
                  :key="n.id"
                  :class="{ flash: flashId === n.id }"
                  :style="{ '--c': MARK[n.kind]?.color }"
                  @mouseenter="hover = n.id"
                  @mouseleave="hover = null"
                >
                  <button type="button" class="jump" :aria-label="`${anchorLabel(n)} ${MARK[n.kind]?.label} 위치로 이동`" @click="jump(n)" @focus="hover = n.id" @blur="hover = null">
                    <i class="k">{{ MARK[n.kind]?.label || n.kind }}</i>
                    <b>{{ anchorLabel(n) || '위치 없음' }}</b>
                    <small v-if="n.anchor.quote && n.anchor.lineStart" class="muted">“{{ n.anchor.quote.slice(0, 24) }}{{ n.anchor.quote.length > 24 ? '…' : '' }}”</small>
                  </button>
                  <p>{{ n.text }}</p>
                  <div class="acts">
                    <small class="muted">{{ when(n.createdAt) }}<template v-if="checks && n.msgIdx != null"> · 메시지 #{{ n.msgIdx }} 무렵</template></small>
                    <button v-if="canCite && n.range" type="button" class="btn link sm" @click="cite(n.range[0], n.range[1])">대화에 인용</button>
                    <button v-if="editable && remove" type="button" class="btn link sm del" :class="{ warn: confirmDel === n.id }" @click="del(n)">{{ confirmDel === n.id ? '한 번 더 누르면 지워져요' : '지우기' }}</button>
                  </div>
                </li>
              </TransitionGroup>
              <p v-if="!anns.length" class="empty">
                {{ editable ? '아직 남긴 마크업이 없어요. 본문에서 줄을 고르거나 문장을 드래그해 질문·우려·제안을 남겨 보세요.' : '지원자가 남긴 마크업이 없어요.' }}
              </p>

              <template v-if="checks">
                <h3 class="chk-h">심어 둔 확인 지점 <span class="n">{{ myChecks.filter((c) => c.spotted).length }}/{{ myChecks.length }}</span></h3>
                <p class="muted tiny">에이전트가 일부러 넣어 둔 문제예요. 마크업 줄 범위가 ±1줄 안에 들면 ‘발견’으로 셉니다.</p>
                <ul class="checks">
                  <li v-for="c in myChecks" :key="c.line">
                    <button type="button" class="jump" @click="scrollToLines([c.line, c.line])">
                      <span class="chip" :class="c.spotted ? 'green' : 'amber'">{{ c.spotted ? '발견' : '놓침' }}</span>
                      <b>L{{ c.line }}</b>
                    </button>
                    <p>{{ c.issue }}</p>
                  </li>
                </ul>
                <p v-if="!myChecks.length" class="empty">이 과제에는 확인 지점이 없어요.</p>
              </template>
            </aside>
          </div>
          <p class="sr" aria-live="polite">{{ live }}</p>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.layer { position: fixed; inset: 0; z-index: 50; display: flex; justify-content: flex-end; }
.scrim { position: absolute; inset: 0; background: rgba(15, 23, 42, 0.32); }
.panel { position: relative; width: min(1000px, 100vw); height: 100%; display: flex; flex-direction: column; background: var(--panel); border-left: 1px solid var(--line); box-shadow: -12px 0 40px rgba(15, 23, 42, 0.16); }
.drawer-enter-active .scrim, .drawer-leave-active .scrim { transition: opacity 0.22s ease; }
.drawer-enter-active .panel { transition: transform 0.32s cubic-bezier(0.2, 0.9, 0.3, 1); }
.drawer-leave-active .panel { transition: transform 0.22s ease-in; }
.drawer-enter-from .scrim, .drawer-leave-to .scrim { opacity: 0; }
.drawer-enter-from .panel, .drawer-leave-to .panel { transform: translateX(102%); }

.hd { display: flex; align-items: center; gap: 12px; padding: 14px 18px 10px; border-bottom: 1px solid var(--line); }
.ttl { flex: 1; min-width: 0; }
.ttl h2 { margin: 0; font-size: 17px; letter-spacing: -0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ttl small { color: var(--muted); font-size: 12.5px; }
.kind { font-style: normal; flex: none; font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 7px; }
.kind.design { background: color-mix(in srgb, #2563eb 14%, transparent); color: #3b82f6; }
.kind.result { background: color-mix(in srgb, #0d9488 16%, transparent); color: #14b8a6; }
.kind.code { background: color-mix(in srgb, #64748b 18%, transparent); color: var(--ink); }
.seg { display: flex; padding: 3px; border-radius: 9px; background: var(--bg); border: 1px solid var(--line); }
.seg button { border: 0; background: none; color: var(--muted); font-size: 12.5px; font-weight: 700; padding: 4px 10px; border-radius: 6px; transition: background 0.15s, color 0.15s; }
.seg button.on { background: var(--panel); color: var(--ink); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12); }
.x { flex: none; width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--line); background: var(--panel); color: var(--muted); font-size: 14px; }
.x:hover { color: var(--ink); border-color: var(--muted); }
.x.sm { width: 24px; height: 24px; font-size: 11px; margin-left: auto; }
.summary { margin: 10px 18px 0; font-size: 14px; }
.hint { margin: 8px 18px 0; padding: 8px 12px; border-radius: 10px; background: var(--brand-soft); font-size: 12.5px; line-height: 1.55; }
.hint b { color: var(--brand); margin-right: 4px; }
kbd { font-family: inherit; font-size: 11px; padding: 0 5px; border-radius: 4px; border: 1px solid var(--line); background: var(--panel); margin: 0 1px; }

.content { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 280px; margin-top: 10px; border-top: 1px solid var(--line); }
.body { position: relative; overflow: auto; padding: 14px 18px 18px; outline: none; }
.body:focus-visible { box-shadow: inset 0 0 0 2px var(--brand-soft); }

/* numbered source */
.numbered { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--bg); }
.numbered-in { display: inline-block; min-width: 100%; padding: 6px 0; }
.ln { display: flex; align-items: stretch; font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; font-size: 13px; line-height: 1.6; transition: background 0.15s; }
.ln::before { content: attr(data-no); flex: none; width: 44px; padding-right: 10px; text-align: right; color: var(--muted); opacity: 0.7; user-select: none; font-variant-numeric: tabular-nums; }
.gut { flex: none; width: 12px; display: flex; flex-direction: column; justify-content: center; gap: 2px; border-right: 1px solid var(--line); margin-right: 12px; }
.gut i { width: 6px; height: 6px; border-radius: 50%; }
.ln code { display: block; min-height: 1.6em; white-space: pre; padding-right: 18px; tab-size: 4; }
.numbered.pick .ln { cursor: pointer; }
.numbered.pick .ln:hover { background: color-mix(in srgb, var(--brand) 6%, transparent); }
.ln.mk { background: color-mix(in srgb, var(--mk) 11%, transparent); box-shadow: inset 3px 0 0 var(--mk); }
.ln.hov, .ln.flash { background: color-mix(in srgb, var(--mk, var(--brand)) 24%, transparent); }
.ln.sel { background: color-mix(in srgb, var(--brand) 20%, transparent); box-shadow: inset 3px 0 0 var(--brand); }
.ln.cur { outline: 1px dashed var(--brand); outline-offset: -1px; }
.ln.chk::before { content: '⚑ ' attr(data-no); color: #d97706; opacity: 1; font-weight: 700; }
.ln.chk.spotted::before { color: var(--ok); }
.ln.flash { animation: flash 1.4s ease; }

/* rendered markdown: block highlights */
.doc { font-size: 14.5px; line-height: 1.7; max-width: 72ch; }
.doc :deep([data-ls]) { border-radius: 6px; transition: background 0.15s, box-shadow 0.15s; }
.doc.pick :deep([data-ls]) { cursor: pointer; }
.doc.pick :deep([data-ls]:hover) { background: color-mix(in srgb, var(--brand) 6%, transparent); }
.doc :deep([data-mk]) { background: color-mix(in srgb, var(--mk, #2563eb) 11%, transparent); box-shadow: inset 3px 0 0 var(--mk, #2563eb); padding-left: 8px; }
.doc :deep([data-mk='question']) { --mk: #2563eb; }
.doc :deep([data-mk='risk']) { --mk: #d97706; }
.doc :deep([data-mk='suggest']) { --mk: #7c3aed; }
.doc :deep([data-mk='ok']) { --mk: #16a34a; }
.doc :deep(.is-hov), .doc :deep(.is-flash) { background: color-mix(in srgb, var(--mk, var(--brand)) 24%, transparent); }
.doc :deep(.is-sel) { background: color-mix(in srgb, var(--brand) 18%, transparent); box-shadow: inset 3px 0 0 var(--brand); padding-left: 8px; }
.doc :deep(.is-cur) { outline: 1px dashed var(--brand); outline-offset: 1px; }
.doc :deep(.is-chk) { outline: 1.5px dashed #d97706; outline-offset: 2px; }
.doc :deep(.is-chk.is-spotted) { outline-color: var(--ok); }
.doc :deep(.is-flash) { animation: flash 1.4s ease; }
.doc :deep(tr[data-mk] > :first-child) { box-shadow: inset 3px 0 0 var(--mk); }

/* markup popover */
.pop { position: sticky; bottom: 10px; margin-top: 14px; max-width: 580px; z-index: 3; padding: 12px; border-radius: 12px; background: var(--panel); border: 1.5px solid var(--brand); box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18); display: flex; flex-direction: column; gap: 8px; }
.pop-h { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 13px; }
.pop-h b { color: var(--brand); flex: none; }
.pop-h .q { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.kinds { display: flex; gap: 6px; flex-wrap: wrap; }
.kinds button { border: 1.5px solid var(--line); background: var(--panel); color: var(--ink); font-size: 12.5px; font-weight: 700; padding: 4px 12px; border-radius: 999px; transition: border-color 0.15s, background 0.15s, color 0.15s; }
.kinds button:hover { border-color: var(--c); }
.kinds button.on { border-color: var(--c); background: color-mix(in srgb, var(--c) 14%, transparent); color: var(--c); }
.pop textarea { width: 100%; resize: vertical; min-height: 64px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 9px; background: var(--panel); line-height: 1.55; }
.pop-f { display: flex; align-items: center; gap: 8px; }
.pop-f small { flex: 1; }
.bad { margin: 0; font-size: 12.5px; color: #dc2626; }
.pop-enter-active { transition: opacity 0.18s, transform 0.18s; }
.pop-leave-active { transition: opacity 0.12s; }
.pop-enter-from { opacity: 0; transform: translateY(6px); }
.pop-leave-to { opacity: 0; }

/* markup list */
.rail { overflow: auto; padding: 14px 16px 24px; border-left: 1px solid var(--line); background: color-mix(in srgb, var(--bg) 55%, var(--panel)); }
.rail h3 { display: flex; align-items: baseline; gap: 6px; margin: 0 0 10px; font-size: 14px; }
.rail h3 small { margin-left: auto; font-size: 11.5px; font-weight: 600; color: var(--muted); }
.rail .n { font-size: 12px; color: var(--brand); font-variant-numeric: tabular-nums; }
.chk-h { margin-top: 20px !important; }
.marks, .checks { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; position: relative; }
.marks li, .checks li { padding: 9px 11px; border-radius: 10px; background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--c, var(--line)); transition: box-shadow 0.2s, border-color 0.2s; }
.marks li:hover { box-shadow: 0 2px 10px rgba(15, 23, 42, 0.08); }
.marks li.flash { animation: flash 1.4s ease; }
.jump { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 0; border: 0; background: none; color: var(--ink); text-align: left; font-size: 12.5px; }
.jump b { font-variant-numeric: tabular-nums; }
.k { font-style: normal; font-size: 11px; font-weight: 800; padding: 1px 7px; border-radius: 999px; background: color-mix(in srgb, var(--c) 15%, transparent); color: var(--c); }
.marks p, .checks p { margin: 5px 0 0; font-size: 13.5px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.acts { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
.acts small { flex: 1; font-size: 11.5px; }
.btn.link.sm { padding: 0; font-size: 12px; }
.del { color: var(--muted) !important; }
.del.warn { color: #dc2626 !important; }
.empty { margin: 0; font-size: 13px; color: var(--muted); line-height: 1.6; }
.tiny { font-size: 12px; margin: -4px 0 10px; line-height: 1.5; }
.mk-enter-active { transition: opacity 0.3s, transform 0.3s; }
.mk-leave-active { transition: opacity 0.2s, transform 0.2s; position: absolute; left: 0; right: 0; }
.mk-enter-from { opacity: 0; transform: translateX(8px); }
.mk-leave-to { opacity: 0; transform: translateX(-8px); }
.mk-move { transition: transform 0.3s; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
@keyframes flash { 0%, 100% { box-shadow: none; } 30% { box-shadow: 0 0 0 3px color-mix(in srgb, var(--mk, var(--c, var(--brand))) 45%, transparent); } }

@media (max-width: 820px) {
  .content { display: flex; flex-direction: column; overflow: auto; }
  .body { overflow: visible; padding-bottom: 24px; }
  .rail { overflow: visible; border-left: 0; border-top: 1px solid var(--line); }
  .hd { flex-wrap: wrap; }
}
@media (prefers-reduced-motion: reduce) {
  .drawer-enter-active .panel, .drawer-leave-active .panel { transition: none; }
  .ln.flash, .doc :deep(.is-flash), .marks li.flash { animation: none; }
  .mk-enter-active, .mk-leave-active, .mk-move, .pop-enter-active { transition: none; }
}
</style>
