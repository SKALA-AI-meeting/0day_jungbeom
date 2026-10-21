<script setup>
// Milestone checkpoints. Reached steps open one by one: the current one keeps pulsing, the next shows as a faint preview,
// later ones stay folded until reached. Passing a step draws its check (CheckMark).
import { computed } from 'vue'
import CheckMark from './CheckMark.vue'

const props = defineProps({ milestones: Array, current: Number, done: Boolean })

// checks already passed when the page opens draw one after another; a step passed later draws at once
const passedAtLoad = props.done ? props.milestones.length : props.current
const delay = (i) => (i < passedAtLoad ? i * 0.18 : 0)

const state = (i) => (props.done || i < props.current ? 'past' : i === props.current ? 'now' : i === props.current + 1 ? 'next' : 'later')
const shown = computed(() => (props.milestones || []).map((m, i) => ({ ...m, i, state: state(i) })).filter((s) => s.state !== 'later'))
const later = computed(() => (props.milestones || []).filter((_, i) => state(i) === 'later').length)
const reached = computed(() => (props.done ? props.milestones.length : Math.min(props.current + 1, props.milestones.length)))
</script>

<template>
  <div class="stepper">
    <div class="meter" role="progressbar" :aria-valuenow="reached" aria-valuemin="0" :aria-valuemax="milestones.length" :aria-label="`진행 단계 ${reached}/${milestones.length}`">
      <i v-for="(m, i) in milestones" :key="m.key" :class="state(i)" />
    </div>
    <TransitionGroup tag="ol" name="ms" class="steps">
      <li v-for="s in shown" :key="s.key" :class="s.state" :aria-current="s.state === 'now' ? 'step' : undefined">
        <span class="mark">
          <CheckMark v-if="s.state === 'past'" :size="28" :delay="delay(s.i)" />
          <span v-else class="ring"><b>{{ s.i + 1 }}</b></span>
        </span>
        <div class="txt">
          <b>{{ s.label }}<em v-if="s.state === 'now'">지금</em><em v-else-if="s.state === 'next'" class="soft">다음</em></b>
          <small v-if="s.state !== 'next'">{{ s.desc }}</small>
        </div>
      </li>
    </TransitionGroup>
    <Transition name="fade">
      <p v-if="later" class="later"><i v-for="n in later" :key="n" />이후 단계는 대화가 이어지면 열려요</p>
    </Transition>
  </div>
</template>

<style scoped>
.meter { display: flex; gap: 4px; margin: -2px 0 12px; }
.meter i { flex: 1; height: 4px; border-radius: 2px; background: var(--line); transition: background 0.5s ease; }
.meter i.past { background: var(--ok); }
.meter i.now { background: var(--brand); animation: glow 1.6s ease-in-out infinite; }
.steps { list-style: none; margin: 0; padding: 0; position: relative; }
.steps li { display: flex; gap: 12px; padding: 8px 0 12px; position: relative; color: var(--muted); transition: color 0.4s, opacity 0.4s; }
/* the rail between two steps: solid once passed, dashed towards the preview */
.steps li:not(:last-child)::after { content: ''; position: absolute; left: 13px; top: 40px; bottom: -6px; width: 2px; border-radius: 1px; background: var(--line); transform-origin: top; transition: background 0.5s; }
.steps li.past:not(:last-child)::after { background: var(--ok); animation: grow 0.5s ease-out both; }
.steps li.now:not(:last-child)::after { background: repeating-linear-gradient(to bottom, var(--brand) 0 4px, transparent 4px 8px); opacity: 0.5; }
.mark { width: 28px; height: 28px; flex: none; display: grid; place-items: center; z-index: 1; }
.ring { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); font-size: 13px; transition: border-color 0.4s, color 0.4s; }
.now .ring { border-color: var(--brand); color: var(--brand); animation: beat 1.6s ease-in-out infinite; }
.next .ring { border-style: dashed; opacity: 0.7; }
.now { color: var(--ink); }
.next { opacity: 0.55; }
.txt { display: flex; flex-direction: column; gap: 2px; line-height: 1.35; padding-top: 4px; min-width: 0; }
.txt b { display: flex; align-items: center; gap: 6px; font-size: 14.5px; }
.txt em { font-style: normal; font-size: 11px; font-weight: 700; padding: 1px 7px; border-radius: 999px; background: var(--brand-soft); color: var(--brand); }
.txt em.soft { background: var(--line); color: var(--muted); }
.txt small { font-size: 12.5px; color: var(--muted); }
.now .txt small { color: var(--ink); opacity: 0.8; }
.later { display: flex; align-items: center; gap: 4px; margin: 2px 0 0 9px; font-size: 12px; color: var(--muted); }
.later i { width: 6px; height: 6px; border-radius: 50%; background: var(--line); margin-right: 2px; }
.later i:last-of-type { margin-right: 10px; }
.ms-enter-active { transition: opacity 0.5s ease, transform 0.5s cubic-bezier(0.2, 0.9, 0.3, 1), filter 0.5s; }
.ms-enter-from { opacity: 0; transform: translateY(-8px); filter: blur(3px); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@keyframes beat {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--brand) 45%, transparent); border-color: var(--brand); }
  50% { box-shadow: 0 0 0 7px transparent; border-color: color-mix(in srgb, var(--brand) 45%, var(--panel)); }
}
@keyframes glow { 50% { opacity: 0.45; } }
@keyframes grow { from { transform: scaleY(0); } }
@media (prefers-reduced-motion: reduce) {
  .now .ring, .meter i.now, .steps li.past::after { animation: none; }
  .ms-enter-active { transition: opacity 0.2s; }
  .ms-enter-from { transform: none; filter: none; }
}
</style>
