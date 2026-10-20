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
export const MODE_LABEL = { competing: '경쟁형', collaborating: '협력형', compromising: '타협형', avoiding: '회피형', accommodating: '수용형' }
export const MODE_POS = { competing: [1, 5], collaborating: [5, 4], compromising: [3, 3], avoiding: [1, 1], accommodating: [5, 1] } // [cooperative, assertive]
export const kappaWord = (k) => (k == null ? '계산 불가' : k < 0 ? '우연 이하' : k <= 0.2 ? '약간' : k <= 0.4 ? '보통 이하' : k <= 0.6 ? '중간' : k <= 0.8 ? '상당' : '거의 완전')
