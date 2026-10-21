<script setup>
// A check that draws itself once (stroke-dashoffset). Shared by stage checklists and the milestone stepper.
// `delay` (s) staggers several checks that mount together, e.g. the steps already passed when a session reloads.
defineProps({ size: { type: Number, default: 22 }, tone: { type: String, default: 'ok' }, delay: { type: Number, default: 0 } })
</script>

<template>
  <svg class="ck" :class="tone" :width="size" :height="size" viewBox="0 0 24 24" aria-hidden="true" :style="{ '--ck-delay': `${delay}s` }">
    <circle class="disc" cx="12" cy="12" r="11" />
    <path class="tick" d="M6.5 12.5l3.6 3.6L17.6 8.6" pathLength="1" />
  </svg>
</template>

<style scoped>
.ck { flex: none; display: block; }
.disc { fill: var(--ok); transform-origin: center; animation: pop 0.32s var(--ck-delay, 0s) cubic-bezier(0.3, 1.6, 0.6, 1) both; }
.ck.brand .disc { fill: var(--brand); }
.tick { fill: none; stroke: #fff; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; stroke-dasharray: 1; stroke-dashoffset: 1; animation: draw 0.42s calc(var(--ck-delay, 0s) + 0.16s) ease-out forwards; }
@keyframes pop { from { transform: scale(0.4); opacity: 0; } to { transform: scale(1); opacity: 1; } }
@keyframes draw { to { stroke-dashoffset: 0; } }
@media (prefers-reduced-motion: reduce) { .disc, .tick { animation: none; stroke-dashoffset: 0; } }
</style>
