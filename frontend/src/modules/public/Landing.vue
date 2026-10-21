<script setup>
import { RouterLink } from 'vue-router'
import { auth } from '../../api'

const FLOW = [
  { n: 1, t: '가입', d: '초대 링크에서 계정을 만들어요' },
  { n: 2, t: '계정 확인', d: '에이전트가 가입 요건과 입력값을 점검해요. 애매하면 담당자가 결정해요' },
  { n: 3, t: '3자 대화', d: 'AI 팀원 두 명과 소통 → 조율 → 타협 → 설득' },
  { n: 4, t: '리포트 승인', d: '에이전트가 정리한 관찰 근거를 담당자가 확인하고 공개해요' },
]
</script>

<template>
  <main class="page">
    <section class="hero">
      <h1>AI 팀원과 함께하는 첫 출근</h1>
      <p class="sub">진행 중인 프로젝트에 합류해 AI 팀원 두 명과 일을 풀어 가는 협업 평가예요. 정답은 없고, 평소 하던 대로 대화하면 돼요.</p>
    </section>

    <section class="roles">
      <article class="card role">
        <span class="tag">지원자</span>
        <h2>평가에 참여해요</h2>
        <p class="muted">채용 담당자가 보낸 초대 링크로 가입하고, 계정 확인이 끝나면 바로 대화방에 들어가요.</p>
        <div class="acts">
          <RouterLink v-if="auth.state.candidate" to="/me" class="btn primary">내 평가로 가기</RouterLink>
          <template v-else>
            <RouterLink to="/join/demo" class="btn primary">데모 초대로 가입</RouterLink>
            <RouterLink to="/login" class="btn">로그인</RouterLink>
          </template>
        </div>
      </article>
      <article class="card role">
        <span class="tag admin">채용 담당자</span>
        <h2>결정하고 확인해요</h2>
        <p class="muted">에이전트가 사람의 확인을 요청한 항목부터 처리하고, 지원자별 관찰 근거와 리포트를 봐요.</p>
        <div class="acts">
          <RouterLink v-if="auth.state.admin" to="/admin/inbox" class="btn primary">관리자 화면으로</RouterLink>
          <template v-else>
            <RouterLink to="/admin/login" class="btn primary">로그인</RouterLink>
            <RouterLink to="/admin/signup" class="btn">기업 계정 만들기</RouterLink>
          </template>
        </div>
      </article>
    </section>

    <ol class="flow">
      <li v-for="f in FLOW" :key="f.n" :style="{ animationDelay: `${f.n * 70}ms` }">
        <b>{{ f.n }}</b>
        <div><strong>{{ f.t }}</strong><small>{{ f.d }}</small></div>
      </li>
    </ol>
  </main>
</template>

<style scoped>
.hero { margin: 12px 0 22px; }
.hero h1 { font-size: 30px; }
.roles { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.role { display: flex; flex-direction: column; gap: 6px; }
.role h2 { margin: 6px 0 0; font-size: 20px; }
.role p { margin: 0 0 8px; }
.tag { align-self: flex-start; font-size: 12px; font-weight: 800; color: var(--brand); background: var(--brand-soft); padding: 2px 10px; border-radius: 999px; }
.tag.admin { color: #92400e; background: #fef3c7; }
.acts { display: flex; gap: 8px; margin-top: auto; }
.acts .btn:hover { text-decoration: none; }
.flow { list-style: none; padding: 0; margin: 26px 0 0; display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; counter-reset: f; }
.flow li { display: flex; gap: 10px; padding: 14px; border-radius: 12px; background: var(--panel); border: 1px solid var(--line); opacity: 0; animation: rise 0.4s ease forwards; }
.flow b { width: 26px; height: 26px; flex: none; display: grid; place-items: center; border-radius: 50%; background: var(--brand); color: #fff; font-size: 13px; }
.flow div { display: flex; flex-direction: column; line-height: 1.35; }
.flow small { color: var(--muted); font-size: 12px; margin-top: 2px; }
@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .flow li { animation: none; opacity: 1; } }
@media (max-width: 800px) { .roles, .flow { grid-template-columns: 1fr; } }
</style>
