# 디자인 시스템 (web)

레퍼런스: Linear·Tegon류 이슈 트래커와 칸반 보드(2026-10-20 사용자 제공 이미지). 톤은 "오늘 합류한 팀의 업무 도구". 밝은 바탕, 흰 표면, 얇은 선, 부드러운 모서리, 색은 상태·태그에만. 토큰은 `apps/web/app/globals.css`의 `@theme`가 정본이고 이 문서는 뜻과 쓰임을 적는다. 레이아웃과 흐름은 `design-direction.md`, 화면별 규칙은 `design.md`.

## 색

| 토큰 | 값 | 쓰임 |
|---|---|---|
| canvas | #F6F7F9 | 페이지 바탕 |
| surface | #FFFFFF | 카드·패널·입력 |
| surface-sunken | #EEF0F3 | 레일, 선택된 항목 배경, 코드·인용 |
| line | #DDE1E6 | 1px 경계. 그림자 대신 선 |
| ink / muted / subtle | #1B1F24 / #5F6873 / #8B939C | 본문 / 보조 / 메타(시각·버전) |
| accent | #2F6FDE (+strong #2459B8, soft #E8F0FD) | 버튼·링크·선택·포커스. 하나만 |
| success / warning / danger | #1F8A5B / #B26A00 / #C4362F (+soft) | 완료·마감 경고·오류 |

상태 색(보드 칸·상태 알약). 레퍼런스의 "In review 파랑, In progress 노랑, Done 초록"을 따른다.

| 상태 | 알약 배경 / 글자 | 아이콘 |
|---|---|---|
| 할 일 | #EEF0F3 / muted | 점선 원 |
| 진행 중 | #FDF1DD / #B26A00 | 반원 |
| 완료 | #E5F4EC / #1F8A5B | 체크 원 |

파트 태그 색(파스텔 5색, 채도 낮게). 보드 카드·문서 카드·최종본 섹션에서 같은 파트는 같은 색.

| 파트 | 배경 / 글자 |
|---|---|
| 1 문제 정의 | #E8F0FD / #2459B8 |
| 2 인터뷰 근거 | #FDE8EF / #B0325F |
| 3 핵심 기능 | #FDF1DD / #8A5200 |
| 4 사례 | #E5F4EC / #1F6F4B |
| 5 지표·일정 | #EEE9FB / #5B3FB3 |

사람 색(이니셜 아바타). 한서윤 #5B3FB3 바탕 흰 글자 "서", 이도현 #1F8A5B "도", 지원자 #2F6FDE 별칭 첫 글자. 온라인은 아바타 우하단 초록 점.

## 타이포·간격·모서리

- Pretendard. xs 12 / sm 13 / base 15 / lg 17 / xl 20 / 2xl 24. 메시지 본문 base, 메타 xs, 섹션 제목 lg, 화면 제목 2xl.
- 간격 4px 단위. 카드 안 16, 카드 사이 12, 패널 안 20.
- 모서리 sm 4(태그·알약) / md 8(버튼·입력·카드) / lg 12(패널·대화 상자). 아바타 원형.
- 그림자는 떠 있는 것(팝오버·대화 상자·열린 문서 헤더)에만 `0 8px 24px rgba(27,31,36,.08)`.

## 컴포넌트

기존 `components/ui/`(button, card, badge, status-badge, tabs, field, confirm-dialog, empty-state)에 아래를 더한다. props는 foundation이 정하고 내부는 web-redesign이 쓴다.

| 컴포넌트 | 쓰임 | 비고 |
|---|---|---|
| Avatar | 이니셜·색·온라인 점·크기(20/28/36) | 아바타 묶음(AvatarGroup)은 겹침 -6px |
| Chip | 파트 태그·버전·"2번 필요" 의존 배지 | 배경 soft + 글자 진한 색, radius sm |
| StatusPill | 할 일·진행 중·완료 | 아이콘 + 글자, 보드 칸 머리와 카드에 공용 |
| RailItem | 레일의 채널·DM·알림 | 선택 시 surface-sunken, 안 읽음 수 배지 |
| ChannelHeader | 채널명·멤버 아바타 묶음·마감 시계 | "누가 보는가"를 항상 표시 |
| MessageRow | 아바타·이름·시각·본문 | 말풍선 없음. 같은 사람 연속 메시지는 아바타 생략 |
| SystemLine | "도현님이 4번 v1을 보냈어요" | muted, 가운데 정렬 없이 왼쪽 얇은 줄 |
| DocCard | 메시지 안 문서 카드: 파트 칩·제목·보낸 사람·버전·열기 | 레퍼런스의 첨부 카드 형태, 클릭 영역 전체 |
| DocViewer | 가운데 열린 문서: 헤더(제목·주인·버전 선택·답글·최종본에 가져오기·닫기)·본문 | 열릴 때 대화 위로 슬라이드 |
| DocEditor | 오른쪽 내 문서 편집: 제목·본문 textarea·마지막 저장·보내기 | 1초 디바운스 저장 |
| FinalDoc | 최종본: 섹션 5개, 섹션마다 출처 칩("도현 v2에서")·가져오기·편집 | 제출 버튼은 여기 |
| BoardColumn / BoardCard | 칸 3개, 카드(번호 칩·제목·담당 아바타·언제까지·의존 배지) | 끌어 놓기 dnd kit |
| PropertyRow | 카드 상세 패널의 상태/담당/언제까지/의존 행 | 레퍼런스 8의 속성 행 |
| DocList | 자료함 목록: 잠금 아이콘·공개 예정 시각 | |
| Timer | 상단 "마감까지 01:23:40" | 10분 전부터 warning 색 |
| Toast | 저장·보내기·충돌 안내 | Sonner |

## 라이브러리 (`pick-ui-library` 기준)

| 용도 | 선택 |
|---|---|
| 접근성 기본 요소(메뉴·팝오버·대화 상자·선택) | base-ui (이미 설치) |
| 끌어 놓기(보드) | dnd kit |
| 토스트 | Sonner |
| 전환 애니메이션(문서 열기·카드 이동·레이아웃) | motion. 단순 hover·fade는 CSS |
| 변형 스타일 | cva + clsx (clsx 설치됨) |
| 읽기 전용 Markdown(자료·받은 문서) | react-markdown + remark-gfm(표·목록), 받은 문서만 remark-breaks(평문 줄바꿈). `skipHtml`로 원문 HTML은 그리지 않음 |

## 모션 (`animate`·`review-animations` 기준)

- 문서 열기: 가운데 패널 위로 160ms ease-out 슬라이드 + 페이드. 닫기 120ms.
- 메시지 도착: 120ms 페이드, 스크롤은 사용자가 맨 아래에 있을 때만.
- 보드 카드 이동: layout 애니메이션 150ms. 드롭 시 scale 0.98 → 1.
- 버튼 `:active` scale 0.97. 전환은 `all` 대신 속성 지정.
- 타이머 경고: 10분 전 색 전환 1회, 깜빡임 없음.
- 그 밖의 모션 없음. `break-ui`로 긴 별칭·빈 목록·긴 메시지·긴 문서를 점검한다.

## 하지 않는 것

진한 색 레일, 말풍선, 그라데이션, 사진 아바타, 다크 모드, 이모지 리액션, 스켈레톤 과다(목록 로딩만).
