// Competency / signal visual language shared by candidate and admin screens.
export const COMP_COLOR = {
  C01: { fg: '#2563eb', bg: '#dbeafe' },
  C02: { fg: '#7c3aed', bg: '#ede9fe' },
  C03: { fg: '#0d9488', bg: '#ccfbf1' },
  C05: { fg: '#ea580c', bg: '#ffedd5' },
}
export const SIGNAL = {
  positive: { label: '도움이 되는 행동', color: '#16a34a' },
  neutral: { label: '관찰', color: '#94a3b8' },
  risk: { label: '면접 확인 필요', color: '#d97706' },
}
export const SPEAKER_COLOR = { user: '#2563eb', lead: '#0f766e', peer: '#b45309' }
export const MS_LABEL = { communicate: '소통', coordinate: '조율', compromise: '타협', persuade: '설득' }
// What each milestone asks of the candidate (format only; the prepared situations stay undisclosed until the debrief).
export const MS_HINT = {
  communicate: '상황을 파악하는 단계예요. 모르는 건 묻고, 들은 내용을 내 말로 정리해 서로 이해한 게 맞는지 확인해 보세요.',
  coordinate: '요구와 역할이 엇갈리는 단계예요. 누가 무엇을 언제까지 할지, 무엇이 먼저인지 맞춰 보세요.',
  compromise: '서로 양보할 지점을 찾는 단계예요. 꼭 지켜야 할 것과 조정할 수 있는 것을 나눠 이야기해 보세요.',
  persuade: '결정을 이끄는 단계예요. 과제 자료의 숫자나 문장처럼 같이 볼 수 있는 근거를 들어 의견을 설명해 보세요.',
}
export const MODE_LABEL = { competing: '경쟁형', collaborating: '협력형', compromising: '타협형', avoiding: '회피형', accommodating: '수용형' }
export const MODE_POS = { competing: [1, 5], collaborating: [5, 4], compromising: [3, 3], avoiding: [1, 1], accommodating: [5, 1] } // [cooperative, assertive]
export const kappaWord = (k) => (k == null ? '계산 불가' : k < 0 ? '우연 이하' : k <= 0.2 ? '약간' : k <= 0.4 ? '보통 이하' : k <= 0.6 ? '중간' : k <= 0.8 ? '상당' : '거의 완전')
