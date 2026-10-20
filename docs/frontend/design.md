# 프론트 설계 (web)

Next.js App Router + Tailwind. 상태 관리는 React 상태와 fetch로 충분하다. UI 라이브러리는 디자인 스킬의 `pick-ui-library`가 고른 것만 쓴다.

## 디자인

- 디자인은 `emilkowalski/skills`를 쓴다. 설치: `npx skills@latest add emilkowalski/skills`. 각 스킬은 `skills/<이름>/SKILL.md`.
- foundation이 기본 토큰(색·타이포·간격)과 공용 컴포넌트의 props·골격만 먼저 확정한다(`pick-ui-library`로 라이브러리 선택). web-admin·web-office는 그 위에서 바로 시작한다.
- 디자인 다듬기는 M2 web-polish 트랙이 한다: `emil-design-eng`, 로고·워드마크, `animate`(메시지 도착·진행 표시·타이머 경고 정도), `review-animations`, `break-ui`(긴 별칭, 빈 목록, 긴 메시지, 5파트 긴 문서). 컴포넌트 내부만 바꾸고 props는 유지한다.
- 서비스 이름과 로고는 Day Zero, Day-Zero, Day-0 중 자유롭게 변주한다. 톤: 채용 도구지만 지원자에게는 업무 도구처럼 보여야 한다. 가상 오피스는 "평가 중"이 드러나지 않게 메신저·문서 도구의 평범한 모습을 유지한다.
- 모션은 절제한다. 메시지 도착, 입력 중 표시, 문서 공개 잠금 해제, 남은 시간 경고(10분 전) 정도만.

## 경로

| 경로 | 화면 | 트랙 |
|---|---|---|
| /admin/login, /admin/signup | 로그인·가입 | web-admin |
| /admin/positions | 채용 건 목록 | web-admin |
| /admin/positions/new | 채용 건 생성: 이름, 요소 체크 4개(1~4개) | web-admin |
| /admin/positions/[id] | 지원자 목록, 초대 폼, 상태 배지 | web-admin |
| /admin/sessions/[id]/report | 리포트, 검토 완료 버튼 | web-admin |
| /s/[token] | 링크 입장 → 동의 → 대기 → 오피스 → 디브리핑 (단계는 상태로 전환). 접속이 끊겨도 시간은 흐르며, 복귀 시 그동안의 메시지를 그대로 봄 | web-office |

## 가상 오피스 레이아웃

```
┌ 상단: 회사명 · 남은 시간(mm:ss) · 제출 버튼 ───────────────┐
│ 좌: 채널 목록(팀 채널, 이도현 DM)  │ 중: 메시지 목록 + 입력  │ 우: 탭(기획안 문서 / 태스크 보드 / 회사 문서 / AI 어시스턴트) │
└───────────────────────────────────────────────────────────┘
```

- 메시지 전송은 `client_msg_id`를 붙이고 `message.ack`로 확정 표시. `message.new`로 추가. `agent.progress`는 run_id별로 started→(tool_start/tool_end)→finished/failed를 따라 "이도현이 입력 중…", "자료 찾는 중…"을 표시. 재접속 시 `/state`의 `active_runs`로 복원.
- 기획안 문서: 파트 5개 textarea. 1초 디바운스 후 PUT. 동료 파트는 읽기 전용이고 `document.part_updated`로 채워짐.
- 보드: 파트 카드 5개, 담당자 배지, 지원자 카드만 상태 select.
- 회사 문서: 목록과 본문. `released=false`면 잠금 표시, `document.released`로 열림.
- 어시스턴트: 요청·응답 목록, 인용 문서명 표시. POST 후 응답 대기 표시.
- 타이머는 `ends_at` 기준으로 로컬 계산. `session.ended` 수신 시 디브리핑으로 전환.
- 재연결: WS 끊기면 3초 후 재연결하고 `/sessions/{id}/state`로 전체 갱신. 세션 JWT가 없으면 `/s/{token}/resume`으로 재발급.

## 관리자 리포트 화면

상단: 단계 배지(검토 대기 draft / 확정 중 / 검토 완료 final), 합계(`9/14 · 기록 없음 2`, 담당자 점수가 있으면 나란히), 헤더 문구("기본 점수는 관찰 기록을 평가표 규칙에 대입해 자동 계산한 값이고 담당자 점수는 검토자가 근거를 보고 조정한 값이며, 이 리포트는 합격·불합격을 판정하지 않습니다").
① 산출물: 파트 5개 본문(읽기 전용), 담당 배지, 수정 횟수, 미작성 표시.
② 요소별 카드: 상황, 관찰된 행동, 근거 목록(t_min과 인용·수정·열람), 평가표 항목 4개(자동 값 1/0/기록 없음, draft 단계에서는 담당자 값 입력 토글과 메모 입력, 바꾸면 메모 필수). 관찰 없음은 회색 안내 문구.
③ AI 활용 섹션(점수 없음).
하단 "검토 완료" 버튼: 조정 내용과 전체 메모를 POST /review로 보내고 "확정 중…"으로 바뀌며 폴링으로 reviewed가 되면 검토 시각과 조정 이력 표시. 검토 완료 후 입력은 잠김. 합격·등급·순위 UI 없음.

## mock

`apps/web/mocks/`에 계약 예시 JSON과 WS 이벤트 재생 스크립트를 두고 `NEXT_PUBLIC_MOCK=1`이면 사용한다.

## 완료 기준

- 관리자: 가입→채용 건 생성(요소 0개·5개는 거부)→초대(링크 복사)→목록 상태(7종)와 합계→리포트 draft(산출물·평가표 입력)→항목 조정(메모 필수)→검토 완료→reviewed(이력 표시)가 mock으로 동작
- 지원자: 만료·완료 링크 안내, 동의 전 시작 불가, 오피스 4탭, 타이머, 진행 표시, 제출, 디브리핑, 재연결 후 상태 복원
