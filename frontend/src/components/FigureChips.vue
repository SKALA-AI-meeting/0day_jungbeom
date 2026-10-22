<script setup>
// The compact numbers of an analytics snapshot (api-contract §5 `figures`): counts and agreement, never a score.
import { computed } from 'vue'
import { MODE_LABEL, SIGNAL, kappaWord } from '../constants'

const props = defineProps({
  figures: Object, // { messages, candidate_messages, observations, by_signal, pooled_kappa, kappa_n, tki_estimate, checkpoints, milestones_reached }
  compact: Boolean,
})
// Below this many (message x competency) judgements κ is shown with its sample size and no Landis–Koch word:
// with one or two candidate messages κ = 1 says little about agreement.
const KAPPA_MIN_N = 20

function kappa(f) {
  const n = f.kappa_n
  const value = f.pooled_kappa == null ? '–' : n != null ? `${f.pooled_kappa} · ${n}건` : f.pooled_kappa
  const few = f.pooled_kappa != null && n != null && n < KAPPA_MIN_N
  return { value, hint: few ? '표본 적음' : kappaWord(f.pooled_kappa), few }
}

const items = computed(() => {
  const f = props.figures || {}
  const out = []
  if (f.messages != null) out.push({ k: 'msg', label: '메시지', value: f.candidate_messages != null ? `${f.messages} · 지원자 ${f.candidate_messages}` : f.messages })
  if (f.observations != null) out.push({ k: 'obs', label: '관찰 근거', value: `${f.observations}건`, signals: f.by_signal || null })
  if (f.milestones_reached) out.push({ k: 'ms', label: '도달 단계', value: f.milestones_reached })
  if (f.checkpoints) out.push({ k: 'chk', label: '확인 지점 발견', value: f.checkpoints })
  if ('pooled_kappa' in f) out.push({ k: 'kappa', label: '관찰기↔디텍터 κ', ...kappa(f) })
  if (f.tki_estimate) out.push({ k: 'tki', label: '성향 추정', value: MODE_LABEL[f.tki_estimate] || f.tki_estimate })
  return out
})
</script>

<template>
  <ul v-if="items.length" class="figs" :class="{ compact }" aria-label="핵심 수치">
    <li v-for="x in items" :key="x.k">
      <small>{{ x.label }}</small>
      <b>{{ x.value }}</b>
      <span v-if="x.hint && (!compact || x.few)" class="hint" :class="{ few: x.few }">{{ x.hint }}</span>
      <span v-if="x.signals" class="sig">
        <span v-for="(s, key) in SIGNAL" :key="key" :title="s.label"><i :style="{ background: s.color }" aria-hidden="true" />{{ x.signals[key] ?? 0 }}<span class="sr">{{ s.label }}</span></span>
      </span>
    </li>
  </ul>
</template>

<style scoped>
.figs { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 8px; }
.figs li { display: inline-flex; align-items: baseline; gap: 6px; padding: 5px 10px; border-radius: 10px; border: 1px solid var(--line); background: var(--panel); font-size: 13px; }
.figs small { color: var(--muted); font-size: 12px; }
.hint { color: var(--muted); font-size: 12px; }
.hint.few { color: #b45309; }
.sig { display: inline-flex; gap: 7px; font-size: 12px; color: var(--muted); }
.sig > span { display: inline-flex; align-items: center; gap: 3px; }
.sig i { display: inline-block; width: 7px; height: 7px; border-radius: 50%; }
.compact { gap: 6px; }
.compact li { padding: 2px 9px; border-radius: 999px; font-size: 12px; }
.compact small { font-size: 11.5px; }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }
</style>
