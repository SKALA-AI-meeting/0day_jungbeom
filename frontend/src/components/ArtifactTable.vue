<script setup>
// "같이 확인할 과제": the design doc, result table and code the team looks at together. A row opens the viewer.
// The table follows its own width (container query): in a narrow column, owner and status fold under the title.
import { KIND, ownerOf } from '../utils/artifacts'

defineProps({
  artifacts: { type: Array, required: true }, // normArtifacts()
  personas: { type: Object, default: () => ({}) }, // id -> { name, emoji }
  checks: { type: Array, default: null }, // admin: normCheck() list -> "확인 지점" column
  active: { type: String, default: null }, // id of the artifact open in the viewer
})
const emit = defineEmits(['open'])
const owner = ownerOf
const spotted = (checks, id) => {
  const mine = checks.filter((c) => c.artifactId === id)
  return mine.length ? `${mine.filter((c) => c.spotted).length}/${mine.length}` : '–'
}
</script>

<template>
  <div class="box">
    <table class="tbl">
      <thead>
        <tr>
          <th class="c-kind">종류</th><th>과제</th><th class="c-own wide">담당</th><th class="c-st wide">상태</th>
          <th class="c-n" title="지원자가 남긴 마크업">마크업</th><th v-if="checks" class="c-chk" title="심어 둔 확인 지점 중 지원자가 표시한 수">확인 지점</th>
        </tr>
      </thead>
      <TransitionGroup tag="tbody" name="row" appear>
        <tr v-for="(a, i) in artifacts" :key="a.id" :class="{ on: active === a.id }" :style="{ '--i': i }" @click="emit('open', a)">
          <td><i class="kind" :class="a.kind">{{ KIND[a.kind]?.label || a.kind }}</i></td>
          <td class="ttl">
            <button type="button" class="open" :aria-label="`${a.title} 열기`" @click.stop="emit('open', a)">{{ a.title }}</button>
            <small>{{ a.summary }}</small>
            <small class="narrow">{{ owner(personas, a.owner).emoji }} {{ owner(personas, a.owner).name }} · {{ a.status }}</small>
          </td>
          <td class="own wide" :title="owner(personas, a.owner).name"><em>{{ owner(personas, a.owner).emoji }}</em> {{ owner(personas, a.owner).name }}</td>
          <td class="wide"><i class="st" :title="a.status">{{ a.status }}</i></td>
          <td class="cnt" :class="{ has: a.annotations.length }">{{ a.annotations.length }}</td>
          <td v-if="checks" class="cnt">{{ spotted(checks, a.id) }}</td>
        </tr>
      </TransitionGroup>
    </table>
  </div>
</template>

<style scoped>
.box { container-type: inline-size; }
.tbl { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 13.5px; }
.c-kind { width: 76px; }
.c-own { width: 92px; }
.c-st { width: 72px; }
.c-n { width: 50px; }
.c-chk { width: 66px; }
th { font-size: 11.5px; font-weight: 700; color: var(--muted); text-align: left; padding: 0 6px 6px; white-space: nowrap; }
th.c-n, th.c-chk { text-align: center; }
td { padding: 9px 6px; border-top: 1px solid var(--line); vertical-align: middle; }
tbody tr { cursor: pointer; transition: background 0.15s, box-shadow 0.2s; }
tbody tr:hover { background: var(--bg); }
tbody tr.on { background: var(--brand-soft); box-shadow: inset 3px 0 0 var(--brand); }
.kind { font-style: normal; display: inline-block; font-size: 11.5px; font-weight: 700; padding: 2px 7px; border-radius: 6px; white-space: nowrap; }
.kind.design { background: color-mix(in srgb, #2563eb 14%, transparent); color: #3b82f6; }
.kind.result { background: color-mix(in srgb, #0d9488 16%, transparent); color: #14b8a6; }
.kind.code { background: color-mix(in srgb, #64748b 18%, transparent); color: var(--ink); }
.ttl { line-height: 1.35; }
.open { display: block; max-width: 100%; padding: 0; border: 0; background: none; color: var(--ink); font-weight: 650; text-align: left; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
tr:hover .open { color: var(--brand); }
.ttl small { display: block; color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ttl small.narrow { display: none; }
.own { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; }
.own em { font-style: normal; }
.st { font-style: normal; display: inline-block; max-width: 100%; font-size: 11.5px; color: var(--muted); border: 1px solid var(--line); padding: 1px 6px; border-radius: 999px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: middle; }
.cnt { text-align: center; font-weight: 700; color: var(--muted); font-variant-numeric: tabular-nums; }
.cnt.has { color: var(--brand); }
@container (max-width: 430px) {
  .wide { display: none; }
  .ttl small.narrow { display: block; }
}
.row-enter-active { transition: opacity 0.35s ease calc(var(--i) * 60ms), transform 0.35s ease calc(var(--i) * 60ms); }
.row-enter-from { opacity: 0; transform: translateY(4px); }
@media (prefers-reduced-motion: reduce) { .row-enter-active { transition: none; } }
</style>
