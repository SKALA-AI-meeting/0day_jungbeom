<script setup>
// Report charts rendered by analytics-mcp (render_charts): thumbnails that open larger in an overlay.
// The SVG is shown only through <img src="data:image/svg+xml;…"> (utils/charts.svgSrc), never inserted as HTML.
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { svgSrc } from '../utils/charts'
// The overlay is modal (aria-modal): while it is open, Escape closes it and focus stays on its close button, wherever
// the pointer clicked (keys and focus are watched on the document, not only inside the dialog).

const props = defineProps({
  charts: { type: Array, default: () => [] }, // [{ chart_id, title, svg, caption? }]
  compact: Boolean, // small thumbnails (inbox)
})

const list = computed(() =>
  (props.charts || [])
    .filter((c) => typeof c?.svg === 'string' && c.svg.trim())
    .map((c, i) => ({ key: c.chart_id || c.id || `c${i}`, title: c.title || '차트', caption: c.caption || '', src: svgSrc(c.svg) })),
)

const open = ref(null)
const box = ref(null)
let opener = null
const focusClose = () => box.value?.querySelector('.x')?.focus({ preventScroll: true })
function show(c, e) {
  opener = e?.currentTarget || document.activeElement
  open.value = c
  document.documentElement.style.overflow = 'hidden'
  document.addEventListener('keydown', onKey, true)
  document.addEventListener('focusin', onFocusIn, true)
  nextTick(focusClose)
}
function release() {
  document.removeEventListener('keydown', onKey, true)
  document.removeEventListener('focusin', onFocusIn, true)
  document.documentElement.style.overflow = ''
}
function close() {
  if (!open.value) return
  open.value = null
  release()
  opener?.focus?.({ preventScroll: true })
}
function onKey(e) {
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close() }
  else if (e.key === 'Tab') { e.preventDefault(); focusClose() } // the close button is the only stop
}
function onFocusIn(e) {
  if (!box.value?.contains(e.target)) focusClose() // focus never lands behind the scrim
}
onBeforeUnmount(() => { if (open.value) release() })
</script>

<template>
  <ul v-if="list.length" class="charts" :class="{ compact }">
    <li v-for="c in list" :key="c.key">
      <button type="button" class="thumb" :aria-label="`${c.title} 크게 보기`" @click="show(c, $event)">
        <span class="paper"><img :src="c.src" :alt="c.title" loading="lazy" decoding="async" /></span>
        <span class="cap"><b>{{ c.title }}</b><small v-if="c.caption && !compact">{{ c.caption }}</small></span>
      </button>
    </li>
  </ul>
  <Teleport to="body">
    <Transition name="lb">
      <div v-if="open" class="lb">
        <div class="scrim" aria-hidden="true" @click="close" />
        <figure ref="box" class="box" role="dialog" aria-modal="true" :aria-label="open.title" tabindex="-1">
          <header>
            <b>{{ open.title }}</b>
            <button type="button" class="x" aria-label="닫기" @click="close">✕</button>
          </header>
          <div class="paper big"><img :src="open.src" :alt="open.title" /></div>
          <figcaption v-if="open.caption" class="muted small">{{ open.caption }}</figcaption>
        </figure>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.charts { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.charts.compact { grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); gap: 8px; }
.thumb { width: 100%; height: 100%; display: flex; flex-direction: column; gap: 6px; padding: 6px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); color: var(--ink); text-align: left; transition: border-color 0.15s, box-shadow 0.15s; }
.thumb:hover { border-color: var(--brand); }
.thumb:focus-visible { outline: none; border-color: var(--brand); box-shadow: 0 0 0 3px var(--brand-soft); }
/* the charts are drawn for white paper (a print-like report), so they keep a white sheet in dark mode too */
.paper { display: grid; place-items: center; background: #fff; border-radius: 6px; overflow: hidden; }
.thumb .paper { aspect-ratio: 16 / 10; }
.thumb img { width: 100%; height: 100%; object-fit: contain; display: block; }
.cap { display: flex; flex-direction: column; font-size: 12.5px; line-height: 1.35; min-width: 0; padding: 0 2px; }
.cap b { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cap small { color: var(--muted); font-size: 12px; }
.compact .cap { font-size: 12px; }

.lb { position: fixed; inset: 0; z-index: 60; display: grid; grid-template-columns: minmax(0, 1fr); place-items: center; padding: 24px 16px; }
.scrim { position: absolute; inset: 0; background: rgba(15, 23, 42, 0.55); }
.box { position: relative; margin: 0; width: min(800px, 100%); max-height: calc(100vh - 48px); display: flex; flex-direction: column; gap: 10px; padding: 14px 16px 16px; background: var(--panel); color: var(--ink); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: 0 20px 50px rgba(15, 23, 42, 0.28); }
.box header { display: flex; align-items: center; gap: 10px; }
.box header b { flex: 1; min-width: 0; }
.x { flex: none; width: 32px; height: 32px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); color: var(--ink); }
.x:hover { border-color: var(--brand); color: var(--brand); }
.x:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.box:focus { outline: none; }
.big { padding: 12px; overflow: auto; min-height: 0; min-width: 0; }
.big img { width: 100%; height: auto; max-height: calc(100vh - 180px); object-fit: contain; display: block; }
/* on a phone the 720 px chart would shrink to ~5 px labels: keep it readable and let the sheet scroll sideways */
@media (max-width: 640px) {
  .big { place-items: start; }
  .big img { width: 600px; max-width: none; max-height: none; }
}
.box figcaption { margin: 0; }
.lb-enter-active, .lb-leave-active { transition: opacity 0.18s ease; }
.lb-enter-from, .lb-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .thumb, .lb-enter-active, .lb-leave-active { transition: none; } }
</style>
