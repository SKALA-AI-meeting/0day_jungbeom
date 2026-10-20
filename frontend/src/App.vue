<script setup>
import { RouterLink, RouterView, useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <header class="topbar">
    <RouterLink to="/" class="brand">Day&nbsp;Zero <span>협업 대화 관찰</span></RouterLink>
    <nav>
      <RouterLink to="/">지원자</RouterLink>
      <RouterLink to="/admin" :class="{ 'router-link-active': route.path.startsWith('/admin') }">관리자</RouterLink>
    </nav>
  </header>
  <RouterView />
</template>
