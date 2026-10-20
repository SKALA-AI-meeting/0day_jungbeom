// break-ui 점검용 최악의 데이터(개발 mock 전용). 주소에 ?data=worst가 있으면 admin.ts·office.ts가 픽스처에 덮어쓴다.
// 값은 실제로 나올 법한 것만 쓴다: 긴 외국 이름·긴 이메일, 한 글자 별칭, 공백 없는 URL, 긴 문서, 빈 목록.
export const WORST =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).get("data") === "worst";

export const LONG_ALIAS = "Aleksandra Wiśniewska-Kowalczyk";
export const LONG_EMAIL = "bartholomew.fitzgerald@northwind-industries-holdings.example.com";
export const LONG_POSITION =
  "2026 하반기 프로덕트 매니저(커뮤니티·리텐션) 경력 3년 이상 수시 채용 — 2차 과제";
export const LONG_URL =
  "https://docs.example.com/moarun/research/2026-q4/first-meetup-retention-interview-summary-final-v3-revised.pdf";

/** 문단이 여러 개인 긴 문서(최종본 섹션 최대 분량의 두 배쯤) */
export const LONG_DOC = Array.from(
  { length: 14 },
  (_, i) =>
    `${i + 1}) 첫 모임을 마친 참여자 가운데 두 번째 모임에 오지 않은 사람의 이유를 인터뷰와 지표로 나눠 정리합니다. 일정 안내를 놓친 경우와 아는 사람이 없어 어색했던 경우를 따로 셉니다.`,
).join("\n");

export const LONG_MESSAGE = `${LONG_DOC.slice(0, 400)} 참고: ${LONG_URL}`;
