<script setup>
// Vertical checklist of agent stages. Steps appear as they arrive; running pulses, done draws its check.
import CheckMark from './CheckMark.vue'

defineProps({
  steps: { type: Array, required: true }, // [{ key, label, status: pending|running|waiting|done|failed|skipped, detail? }]
  compact: Boolean,
})
</script>

<template>
  <TransitionGroup tag="ol" name="step" class="stages" :class="{ compact }">
    <li v-for="s in steps" :key="s.key" :class="s.status">
      <span class="dot">
        <CheckMark v-if="s.status === 'done'" :size="compact ? 18 : 22" />
        <span v-else-if="s.status === 'failed'" class="x">!</span>
        <span v-else class="ring" />
      </span>
      <div class="txt">
        <b>{{ s.label }}</b>
        <small v-if="s.detail">{{ s.detail }}</small>
        <small v-else-if="s.status === 'running'">진행 중…</small>
        <small v-else-if="s.status === 'waiting'">기다리는 중</small>
        <small v-else-if="s.status === 'skipped'">건너뜀</small>
      </div>
    </li>
  </TransitionGroup>
</template>

<style scoped>
.stages { list-style: none; margin: 0; padding: 0; position: relative; }
.stages li { display: flex; gap: 12px; padding: 9px 0; position: relative; color: var(--muted); transition: color 0.3s; }
.stages li:not(:last-child)::after { content: ''; position: absolute; left: 10px; top: 36px; bottom: -4px; width: 2px; background: var(--line); transition: background 0.4s; }
.stages li.done:not(:last-child)::after { background: var(--ok); }
.compact li { padding: 5px 0; }
.compact li:not(:last-child)::after { left: 8px; top: 27px; }
.dot { width: 22px; height: 22px; flex: none; display: grid; place-items: center; z-index: 1; }
.compact .dot { width: 18px; height: 18px; }
.ring { width: 100%; height: 100%; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); }
.running .ring { border-color: var(--brand); animation: beat 1.2s ease-in-out infinite; }
.skipped .ring { border-style: dotted; opacity: 0.6; }
.skipped b { font-weight: 500; text-decoration: line-through; text-decoration-color: var(--line); }
.waiting .ring { border-color: var(--warn); border-style: dashed; animation: spin 3s linear infinite; }
.x { width: 100%; height: 100%; border-radius: 50%; background: #dc2626; color: #fff; font-weight: 800; font-size: 12px; display: grid; place-items: center; }
.running, .waiting, .done { color: var(--ink); }
.failed { color: #b91c1c; }
.txt { display: flex; flex-direction: column; line-height: 1.35; min-width: 0; }
.txt small { font-size: 12px; color: var(--muted); }
@keyframes beat { 0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--brand) 45%, transparent); } 50% { box-shadow: 0 0 0 6px transparent; } }
@keyframes spin { to { transform: rotate(360deg); } }
.step-enter-active { transition: opacity 0.35s ease, transform 0.35s ease; }
.step-enter-from { opacity: 0; transform: translateY(-6px); }
@media (prefers-reduced-motion: reduce) { .running .ring, .skipped .ring { border-style: dotted; opacity: 0.6; }
.skipped b { font-weight: 500; text-decoration: line-through; text-decoration-color: var(--line); }
.waiting .ring { animation: none; } .step-enter-active { transition: none; } }
</style>
