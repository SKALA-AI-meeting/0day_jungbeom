<script setup>
import { computed } from 'vue'
import { COMP_COLOR } from '../constants'
import { renderMarkdown } from '../utils/markdown'

const props = defineProps({
  message: Object,
  who: Object, // { name, emoji, role }
  mine: Boolean,
  highlight: Boolean,
  badges: { type: Array, default: () => [] }, // competency ids observed on this message (admin only)
  tag: { type: String, default: '' }, // e.g. the option chosen with this message
  sources: { type: Array, default: () => [] }, // company documents the persona cited (rag-mcp)
})
// Markdown + LaTeX; a half-streamed line (open `$`, `**`, fence) simply shows as text until it closes.
const html = computed(() => renderMarkdown(props.message.text))
</script>

<template>
  <div class="row" :class="{ mine, hl: highlight }">
    <span v-if="!mine" class="av">{{ who?.emoji }}</span>
    <div class="body">
      <div class="meta">
        <b>{{ who?.name }}</b><span v-if="who?.role" class="role">{{ who.role }}</span>
        <span v-for="c in badges" :key="c" class="dot" :style="{ background: COMP_COLOR[c].fg }" :title="c">{{ c }}</span>
      </div>
      <div v-if="tag" class="tag">✔ 선택: {{ tag }}</div>
      <div class="bubble md" :class="{ live: message.live }" v-html="html" />
      <div v-if="sources.length" class="src">근거 · <span v-for="(s, i) in sources" :key="i">{{ s.doc }}<template v-if="s.section"> {{ s.section }}</template><template v-if="i < sources.length - 1">, </template></span></div>
    </div>
  </div>
</template>

<style scoped>
.row { display: flex; gap: 10px; margin: 12px 0; align-items: flex-start; border-radius: 12px; transition: background 0.4s; padding: 2px; }
.row.mine { flex-direction: row-reverse; }
.row.hl { background: #fef08a55; outline: 2px solid #facc15; }
.av { width: 36px; height: 36px; flex: none; display: grid; place-items: center; border-radius: 50%; background: var(--line); font-size: 19px; }
.body { max-width: 82%; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.row.mine .body { align-items: flex-end; }
.meta { font-size: 12px; color: var(--muted); display: flex; gap: 6px; align-items: center; }
.meta b { color: var(--ink); }
.dot { color: #fff; font-size: 10px; font-weight: 800; padding: 0 6px; border-radius: 999px; line-height: 16px; }
.bubble { padding: 10px 14px; border-radius: 14px; background: var(--panel); border: 1px solid var(--line); word-break: keep-all; overflow-wrap: anywhere; max-width: 100%; min-width: 0; line-height: 1.6; }
.bubble.live > :deep(:last-child)::after { content: ''; display: inline-block; width: 7px; height: 1.05em; margin-left: 3px; vertical-align: -0.15em; border-radius: 1px; background: currentColor; opacity: 0.5; animation: caret 1s steps(1) infinite; }
.tag { font-size: 12px; font-weight: 700; color: var(--brand); background: var(--brand-soft); padding: 4px 10px; border-radius: 8px; max-width: 100%; }
.src { font-size: 11.5px; color: var(--muted); padding-left: 4px; }
.row.mine .bubble { background: var(--brand); color: #fff; border-color: var(--brand); }
.row.mine .bubble :deep(a) { color: #fff; text-decoration: underline; }
.row.mine .bubble :deep(code) { background: rgba(255, 255, 255, 0.18); color: #fff; }
.row.mine .bubble :deep(blockquote) { border-left-color: rgba(255, 255, 255, 0.5); color: rgba(255, 255, 255, 0.85); }
@keyframes caret { 50% { opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .bubble.live > :deep(:last-child)::after { animation: none; } }
</style>
