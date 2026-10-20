// 기획안 파트 제목. State 스냅샷에 제목이 없어 카탈로그(scenarios/catalog.yaml parts)와 같은 값을 둔다.
// State에 parts 제목이 들어오면 이 표를 지운다(보고서 변경 요청).
export const PART_TITLES: Record<number, string> = {
  1: "문제 정의와 대상 사용자",
  2: "사용자 인터뷰에서 찾은 근거",
  3: "핵심 기능 제안",
  4: "비슷한 서비스 사례",
  5: "성공 지표와 출시 일정",
};

export const PART_NUMBERS = [1, 2, 3, 4, 5];

/** "이도현" → "도현님" */
export function callName(fullName: string) {
  return `${fullName.length >= 3 ? fullName.slice(1) : fullName}님`;
}
