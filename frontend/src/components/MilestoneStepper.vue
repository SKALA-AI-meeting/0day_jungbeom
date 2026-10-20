<script setup>
defineProps({ milestones: Array, current: Number, done: Boolean })
</script>

<template>
  <ol class="steps">
    <li v-for="(m, i) in milestones" :key="m.key" :class="{ now: i === current && !done, past: i < current || done }">
      <span class="n">{{ i < current || done ? '✓' : i + 1 }}</span>
      <div><b>{{ m.label }}</b><small>{{ m.desc }}</small></div>
    </li>
  </ol>
</template>

<style scoped>
.steps { list-style: none; margin: 0; padding: 0; position: relative; }
.steps li { display: flex; gap: 12px; padding: 10px 0; position: relative; color: var(--muted); }
.steps li:not(:last-child)::after { content: ''; position: absolute; left: 13px; top: 38px; bottom: -6px; width: 2px; background: var(--line); }
.steps li.past:not(:last-child)::after { background: var(--ok); }
.n { width: 28px; height: 28px; flex: none; display: grid; place-items: center; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); font-size: 13px; font-weight: 700; z-index: 1; }
.past .n { background: var(--ok); border-color: var(--ok); color: #fff; }
.now .n { border-color: var(--brand); color: var(--brand); box-shadow: 0 0 0 4px var(--brand-soft); }
.now { color: var(--ink); }
div { display: flex; flex-direction: column; line-height: 1.3; }
small { font-size: 12px; color: var(--muted); }
</style>
