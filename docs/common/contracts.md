# 인터페이스 계약

병렬 트랙의 공용 기준. 트랙은 이 파일을 바꾸지 않는다. 바꿔야 하면 오케스트레이터에 올린다. 2026-10-21 토론형 전환(`docs/handoff/briefs/brief-debate-pivot.md`) 기준이며, 보드·분업·파트 문서·팀장·문서 공개 예약 계약은 모두 삭제됐다. 브리프 맨 아래 "리뷰 반영 결정"(R1~R7)을 반영했다: 요소 5개·페르소나 3명 고정(채용 건의 요소 선택 없음), 세션 길이 60·15분, 칸 상태 `empty | confirmed`, 그래프 자극 4종과 세션 메일박스, api 직접 시간 초과 채우기, 카드 `card_due` 단일 트리거.

예시 JSON은 mock 서버와 테스트 픽스처의 정본이다. 단, **요소·카드·페르소나 유형·평가표 차원(`dimension_id`)의 id는 문자열로만 받고 실제 목록은 `rubric.md`(BARS 척도, 차원 19개)·`scenario-model.md`가 정본**이다. 예시의 `persuasion`·`stubborn`·`listen_engage` 같은 값은 자리표시다.

## 공통

- 공개 베이스: `http://api:8000` (web이 호출). 내부 베이스: `http://api:8001` (`/internal/*`만, compose 네트워크 안에서만 열림, 포트 미공개).
- 응답 JSON. 오류는 `{"error": {"code": "...", "message": "..."}}`와 HTTP 4xx/5xx. **입력 검증 실패는 모두 422**이고 `code`는 `invalid_input` 또는 그 세부 코드(`invalid_keyword`·`invalid_dimension`·`memo_required`·`duplicate_dimension`·`invalid_previous_session`)다(400은 쓰지 않는다). 상태 충돌은 409이고 `code`는 `conflict` 또는 세부 코드다: `phase_not_open`(현재 단계가 아님), `slot_confirmed`(칸이 이미 확정), `no_consensus`(합의 판정이 그 안이 아님), `stale_generation`(게시 시점 generation 불일치), `session_ending`(제출·종료 뒤 쓰기), `already_reviewed`(검토 뒤 다른 본문), `draft_mismatch`(final 해시가 draft와 다름). 그 밖의 상태 충돌은 `conflict`. 권한 401·403, 없음 404, 만료·취소 410, 잠김 423.
- CORS: 공개 앱(8000)만 `WEB_ORIGIN`(쉼표 구분, 기본 `http://localhost:3000`)을 허용한다. 메서드 전부, 헤더 `Authorization`·`Content-Type`. 내부 앱(8001)에는 두지 않는다.
- 인증 헤더: `Authorization: Bearer <jwt>`. 내부: `X-Internal-Token: <secret>`. assessment-mcp: `X-Assessment-Token: <secret>`.
- 시각은 ISO 8601 UTC. 세션 상대 시각은 `t_min`(세션 시작 기준 분, 소수 허용)으로도 함께 준다.
- 오피스 시각: `오피스 시각 = 09:00 + t_min × 60 / session_minutes`(분 단위 내림, "HH:MM"). 60분 세션은 09:00~10:00, 데모 15분도 같은 비율. API는 `t_min`과 `session_minutes`를 주고 표시 변환은 web이 한다. 지원자 화면은 남은 시간을 중심으로 보이고 오피스 시각은 메시지 타임스탬프에만 쓴다(같은 줄에 함께 쓰지 않음).
- 세션 길이 `session_minutes` ∈ {60, 15}. 15분은 데모·e2e용 압축이고 모든 시각 값은 같은 비율로 환산한다(카드·유휴 오프셋은 최소 20초).
- 참여자 id: `candidate`, `p1`·`p2`·`p3`(AI 동료 자리), `system`. **공개 API와 WS에는 자리 id와 표시 이름만 나가고 페르소나 유형은 나가지 않는다.** 자리 → 유형 대응은 `positions.scenario.seats`에 있고 관리자 리포트·디브리핑·내부 API만 본다.
- 표시 이름·프로필(D13-3): 참여자·자리 객체는 `display_name`과 `avatar_url`을 가진다. 지원자는 `display_name`만(`sessions.display_name`, 동의 때 입력, 비우면 초대 별칭)이고 화면은 이니셜 아바타를 쓴다. AI 자리의 `display_name`은 `positions.scenario.seats[].name`, `avatar_url`은 같은 자리의 `avatar`(카탈로그 `personas.yaml`의 `avatar`, 파일은 `scenarios/missions/<id>/assets/avatars/`)로 만든 `/assets/missions/<mission_id>/avatars/<file>`이다. 이 경로는 공개 앱(8000)이 읽기 전용으로 서빙한다. 이미지는 임시이며 교체는 에셋 파일과 `avatar` 경로만 바꾼다. 관리자 리포트·목록은 별칭(`alias`)을 기본으로 쓴다.
- 단계 id: `keyword`, `problem`, `solution`, `proposal`. 앞 셋이 칸(slot)을 가진 토론 단계다.
- 멱등: `Idempotency-Key` 헤더는 쓰지 않는다. 도메인 규칙과 아래 저장 키로만 보장하며 같은 키의 재요청은 기존 행을 돌려준다.

| 저장 | 멱등 키 |
|---|---|
| 지원자 메시지 | (session_id, client_msg_id) |
| AI·시스템 메시지 | (session_id, run_id, seq) |
| 의도 분류 | message_id |
| 안(option) | 시나리오 안은 (session_id, phase, scenario_option_key), 자유 안은 (session_id, phase, source_message_id). 같은 시나리오 안을 누가 다시 제안해도 기존 행을 돌려준다(최초 제안자 보존) |
| 입장(stance) | (session_id, source_message_id, participant, option_id) |
| 칸 확정 | (session_id, phase). 이미 confirmed면 같은 run_id 재요청은 기존 칸, 다르면 409 `slot_confirmed` |
| 합의 채우기(`fill_slot`) | 칸 확정과 공지 메시지가 한 트랜잭션. 공지는 (session_id, run_id, seq 5), `meta.kind = "consensus_fill"`. 같은 run_id 재호출은 단계가 이미 넘어갔어도 기존 칸·공지를 돌려준다 |
| 시간 초과 채우기 | (session_id, phase). 공지 메시지는 run_id = `uuid5(session_id, "timeout:"+phase)`, seq 0 |
| 카드 관찰 | (session_id, card_id) |
| 카드 진행(`session_cards`) | (session_id, card_id). `delivered_seats`는 자리 집합(중복 추가 무시), `locked_option_id`는 처음 한 번만 |
| 평가 실행(`save_evaluation`) | (session_id, run_id). 같은 run_id의 `evaluation_runs` 행이 있으면 저장하지 않고 기존 결과 반환(재시도 이어하기·리포트 재생성 재사용). 차원 행 unique는 (session_id, dimension_id, run_id) |
| 담당자 조정(review) | 세션 상태. approving 이후 같은 본문 재요청은 200, 다르면 409 |
| 기획안 제출 | 세션 상태. completed 이후 재호출은 저장된 값 |

## 세션 상태 머신

### status (생명주기)

```
invited ──동의·시작──▶ in_progress ──제출 / 세션 만료 자동 제출──▶ completed ──워커 draft──▶ report_ready ──검토 완료──▶ approving ──워커 final──▶ reviewed
   │                        │                                              └──워커 3회 실패──▶ failed(report) ──재생성──▶ completed
   └──취소──▶ cancelled ◀────┘ (시작 후 취소 = 중도 포기, 리포트 없음)
                            └──페르소나 LLM 연속 실패 3회──▶ failed(session)
```

- `ended_at`: 세션이 끝난 시각. completed(제출·자동 제출)·failed(session)·cancelled로 바뀌는 트랜잭션에서 한 번 쓴다(시작 전 취소 포함). failed(report)는 이미 completed라 바꾸지 않는다. **삭제 예정일 `purge_at = ended_at + 90일`, 디브리핑 기한 = `ended_at + 7일`**.

### phase (in_progress 안의 진행)

| phase | 칸 | 예산(60분 기준, 15분은 ÷4) | 다음으로 가는 조건 |
|---|---|---|---|
| keyword | keyword | 10분 (2.5) | 칸 confirmed (지원자 확정 / AI 합의 채우기 / api 시간 초과 채우기) |
| problem | problem | 18분 (4.5) | 같음 |
| solution | solution | 18분 (4.5) | 같음 |
| proposal | 없음 | 14분 (3.5) | 기획안 제출 또는 `ends_at` 자동 제출 |
| completed | — | — | status=completed와 같은 트랜잭션 |

- 시작 전 phase는 null. start에서 `keyword`.
- 단계가 바뀌면(`advance_phase`) `sessions.generation`도 +1 한다(아래 "세션 메일박스").
- 단계 마감은 누적 고정: `phase_deadline_at(k) = started_at + (예산 1..k의 합) × session_minutes / 60`. 일찍 확정하면 남은 시간이 다음 단계로 이월된다. proposal 마감 = `ends_at`.
- 상태·단계 변경은 api `SessionService` 한 곳만 한다(start, advance_phase, submit, cancel, fail, mark_report_ready, approve, mark_reviewed, regenerate).

### 칸(slot) 상태

```
empty ──지원자 확정 / AI 합의 채우기 / api 시간 초과 채우기──▶ confirmed
```

칸 상태는 두 개뿐이다. 지원자 초안 저장(`PUT slots`)·`filled` 상태·WS `slot.filled`는 없다(입력 중 값은 화면에만 있다).

| 필드 | 값 |
|---|---|
| status | `empty` ∣ `confirmed` |
| value | 확정 값(짧은 문장) |
| option_id | 확정 값과 같은 안. 지원자 확정 값이 어느 안과도 연결되지 않으면 null |
| filled_by | `candidate` ∣ `p1`∣`p2`∣`p3` (시간 초과 채우기도 공지한 자리 id. `system` 값은 없다) |
| resolution | `consensus` ∣ `timeout` |
| support | 확정 순간의 지지 현황 스냅샷 `[{option_id, supporters: [participant]}]` |
| confirmed_at, t_min | 확정 시각 |

- 지원자는 언제든 확정할 수 있다(혼자 확정 포함). 확정 순간의 지지 현황이 `support`에 남아 분석에서 보인다.
- keyword 칸은 버튼으로 후보 키(`option_key`, 예: `water`)를 보내 확정한다. 후보 밖 키면 422 `invalid_keyword`. 그 키의 안 행이 없으면 api가 만든다(proposer = candidate, source_message_id null).
- 문제 상황·해결책 칸의 지원자 확정 값은 **결정적 규칙으로만** 안에 연결한다(확정 경로에 LLM 없음): ① 요청의 `option_key`가 그 단계의 기존 안 행의 `scenario_option_key`와 같거나 ② `value`를 정규화(위치와 관계없이 구두점 전부 제거, 연속 공백을 하나로, 앞뒤 공백 제거, 소문자. 예: `도심 폭우·침수` = `도심 폭우침수`)한 문자열이 그 단계 기존 안 라벨의 정규화 값과 같으면 그 안. 둘 다 아니면 `option_id=null`이고 새 안을 만들지 않는다(최초 제안자를 잘못 귀속하지 않기 위해).

### 합의 판정과 시간 초과 선택 (api의 함수 하나 `consensus.judge`)

수치·우선순위·채우는 자리 선택은 `scenario-model.md` "AI 동료가 칸을 채우는 조건"·"시간 초과 규칙"이 정본이다. 계약은 입력과 결과만 고정한다.

- 입력: 그 단계의 안과 `stances` 이력. **현재 지지는 참여자당 하나**다 = 참여자별로 그 단계의 마지막 `support` 행의 안. 다른 안을 support하면 이전 지지를 대체한다(두 안을 동시에 지지하지 않는다). 그 뒤에 **같은 안에 대한 `oppose`가 있으면 지지를 철회**한 것으로 보고 현재 지지는 null이다. 다른 안에 대한 oppose는 현재 지지를 바꾸지 않는다. 제안(propose)은 제안자의 지지를 포함한다. 지원자 입장은 의도 분류 `confidence = high`일 때만 stances 행이 된다(아래 "의도 분류 출력 스키마"). AI 입장은 항상 유효하다.
- 합의 결과 `consensus_option_id`: 한 안의 현재 지지자가 4명 중 3명 이상이고 **지원자가 그 지지자**이면 그 안, 아니면 null. 대기 시간 조건은 없다(성립하는 즉시 AI가 채운다).
- 시간 초과 결과 `timeout_option_id`: 지지자 최다 → 동률이면 지원자 지지 안 → 먼저 제안된 안 → 안이 없으면 단계 기준안(문제 상황은 카드가 잠근 `session_cards.locked_option_id`가 있으면 그것, 키워드는 `default_keyword`). 기준안 행이 없으면 채우기 트랜잭션에서 그 안을 만든다(proposer는 공지하는 자리).
- 두 값은 DebateState에 실리고, api의 `fill` 검사와 시간 초과 채우기가 같은 함수를 쓴다.
- **같은 run 재판정**: 그래프 `fill` 노드는 `apply`가 이번 run의 발언 입장을 저장한 **뒤** 지지를 다시 읽어 판정한다(load 때 값만 보지 않는다). AI 발언으로 지원자 포함 3/4 지지가 생기면 다음 자극을 기다리지 않고 같은 run에서 채운다.

### 시간 초과 채우기 (api가 직접, 그래프 없음)

스케줄러가 `now ≥ phase_deadline_at`이고 칸이 empty인 토론 단계를 찾으면 api `services/timeout.py`가 한 트랜잭션으로: `timeout_option_id` 계산 → 공지 자리(시나리오의 시간 초과 우선순위 첫 자리, `scenario-model.md`) 이름으로 시나리오 고정 문장("시간이 다 돼서 대화에서 가장 많이 모인 의견인 X로 할게요")을 messages에 저장(sender = 그 자리, `meta.kind = "timeout_fill"`) → 칸 confirmed(`resolution: timeout`, `filled_by` = 그 자리) → `advance_phase`. LLM·MCP·메일박스를 거치지 않는다. 그래프 자극에 `timeout`은 없다.

### 합의 채우기 (그래프 `fill` → `fill_slot`, 한 트랜잭션)

그래프 `fill` 노드의 `announce_fill` 분기가 지지자 중 우선순위 자리(`scenario-model.md`)와 시나리오 고정 문장("그럼 X로 정리할게요.", 이름만 치환)을 정해 `fill_slot{session_id, option_id, seat, content, run_id}`를 한 번 부른다. 이 분기는 일반 발언 루프(`respond → guard → stance_check → apply(post_message)`)를 거치지 않고 LLM도 부르지 않는다. api는 한 트랜잭션으로: `consensus.judge` 재검사(이 option_id가 합의 안이 아니면 409 `no_consensus`) → 칸 confirmed(`resolution: consensus`, `filled_by` = seat) → 공지 메시지 저장(sender = seat, run_id, seq 5, `meta.kind = "consensus_fill"`) → `advance_phase`(generation +1). 커밋 뒤 WS로 `message.new`(공지)와 `slot.confirmed`를 보내고 이어서 전환 공통 프레임(`phase.changed`·`timer`, keyword면 `materials.opened`)을 보낸다. 409면 칸·공지·단계 어느 것도 저장하지 않는다. 칸 확정과 공지가 함께 커밋되므로 "칸은 확정됐는데 공지가 없는" 상태가 생기지 않고, 재실행이 낡은 자극으로 `skipped`돼도 보충할 공지가 남지 않는다.

### 지원자 문구 (R7)

지원자 화면 문구는 내부 용어 대신 지원자 말을 쓴다: 칸 → "정할 항목", 합의 패널 → "결정 사항", 확정 → "이걸로 정하기". API 필드 이름(`slot`·`confirm`)은 그대로다.

칸 결과 표시(지원자 화면·관리자 리포트 공통): api가 칸마다 표시용 `outcome`(`consensus`∣`candidate_decision`∣`timeout`∣확정 전 null)을 계산해 `/state`의 `slots`, 칸 확정 응답의 `slot`, WS `slot.confirmed`, 리포트 `slots`에 함께 내린다(열로 저장하지 않고 확정 값에서 계산). `resolution: timeout`이면 `timeout`("시간 초과"). `resolution: consensus`이면 확정 시점 `support` 스냅샷에서 확정 안 지지자가 참여자 4명 중 3명 이상이면 `consensus`("합의"), 아니면(지원자 혼자 확정 등) `candidate_decision`("지원자 결정"). AI 합의 채우기(`fill_slot`)는 항상 `consensus`다. 화면은 `outcome`만 보고 지지 현황(`support`)은 계속 지원자 화면에 내려가지 않는다. 데이터 값(`resolution`)은 바꾸지 않는다.

## 의도 분류 출력 스키마

지원자 메시지마다 **세션 메일박스가 `message` 자극을 꺼낼 때** 순서대로 호출한다(`MODEL_INTENT`, 타임아웃 10초, 재시도 없음). 큐 밖에서는 메시지 저장·generation +1·enqueue만 한다. 분류와 아래 안·입장 반영은 그 자극이 낡았어도(generation이 현재 값보다 작음) **반드시 수행**하고, 낡은 자극에서 건너뛰는 것은 턴 선택·페르소나 발언 생성뿐이다. 분류 결과는 `message_id` 멱등이라 같은 자극의 재실행(재큐·재시작)에서 다시 부르지 않는다. **분류 입력과 안·입장 저장 대상의 단계는 저장된 `messages.phase`**다. 메일박스가 밀린 동안 단계가 바뀌었어도 현재 단계로 바꿔 분류하지 않는다. 현재 단계 검사는 턴 선택·발언 생성을 생략할지 판단하는 데만 쓴다. 입력: 메시지, 메시지의 단계(`messages.phase`), 그 단계의 기존 안 목록 `[{option_id, label, scenario_option_key}]`, **그 단계의 카탈로그 안 전체** `[{scenario_option_key, label}]`(아직 아무도 말하지 않은 안 포함. 키워드 단계는 후보 4개), 직전 메시지 5개.

```json
{"intent": "propose", "target_option_id": null, "scenario_option_key": "water_p2", "new_option_label": null, "confidence": "high", "addressed_to": ["p2"]}
```

| 필드 | 값 |
|---|---|
| intent | `propose`(새 안 또는 기존 안을 자기 의견으로 냄) ∣ `agree` ∣ `oppose` ∣ `question` ∣ `other` |
| target_option_id | 대상이 기존 안 행이면 그 id, 아니면 null |
| scenario_option_key | 대상이 아직 행이 없는 카탈로그 안이면 그 키, 아니면 null |
| new_option_label | intent=propose이고 기존 안·카탈로그 안 어느 것과도 다를 때 짧은 라벨(20자 이내), 아니면 null |
| confidence | `high` ∣ `low`. 의도와 대상이 분명하면 high |
| addressed_to | 이름을 부르거나 답한 자리 id 목록(턴 매니저 규칙 입력). 없으면 [] |

처리(결정적 코드):

- `propose` + scenario_option_key → 그 키로 안 행을 만들거나(이미 있으면 기존 행, 멱등 키 (session_id, phase, scenario_option_key)) proposer = candidate. 뒤에 AI가 같은 안을 `propose_option`해도 같은 행이 돌아오므로 최초 제안자가 보존된다. `propose` + new_option_label → 자유 안(proposer = candidate). **안 행은 confidence와 상관없이 만든다**(최초 제안 사실 기록).
- 입장: confidence = high일 때만 stances 행을 쓴다. `propose`·`agree` + 대상 → support, `oppose` + 대상 → oppose(같은 안의 이전 support를 철회). confidence = low·`question`·`other` → 입장 없음.
- 실패·스키마 위반은 `{"intent": "other", "target_option_id": null, "scenario_option_key": null, "new_option_label": null, "confidence": "low", "addressed_to": []}`, `fallback=true`.
- 분류는 토론 진행용이다. 세션 후 평가 에이전트에는 참고 입력으로만 들어가고 원문과 다르면 원문을 따른다(`rubric.md` 1.2). 정확도 기준선은 `tests/eval/` 의도 분류 20문장을 실 모델(gpt-4o-mini)로 잰 0.85다.

## 그래프 자극 (stimulus)

토론 그래프는 자극마다 한 번 실행된다. 자극은 아래 **4종**이고 `agent_runs.stimulus`·턴 매니저 결정의 `stimulus`·State 스냅샷 `active_runs[].stimulus`가 같은 값을 쓴다. `timeout`(api가 직접 채움)·`room_quiet`는 없다.

| type | 발생 | 함께 오는 값 | run_id |
|---|---|---|---|
| `message` | 지원자 room 메시지 저장 뒤(의도 분류는 메일박스가 이 자극을 처리할 때) | message_id | api가 새로 발급(uuid4) |
| `phase_started` | 세션 시작·단계 전환 커밋 뒤 `advance_phase`가 넣음 | phase | `uuid5(session_id, "phase:"+phase)` |
| `idle` | api 스케줄러. 토론 단계에서 침묵 초대 조건(`scenario-model.md` 3.1)이 참이고 그 단계 `invite_delivered`가 false | phase | enqueue마다 새로 발급(uuid4) |
| `card_due` | api 스케줄러. 카드 예정 시각(단계 시작 + `offset_min`, 최소 20초) 도달 뒤 그 카드가 아직 `delivered`가 아님 | phase, card_id | enqueue마다 새로 발급(uuid4) |

형식: `Stimulus = {type, phase, generation, message_id?, card_id?}`. `message` 자극의 `generation`은 **그 메시지 저장 트랜잭션이 올린 값**이다(enqueue 시점에 다시 읽지 않는다. 그사이 다른 메시지가 저장됐으면 이 자극은 낡은 자극이 된다). 다른 자극의 `generation`은 enqueue 시점의 `sessions.generation`. `message` 자극의 `phase`는 그 메시지의 `messages.phase`.

- **다시 넣기(재평가)**: 스케줄러는 5초 틱마다 조건을 다시 본다. 침묵 초대가 아직 전달되지 않았으면(`invite_delivered` false) `idle`을, 카드가 아직 `delivered`가 아니면 `card_due`를 다시 넣는다. 같은 단계의 `idle`, 같은 card_id의 `card_due`가 이미 큐에 있거나 실행 중이면 넣지 않는다. 지원자가 입력 중(`typing` 유효)이면 그 틱에는 넣지 않는다.
- `card_due`는 담당 자리 전원이 delivered될 때까지 enqueue마다 **새 uuid4 run_id**로 다시 넣는다. 카드 1회 실행 제한이나 고정 run_id는 없다. 앞 run이 `finished`여도 일부 화자가 버려졌으면 다음 `card_due`가 남은 화자를 이어서 넣는다. 카드 전달의 멱등은 `session_cards.delivered_seats`(자리 집합)와 관찰의 (session_id, card_id)로만 판단한다.
- 카드 트리거는 시각 기반 `card_due` 하나다(이벤트 트리거 없음). 예외로 페르소나 발언이 없는 `honesty_credit`은 기획안 단계 `phase_started` 실행에서 `record_observation`만 남긴다(`trigger_message_id` = 그 단계 시작 시스템 안내 메시지).
- **카드 진행 상태 `session_cards`**: 카드마다 `(session_id, card_id)` 한 행. `card_due` 첫 처리 때 행을 만들고, 문제 상황 카드(`flexibility_majority`·`listening_pressure`)는 그때 기준안을 계산해 `locked_option_id`·`locked_at`으로 잠근다 = "지원자의 현재 지지 안이 아닌 첫 시나리오 안"(`scenario-model.md` 순서). 그 시나리오 안의 행이 아직 없으면 잠금 트랜잭션에서 만든다(proposer = 그 카드의 첫 담당 자리, 곧바로 카드 발언으로 그 안을 밀기 때문). 같은 단계의 두 카드는 같은 기준안을 쓰고 한 번 잠그면 바꾸지 않는다. 예정 시각이 같은 카드들은 먼저 실행된 `card_due` run의 `cards` 노드가 예정 시각이 지난 미전달 카드를 함께 처리한다(뒤에 꺼낸 같은 시각 카드의 `card_due`는 `delivered_seats`에 이미 든 자리를 다시 말하게 하지 않는다). 카드 전에는 고집형도 입장을 밝히지 않는다.
- **전달 기록**: 카드 화자가 실제로 게시해야 전달이다. 메시지 하나가 여러 카드를 함께 전달할 수 있다(예: 같은 시각의 `flexibility_majority`·`listening_pressure`는 고집형의 첫 기준안 발언이 두 카드의 첫 발언). `POST /internal/sessions/{id}/messages`의 `card_ids`(카드 id 배열)에 든 **카드마다** api가 그 `session_cards` 행의 `delivered_seats`에 sender 자리를 더한다. 담당 자리(`scenario-model.md` 카드 `actor`를 `seats`로 대응) 전원이 들어가면 그 카드는 delivered이고, 아직이면 다음 run의 결정적 노드가 남은 화자를 이어서 넣으며 스케줄러도 `card_due`를 다시 넣는다. 카드 관찰(`record_observation`)은 **카드마다 1건**, 그 카드의 첫 카드 발언이 게시된 뒤 기록한다(`trigger_message_id` = 그 메시지. 공동 전달이면 두 관찰이 같은 메시지를 가리킨다).

### 세션 메일박스 (직렬화)

- api 프로세스에 세션마다 메일박스 하나(`app/mailbox.py`): asyncio Queue + 소비 Task 1개가 자극을 하나씩 직렬로 실행한다. 세션 Lock·`lock_held`·처리 집합(`handled`)은 없다. api는 단일 프로세스로 운영한다.
- 큐 밖의 지원자 메시지 처리는 저장·`sessions.generation += 1`(같은 트랜잭션)·`message` 자극 enqueue뿐이다. 단계 전환(`advance_phase`)도 +1. 그래프는 **각 게시 직전** generation을 다시 읽어 실행 시작 때 값과 다르면 남은 화자를 버린다(실행은 `finished`, `decision.dropped_seats`에 기록). `post_message`의 `expected_generation`이 api에서 같은 검사를 원자적으로 한 번 더 한다(다르면 409 `stale_generation`).
- `message` 자극은 꺼낸 순서대로 먼저 의도 분류와 안·입장 반영을 한다(위 "의도 분류 출력 스키마", 저장된 `messages.phase` 기준, 낡은 자극도 생략하지 않음). 그다음 자극이 낡았으면 턴 선택·페르소나 발언 생성을 하지 않고 `agent_runs.status = skipped`로 닫는다: phase가 현재 단계와 다름, 또는 `message` 자극인데 generation이 현재 값보다 작음(뒤의 메시지 자극이 응답을 맡음). 다른 자극은 낡았으면 아무것도 하지 않고 skipped.
- 지원자 입력 중 대기(그래프 노드 `wait_typing`): 게시 직전 지원자 `typing`이 유효하면 최대 10초 기다린다. 그래도 유효하면 게시하지 않고 같은 자극을 새 run_id로 큐 뒤에 다시 넣고 이번 실행은 `deferred`.
- `advance_phase`는 `phase_started`를 큐에 넣기만 한다.
- 멱등은 `agent_runs.status`와 DB 멱등 키만 쓴다. 자극 저장: `agent_runs` 행을 `queued`로 만든 뒤 큐에 넣는다. 재시작하면 `queued`·`started` 행을 같은 run_id로 다시 넣는다. 실행 중 프로세스에서 `started`가 200초(역할별 타임아웃 합 + 여유)를 넘으면 `failed`로 닫고 같은 run_id로 다시 넣는다. 같은 run_id 재실행의 게시는 (session_id, run_id, seq) 멱등으로 중복되지 않는다. 합의 채우기는 칸 확정·공지·generation +1이 한 트랜잭션(위 "합의 채우기")이라 fill 커밋 뒤 재실행이 단계 변경으로 `skipped`돼도 미게시 공지가 남지 않는다.
- 비용: LLM 래퍼가 호출마다 `usage.cost_usd`(모델별 단가 표, 래퍼 한 곳)를 계산한다. 누계는 두 컬럼이다: `sessions.debate_cost_usd` = 세션 중 토론 LLM 비용(의도 분류·턴·페르소나·어시스턴트, 하드 상한용), `sessions.cost_usd` = 전체 관측값(토론 + 리포트 평가). 목표 $0.5/세션은 `cost_usd`로 관측만 하고, 토큰 수도 `agent_runs.usage`에서 관측만 한다(세션 중 응답을 끊지 않음). 판단은 api `services/budget.py` 한 곳이 DB에서 `debate_cost_usd`를 읽어 `cost_left = SESSION_COST_HARD_USD(기본 $2) − debate_cost_usd`로 계산하고 DebateState `cost_left`로 넘긴다. `cost_left ≤ 0`이면 페르소나는 LLM 없이 자리별 고정 안전 문구만 게시한다(의도 분류·턴 규칙은 그대로). 시간 초과·합의 채우기·제출은 그대로 진행한다.
- api/agent 경계 `SessionPorts`: `send_typing(seat, state)`, `get_generation()`, `candidate_typing()`, `enqueue(stimulus)`. 그래프는 이 포트로만 api 내부 상태에 닿는다.

## 턴 매니저 결정 스키마

토론 그래프 `turn` 노드의 출력. `agent_runs.decision`에 저장한다(관측·테스트용).

```json
{"stimulus": "message", "generation": 12, "speakers": [{"seat": "p1", "purpose": "push_option", "option_id": "...", "card_ids": []}], "fill": null, "invite": false, "llm_used": false, "dropped_seats": [], "reason": "지원자가 p1의 안에 반대함"}
```

- `purpose`: `respond`(지원자에게 답) ∣ `push_option`(자기 고정 안 주장) ∣ `react`(다른 동료 발언에 반응) ∣ `invite`(침묵 초대) ∣ `card`(카드가 정한 발언. 이전 run에서 전달되지 않은 카드 화자를 이어서 포함). `card_ids`는 그 발언이 전달하는 카드 id 배열(카드 발언이 아니면 []).
- `speakers`는 0~2명이고 일반 발언 루프(respond → apply)를 탄다. 합의 채우기 공지 화자는 `speakers`에 넣지 않는다.
- `fill`은 `{option_id, seat}`(합의 채우기만, seat = 공지·채우는 자리) 또는 null. `fill` 노드의 `announce_fill` 분기가 이 값으로 `fill_slot{option_id, seat, content, run_id}`를 한 번 불러 칸 확정과 공지를 함께 저장한다(위 "합의 채우기"). load 때 합의가 없었어도 apply 뒤 재판정에서 합의가 생기면 같은 분기를 탄다.
- 규칙 결과가 0명이고 자극이 `message`일 때만 턴 LLM(`MODEL_TURN`)을 부른다(`llm_used`). 나머지 자극은 규칙만.

## 인증 생명주기

| 단계 | 호출 | 상태 | 토큰 |
|---|---|---|---|
| 초대 생성 | 관리자 POST /admin/positions/{id}/invites | sessions 행이 `invited`로 함께 생성됨 | 초대 토큰(링크에만, DB에는 해시) |
| 링크 입장 | GET /s/{token} | 응답에 `session_id`·`default_display_name`(초대 별칭, 표시 이름 기본값) 포함. 시작 전 만료(72h) → 410 `expired`, 취소 → 410 `cancelled`. completed 이후·failed → 200에 `status`·`session_id`·`debrief_token`(디브리핑·제출본 열람·설문만, `ended_at` 후 7일). 입장 화면 고정 안내(`entry_notice`, 문구는 PRD): 60분 연속 진행·중간 휴식 없음·PC 권장·AI 동료 3명과 채팅으로 키워드 → 문제 상황 → 해결책을 정하고 기획안을 혼자 써서 제출·**토론 결과가 내 제안과 다를 수 있고 안의 질이 아니라 과정의 태도를 본다**·끊겨도 시간은 흐름·외부 도구는 막지 않되 안의 AI 어시스턴트 요청·응답은 사실로 기록되고 AI가 평가 수준을 매기지 않음·문의 창구 | 없음 |
| 동의 | POST /s/{token}/consent {display_name?} | `consented_at`·`sessions.display_name` 기록(비우면 별칭, 시작 뒤에는 바꾸지 않음) | `{session_token, session_id}`. 세션 JWT 만료 = now + session_minutes + 120분 |
| 시작 전 조회 | GET /sessions/{id}/state (Bearer) | 동의 뒤 시작 전(status invited)에도 허용: 참여자 이름·아바타, 단계 예산, 빈 칸·빈 메시지(시계 값은 null) | 같은 JWT |
| 시작 | POST /s/{token}/start (Bearer) | `in_progress`, `phase=keyword`, started_at·ends_at·phase_deadline_at 확정, 칸 3행(empty)·기획안 초안 행 생성, 첫 시스템 안내 메시지 저장, `phase_started` 자극 enqueue. 시작 시점에 초대가 만료됐으면 410 `expired` | 같은 JWT |
| 재입장 | GET /s/{token} → invited면 consent 재호출, in_progress면 POST /s/{token}/resume, completed 이후면 응답의 `session_id`·`debrief_token`으로 `/sessions/{id}/debrief` | 변화 없음 | resume 응답 `{session_token, session_id}` |
| 재발급 | 관리자 POST /admin/sessions/{id}/reissue | 시작 전(invited, 만료 포함) 세션의 초대 토큰·만료만 교체. 같은 세션·같은 별칭. 옛 링크는 404 `not_found` | 새 초대 토큰 |
| 종료 | 제출 또는 세션 만료 자동 제출 → 같은 요청 안에서 `completed`(+`ended_at`). 자동 제출이면 `proposals.auto_submitted=true`, WS `session.ended{reason: timeout}` | `completed` | JWT는 디브리핑 조회까지 유효 |

검증: 다른 세션 id 접근 403, 동의 중복은 멱등, 시작 후 동의 409, 시작 전 JWT 만료는 consent 재호출, 시작 후 만료는 resume. 재응시(세션 실패·취소·시작 전 만료 뒤 다시 보게 함)는 새 초대·새 세션이고(`previous_session_id`), 재발급은 같은 세션이다.

## 관리자 REST (`/admin`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| POST | /admin/auth/signup | {email, password, company_name} | {token}. 이미 있는 이메일 409 `conflict` |
| POST | /admin/auth/login | {email, password} | {token}. 실패 401 `unauthorized` |
| GET | /admin/catalog | | {elements: [{id, name, meaning, how_we_see}], session_minutes_options: [60, 15], default_session_minutes: 60, candidate_notice_template, candidate_faq: [{q, a}]}. 요소 카드 5장(이름·한 줄 뜻·"이렇게 봅니다")은 **안내용**이다. 모든 채용 건이 5요소를 본다(선택 기능 없음). 페르소나 유형·카드·평가표 차원은 보여 주지 않는다 |
| GET | /admin/positions | | [{id, name, session_minutes, candidate_count, created_at}] |
| POST | /admin/positions | {name, session_minutes?: 60∣15, mission_id?: "debate"} | {id, name, session_minutes, seats: [{seat, name, persona_type, avatar_url}], keywords: [string], catalog_version}. 요소 선택 입력은 없다. 자리 3개는 고정(`p1` 고집형·`p2` 소극형·`p3` 비판형, 이름·아바타는 `scenario-model.md`)이고 5요소·카드 6장을 포함한 시나리오 전체를 `positions.scenario`에 복사·고정. 수정·삭제 없음 |
| GET | /admin/positions/{id}/candidates | | [{session_id, alias, email, status, display_status, display_group, phase?, invited_at, started_at?, ends_at?, ended_at?, last_activity_at?, message_count, report_ready_at?, purge_at?, failed_stage?, failed_reason?, next_action?, previous_session_id?, reissued_at?, elements?: [{element, level: 1~5∣null, adjusted: bool}], low_confidence_count?, level_source?: "auto"∣"reviewer"}]. display_group ∈ waiting∣in_progress∣needs_review∣done∣problem. purge_at = ended_at + 90일(세션이 끝나기 전 null). `elements`는 요소별 수준 칩(조정 병합 후 값), `low_confidence_count`는 확신도 low 차원 수, `level_source`는 조정 행이 하나라도 있으면 reviewer. report 없으면 이 필드들은 null. **총점 없음, 수준 정렬 없음**. 정렬은 초대순 |
| POST | /admin/positions/{id}/invites | {alias?, email, previous_session_id?} | {session_id, invite_url, expires_at, notice_text}. 발송하지 않음(링크·안내 문안 복사). 새 초대는 alias 필수이고 같은 채용 건 안 **유효한** 같은 별칭이 있으면 409 `conflict`. **재응시**: previous_session_id는 그 세션이 failed(session)·시작 전 만료·cancelled일 때만(아니면 422 `invalid_previous_session`)이고, alias를 생략하면 이전 별칭을 그대로 쓴다. 이전 초대는 `superseded_at`이 찍혀 별칭 유일성 검사에서 빠진다 |
| POST | /admin/sessions/{id}/reissue | | {session_id, invite_url, expires_at, notice_text}. **초대 재발급(연장)**: status invited(만료 포함)인 세션만, 아니면 409 `conflict`. 같은 세션·같은 별칭을 유지하고 토큰 해시와 `expires_at`(now + 72h)만 교체, `reissued_at` 기록. 옛 링크는 404 |
| POST | /admin/sessions/{id}/cancel | | {status: "cancelled"}. invited·in_progress에서만(WS `session.ended{cancelled}`, `ended_at` 기록), 그 외 409 |
| GET | /admin/sessions/{id}/report | | Report(아래) 또는 404 |
| POST | /admin/sessions/{id}/report/regenerate | | {status: "completed"}. failed_stage=report만. 그 외 409 |
| POST | /admin/sessions/{id}/review | {adjustments: [{dimension_id, level: 1~5∣null, no_record_reason?, memo}], reviewer_name} | {status: "approving"}. 승인(검토 완료)과 차원 단위 조정을 한 트랜잭션으로 저장한다(`rubric_adjustments`). `reviewer_name` 필수(1~40자). `dimension_id`는 평가표 19개 차원 중 하나(`rubric.md` 3장). `level`이 null이면 `no_record_reason`(기록 없음 사유 코드) 필수, level이 있으면 사유 없음. **memo 필수**(빈 문자열 불가). 요소 수준은 조정된 차원으로 다시 계산한다. 생략 차원은 자동 값. adjustments가 빈 배열이면 조정 없이 승인. 검증 오류는 모두 422: 없는 dimension_id `invalid_dimension`, memo 없음 `memo_required`, 중복 `duplicate_dimension`, level 범위 밖·level과 사유 동시·둘 다 없음·사유 코드 밖·reviewer_name 없음 `invalid_input`. 판정 순서: 상태(409) → 검증(422). 이미 approving·reviewed: 본문 같으면 200 멱등, 다르면 409 `already_reviewed`. report 없거나 상태가 report_ready·approving·reviewed가 아니면 409 `conflict` |
| POST | /admin/sessions/{id}/report/notes | {text, reviewer_name} | {notes: [{id, text, reviewer_name, created_at}]}. approving·reviewed에서만 |
| GET | /admin/sessions/{id}/record | | [{t_min, type: message∣slot∣phase∣assistant_call∣material_view∣proposal_submit∣connection_gap, by, summary, ref: {type, id, t_min}}]. 전체 기록 읽기 전용, t_min 순. `proposal_submit` 줄의 `summary`에는 빈 칸 수와 빈칸 경고 확인 여부를 적는다(예: "제출 · 빈 칸 2개(경고 확인 후 제출)"). `ref`는 리포트 근거의 `record_ref`와 같은 값 |

`session_minutes`가 60·15 밖이면 422 `invalid_input`. 요청에 `elements`가 있으면 422 `invalid_input`(요소 선택 기능 없음). 모든 조회는 JWT의 company_id로 필터. 샘플 리포트는 web 정적 픽스처(`apps/web/fixtures/sample-report.json`, Report 형식). 인쇄·PDF는 web 인쇄 CSS.

### Report

예시는 발췌다(실제 본문은 `elements` 5행, `dimensions` 19행, 각 요소의 모든 차원). `position.name`은 내부 `GET /internal/sessions/{id}`의 `position.name`(`positions.name`)이다.

```json
{"session_id":"...","alias":"지원자A","stage":"draft",
 "position":{"name":"...","session_minutes":60},
 "seats":[{"seat":"candidate","display_name":"김지원"},{"seat":"p1","display_name":"강한결","avatar_url":"/assets/missions/debate/avatars/avatar-01.png","persona_type":"stubborn"},{"seat":"p2","display_name":"윤하람","avatar_url":"/assets/missions/debate/avatars/avatar-02.png","persona_type":"quiet"},{"seat":"p3","display_name":"서지안","avatar_url":"/assets/missions/debate/avatars/avatar-03.png","persona_type":"critic"}],
 "evaluation":{"run_id":"...","rubric_version":"...","prompt_versions":{"common":"<hash>","listening":"<hash>"},"model":"..."},
 "elements":[{"element":"listening","name":"경청/존중","level":3,"summary":"압박에 매번 내용으로 응답했으나 상대 근거 인정은 형식적이었습니다.",
              "dimension_count":4,"no_record_count":1,"low_confidence_count":0,"adjusted_level":null}],
 "dimensions":[{"element":"listening","dimension_id":"listen_engage","name":"응답성","level":4,"no_record_reason":null,
                "rationale":"세 번의 압박 중 두 번은 상대 근거를 받아 답함(앵커 4). 보조 장면과 같은 방향.","confidence":"high",
                "reviewer_hint":"상대 발언에 대체로 내용으로 응답했습니다","adjusted_level":null,"adjusted_no_record_reason":null,"adjust_memo":null,
                "evidence_refs":["msg:<m1>","msg:<m2>"],
                "evidence":[{"ref":"msg:<m1>","kind":"message","counted":true,"speaker":"candidate","phase":"problem","t_min":14.2,"origin":"spontaneous",
                             "quote":"침수 피해는 매년 반복돼서 우선순위가 높다고 봐요.",
                             "context":{"before":[{"id":"<m0>","sender":"p1","content":"...","t_min":13.9}],"after":[{"id":"...","sender":"p3","content":"...","t_min":14.5}]},
                             "record_ref":{"type":"message","id":"<m1>","t_min":14.2}},
                            {"ref":"msg:<m2>","kind":"message","counted":true,"speaker":"candidate","phase":"problem","t_min":18.0,"origin":"spontaneous",
                             "quote":"...","context":{"before":[],"after":[]},"record_ref":{"type":"message","id":"<m2>","t_min":18.0}}]},
               {"element":"listening","dimension_id":"listen_civility","name":"존중하는 반대","level":null,"no_record_reason":"no_activity",
                "rationale":"핵심 창 안 지원자 메시지 없음.","confidence":null,"evidence_refs":[],"evidence":[],
                "adjusted_level":null,"adjusted_no_record_reason":null,"adjust_memo":null}],
 "facts":{"message_count":{"total":24,"keyword":5,"problem":9,"solution":8,"proposal":2},"spontaneous_count":19,"invited_count":5,"spontaneous_ratio":0.79,
          "response_latency_median_sec":21,"intent_counts":{"propose":4,"agree":8,"oppose":3,"question":5,"other":4}},
 "contribution_check":[{"phase":"problem","option_id":"...","label":"도심 폭우·침수 피해 증가","first_proposer":"p3","credited_in_proposal":["p3"],"credit_quote":"문제 상황: 서지안 제안"}],
 "slots":[{"phase":"keyword","value":"물","option_id":"...","filled_by":"candidate","resolution":"consensus","outcome":"consensus","t_min":8.2,
           "first_proposer":"p3","support":[{"option_id":"...","label":"물","supporters":["candidate","p2","p3"]}]}],
 "cards":[{"card_id":"listening_pressure","element":"listening","fired_at":13.0,"delivered":true,"scene":"고집형 동료가 문제 상황 단계에서 자기 안을 강하게 밀어붙인 장면"}],
 "debrief":{"cards":[{"card_id":"listening_pressure","element":"listening","phase":"problem","fired":true,"fired_t_min":13.0,"window":{"start_min":13.0,"end_min":28.0}}],
            "survey":{"natural":4,"fair":3,"free_comment":null}},
 "proposal":{"submitted_at":"...","auto_submitted":false,"sections":{"keyword":"...","problem":"...","solution":"...","rationale":"...","expected_effect":"...",
             "idea_credit":"문제 상황: 서지안 제안. 해결책: 강한결 아이디어에 알림 기능을 제가 보탬"}},
 "ai_usage":{"used":true,"events":[{"call_id":"...","t_min":31.0,"request_quote":"...","response_quote":"...","cited_material_ids":["water_stats"]}]},
 "review":{"reviewer_name":"박담당","reviewed_at":"..."},"notes":[],"connection_gaps":[{"from_t_min":12.0,"to_t_min":13.5}],
 "generated_at":"...","reviewed_at":null,"purge_at":"..."}
```

| 위치 | 필드 | 규칙 |
|---|---|---|
| evaluation | | 이 리포트가 읽은 평가 실행(`evaluation_runs` 행)의 `run_id`·`rubric_version`·`prompt_versions`(`{common: 해시, <element>: 해시}`)·`model` |
| elements[] | `level`, `summary` | 5요소마다 한 행(`evaluation_runs.elements`). level = 수준이 있는 차원 평균을 반올림(.5 올림), 모두 기록 없음이면 null. 워커가 결정적으로 계산. summary는 평가 에이전트가 쓴 1~2줄(기록 없음 차원이 있으면 함께 밝힘). `dimension_count`·`no_record_count`·`low_confidence_count`. **요소 수준끼리 더한 총점·합계는 없다** |
| elements[] | `adjusted_level` | api가 GET 때 조정을 병합해 다시 계산한 요소 수준. 조정이 없으면 null. 자동 summary는 그대로 두고 화면이 "담당자 조정됨"을 표시 |
| dimensions[] | `level`, `no_record_reason`, `confidence`, `rationale`, `evidence_refs` | `evaluations` 행 그대로(`save_evaluation` 입력 형식). level과 no_record_reason은 둘 중 하나만. 기록 없음이면 confidence null. 사유 표시 문장은 `rubric.md` 5장. `confidence = low`는 화면에 "근거 약함, 원문 확인 권장" |
| dimensions[] | `name`, `reviewer_hint` | 차원 이름과 그 수준 행의 담당자 참고 문구(`positions.scenario`의 척도 복사본). 기록 없음이면 reviewer_hint 없음 |
| dimensions[] | `evidence[]` | `evidence_refs`마다 한 항목. `kind`: `message`(quote·speaker·origin·phase·t_min) ∣ `slot`(phase·value·resolution·filled_by·support) ∣ `proposal`(field·발췌) ∣ `contribution`(Contributions 행). `counted`는 근거 개수에 드는지(지원자 행동 단위만 true, AI 동료 메시지·contribution은 false, `hon_credit_record` 예외는 `rubric.md` 3.5). message 근거의 `context`는 `get_transcript_span`(앞 5·뒤 3)으로 만든 **앞뒤 맥락 표시용** 메시지다. 모두 `record_ref {type, id, t_min}`. 오피스 시각은 web이 `t_min`으로 변환 |
| dimensions[] | `adjusted_level`, `adjusted_no_record_reason`, `adjust_memo` | api가 GET 때 `rubric_adjustments`의 그 차원 마지막 행을 병합. 없으면 null. 최종값 = 조정 값이 있으면 그것, 없으면 자동 값 |
| facts | | 사실 지표. 키와 정의는 `rubric.md` 6장 표 그대로(`{<지표 id>: 값}`). 사실만으로 수준을 정하지 않는다 |
| contribution_check | | 채택된 칸 중 최초 제안자가 AI 동료인 안(사실 지표 `ai_adopted_units`)마다 실제 최초 제안자와 기획안 `idea_credit`에 적힌 기여자(`credited_in_proposal`, 워커 추출)·발췌. 정직 요소의 대조표이며 판단은 `hon_credit_record` 차원이 한다 |
| seats | | 첫 항목은 지원자 `{seat: "candidate", display_name}`, 나머지는 AI 자리 `{seat, display_name, avatar_url, persona_type}` |
| slots | `first_proposer` | 확정 안의 최초 제안자(`get_contributions`). option_id null이면 null |
| cards[] | `card_id`, `element`, `fired_at`, `delivered`, `scene` | 카드 6장마다 한 행. `fired_at`은 첫 카드 발언 게시 시각(세션 시작 기준 분, web이 오피스 시각으로 변환), 미발생이면 null. `delivered`는 담당 화자 전원이 게시했는지. 화면은 이 절에 담당자용 "설계된 장면" 표시를 붙인다(같은 채용 건 모든 지원자가 겪는 장면). `scene`은 카드의 고정 문장 `report_template`(`positions.scenario` 복사본) 그대로이며 **LLM이 만들지 않는다**. 판단이 아닌 장면 설명이라 화면의 "관련 카드 장면"·타임라인 카드 표시에 쓴다 |
| debrief | `cards`, `survey` | 발동 카드(`observations`)와 카드의 `window` 규칙(`scenario-model.md`)으로 워커가 계산한 관찰 창(미발생 카드는 `fired: false`), 종료 설문 답(없으면 null) |
| ai_usage | | 판단 기준 없음, 면접 확인용. 시간순 사실만 |

`evaluation`·`elements`(adjusted_level 제외)·`dimensions`(조정 필드 제외)·`facts`·`contribution_check`·`slots`·`cards`·`debrief.cards`는 워커가 draft에 넣는다. 조정 필드·`review`·`notes`·`connection_gaps`·`purge_at`·`proposal`·`debrief.survey`는 api가 GET 때 병합한다. 저장된 `reports.content`는 불변이고 해시는 content에만 적용한다. **final은 승인된 draft content를 그대로 저장한다(해시 동일)**. 담당자 조정은 final content에 굽지 않고 GET 때 병합한다(draft·final 모두 같은 병합 규칙). 텍스트 필드(`summary`·`rationale`)에는 합격·불합격·순위·추천·평가표 밖 점수 표현이 없어야 한다(워커 금지어 검사). 모든 `evidence_refs`는 같은 세션의 실제 행이어야 한다(api가 `save_evaluation` 저장 전에 검증). 요소 수준을 더한 총점·합계는 어디에도 없다.

### 근거 참조 (`evidence_refs[]`)

문자열 하나가 근거 하나다. 형식 밖이거나 같은 세션의 실제 행이 아니면 워커 검증 실패.

| 형식 | 가리키는 것 | 개수에 듦 |
|---|---|---|
| `msg:<message_id>` | room 메시지. 지원자 메시지면 근거 단위, AI 동료·시스템 메시지면 맥락 | 지원자 메시지만 |
| `slot:<phase>` | 지원자가 확정한 칸(`filled_by = candidate`) | 예 |
| `proposal:<field>` | 제출 기획안 필드(`idea_credit` 등, 필드 id는 `scenario-model.md` 템플릿) | 예 |
| `contribution:<option_id>` | Contributions 대조표 행(맥락) | 아니오(`hon_credit_record` 예외, `rubric.md` 3.5) |

최소 개수(수준 1~3은 1개, 4·5는 서로 다른 단위 2개)와 확신도 상한은 `rubric.md` 2.2·2.4.

## 지원자 REST (`/s`, `/sessions`, 포트 8000)

| 메서드 | 경로 | 요청 | 응답 |
|---|---|---|---|
| GET | /s/{token} | | {session_id, company_name, duration_minutes, status, default_display_name, elements_names, entry_notice, contact_email, debrief_token?, failed_stage?} 또는 410 `expired`∣`cancelled`. `default_display_name`은 초대 별칭(입장 화면 이름 칸의 기본값). 모르는 토큰(재발급으로 바뀐 옛 토큰 포함) 404 `not_found` |
| POST | /s/{token}/consent | {display_name?} (1~20자, 기본값은 초대 별칭. 공백 정리·마스킹. 빈 값이면 별칭) | {session_token, session_id}. 동의 중복은 멱등(마지막 display_name, 시작 전까지만) |
| POST | /s/{token}/resume | | {session_token, session_id} (in_progress만, 아니면 409) |
| POST | /s/{token}/start | Bearer | {session_id, started_at, ends_at, phase: "keyword"} (멱등) |
| GET | /sessions/{id}/state | Bearer | State 스냅샷(아래). 시작 전(invited, 동의 뒤)에도 200: `session.status = invited`, 시계 필드 null, `participants`·`phases`·빈 `slots`, 나머지 빈 값 |
| POST | /sessions/{id}/slots/{phase}/confirm | Bearer {value, option_key?} | {slot, phase: <다음 단계>}. 현재 단계만. keyword는 `option_key` 필수(후보 키, 밖이면 422 `invalid_keyword`, `value`는 그 후보 라벨로 저장), problem·solution은 value 필수(비면 422)이고 `option_key`는 선택. 안 연결은 위 "칸 상태"의 결정적 규칙. filled_by=candidate, resolution=consensus, support 스냅샷 저장 → 단계 전환(WS `slot.confirmed`·`phase.changed`·`timer`, keyword면 `materials.opened`). 다른 단계 409 `phase_not_open`, 이미 확정 409 `slot_confirmed`(같은 값 재요청은 200 기존 결과) |
| GET | /sessions/{id}/materials | Bearer | {locked: bool, keyword: string∣null, materials: [{material_id, title}]}. keyword 칸 확정 전이면 locked=true·빈 목록. 확정 뒤에는 그 키워드의 자료(keyword 칸은 후보 4개 중에서만 확정되므로 항상 자료 세트가 있다). 목록·본문·검색은 모두 채용 건의 `catalog_version`으로 `materials` 테이블에서 읽는다(카탈로그 파일을 직접 읽지 않음) |
| GET | /sessions/{id}/materials/{material_id} | Bearer | {material_id, title, content(Markdown)} 또는 423 `not_released`(열리지 않은 자료). 같은 `catalog_version`의 본문. 열람을 `material_views`에 기록 |
| POST | /sessions/{id}/assistant | Bearer {prompt} | {call_id, message_id, content, cited_material_ids, tool_calls: [{name, query?, material_id?}]} 또는 429 `assistant_limit`(세션 60회 초과). 어시스턴트는 tool-calling 루프(`search_materials`·`get_material`, 요청당 도구 최대 3회)로 열린 자료만 보고, 답에는 인용한 자료 id를 붙인다 |
| GET | /sessions/{id}/proposal | Bearer | Proposal {sections, revision, updated_at, submitted_at} |
| PUT | /sessions/{id}/proposal | Bearer {sections, revision} | {revision, updated_at}. 디바운스 저장. in_progress 언제든. `revision`이 현재 값과 다르면 409 `conflict`(다른 탭 덮어쓰기 방지, 화면은 최신을 다시 읽음) |
| POST | /sessions/{id}/proposal/submit | Bearer {blank_warning_shown?: bool} | {status: "completed", completed_at, submitted_at}. phase=proposal에서만(아니면 409 `phase_not_open`). 저장 대기분을 먼저 PUT한 뒤 호출. 현재 초안을 제출본으로 고정 → completed → WS `session.ended{submitted}`. 멱등(completed 이후 재호출은 저장된 값). 화면은 "제출하면 수정할 수 없어요" 확인 창을 거친다. 빈 칸(`sections` 값이 공백뿐)은 api가 제출본에서 직접 계산해 `proposals.submit_blank_sections`에 저장한다(수동·자동 제출 모두, 빈 칸이 없으면 `[]`). 클라이언트가 빈칸 경고 창을 보여 준 뒤 제출했으면 `blank_warning_shown: true`를 보내고, 수동 제출에서 생략하면 false로 저장한다(`proposals.blank_warning_shown`, 자동 제출이면 null). 두 값은 제출 전 null이고 제출 때 한 번 쓰며 멱등 재호출로 바뀌지 않는다. 빈 칸이 있어도 제출은 막지 않는다 |
| GET | /sessions/{id}/debrief | Bearer(세션 JWT 또는 debrief_token) | {intro_notice, elements: [{element, name, how_we_see}] (5요소의 이름과 "이렇게 봅니다" 한 줄, `/admin/catalog` 요소 카드와 같은 문구), cards: [{card_id, element, name, description}] (실제 발동한 카드만, 원천은 `observations`), seats: [{seat: "candidate", display_name}, {seat, display_name, avatar_url, persona_type, persona_description}] (AI 동료가 성향을 가진 AI였다는 설명), my_messages: [{id, content, phase, t_min}], scoring_notice, appeal_contact, connection_gaps, retention_notice, contact_email, proposal: {sections}∣null, view_until(`ended_at` + 7일), survey: {submitted, questions: [{q, text, kind: "scale"∣"text"}]}, failed_stage?}. `intro_notice` 첫 문장은 고정("같은 채용 건의 모든 지원자가 같은 장면을 겪었고, 정답 없이 반응을 본다"). `my_messages`는 지원자 발언 2~3개의 읽기 전용 회고: 토론 단계마다 가장 긴 지원자 메시지 하나씩(최대 3개, 결정적 선택). `appeal_contact`는 이의 제기 연락처 문자열. **척도 세부(차원·수준 앵커)와 평가 결과는 디브리핑에 내려가지 않는다.** 세션 실패면 elements·cards·seats·proposal·my_messages 없이 중단·재응시 안내만 |
| POST | /sessions/{id}/debrief/survey | Bearer(세션 JWT 또는 debrief_token) {answers: [{q: "natural"∣"fair", value: 1~5}], free_comment?: string(500자 이내)} | {submitted: true}. 한 번만 저장(멱등) |

제출 이후 쓰기(메시지·칸·기획안·어시스턴트)는 전부 409 `session_ending`(WS는 오류 프레임 `session_ending`). 디브리핑 기한 = `ended_at` + 7일, 지나면 410 `expired`.

### Proposal

```json
{"sections":{"keyword":"물","problem":"...","solution":"...","rationale":"...","expected_effect":"...",
             "idea_credit":"문제 상황: 서지안 제안. 해결책: 강한결 아이디어에 알림 기능을 제가 보탬"},
 "revision":7,"updated_at":"...","submitted_at":null}
```

- 템플릿 6칸: 키워드 · 문제 상황 · 해결책 · 근거 · 기대효과 · 아이디어 기여. 앞 셋은 proposal 단계 시작 때 비어 있으면 확정 칸 값으로 채운다(지원자가 고칠 수 있음).
- `idea_credit`: 누가 어떤 아이디어를 냈는지 지원자가 자유 문장으로 적는 칸. 화면 안내는 중립적으로 "이 기획에 반영된 의견과 그 의견을 낸 사람"만 쓴다. 평가 에이전트가 `proposal:idea_credit` 근거로 읽고, 워커가 `get_contributions`와 대조해 `contribution_check`를 만든다. 모든 필드는 문자열.

### State 스냅샷

```json
{"session":{"id":"...","alias":"지원자A","status":"in_progress","phase":"problem","started_at":"...","ends_at":"...","session_minutes":60,
            "phase_started_at":"...","phase_deadline_at":"...","phase_remaining_seconds":840,"session_remaining_seconds":2700,
            "office_start":"09:00","office_end":"10:00","completed_at":null},
 "keyword_options":[{"option_key":"water","label":"물"},{"option_key":"fire","label":"불"},{"option_key":"tree","label":"나무"},{"option_key":"wind","label":"바람"}],
 "phases":[{"phase":"keyword","budget_min":10,"deadline_t_min":10},{"phase":"problem","budget_min":18,"deadline_t_min":28},
           {"phase":"solution","budget_min":18,"deadline_t_min":46},{"phase":"proposal","budget_min":14,"deadline_t_min":60}],
 "participants":[{"id":"candidate","display_name":"김지원"},{"id":"p1","display_name":"강한결","avatar_url":"/assets/missions/debate/avatars/avatar-01.png"},
                 {"id":"p2","display_name":"윤하람","avatar_url":"/assets/missions/debate/avatars/avatar-02.png"},{"id":"p3","display_name":"서지안","avatar_url":"/assets/missions/debate/avatars/avatar-03.png"}],
 "slots":[{"phase":"keyword","status":"confirmed","value":"물","filled_by":"candidate","resolution":"consensus","outcome":"consensus","t_min":8.2},
          {"phase":"problem","status":"empty","value":null,"filled_by":null,"resolution":null,"outcome":null,"t_min":null},
          {"phase":"solution","status":"empty","value":null,"filled_by":null,"resolution":null,"outcome":null,"t_min":null}],
 "messages":[{"id":"...","sender":"p1","content":"...","phase":"problem","is_invite":false,"t_min":9.0,"created_at":"..."}],
 "materials":{"locked":false,"keyword":"물","materials":[{"material_id":"water_stats","title":"물 부족 통계"}]},
 "proposal":{"sections":{"keyword":"","problem":"","solution":"","rationale":"","expected_effect":"","idea_credit":""},"revision":0,"updated_at":"...","submitted_at":null},
 "assistant":[{"call_id":"...","request":"...","response":"...","cited_material_ids":[],"t_min":4.0}],
 "typing":["p2"],
 "active_runs":[{"run_id":"...","stimulus":"message"}],
 "connection_gaps":[],
 "ws_seq":143}
```

스냅샷이 전체 상태이고 WS는 증분만 보낸다. `participants`의 지원자는 `display_name`만, AI 자리는 `display_name`·`avatar_url`(유형 없음). 칸의 `support`와 안·지지 현황은 지원자 화면에 내려가지 않는다(합의 패널은 고른 결과만). `keyword_options`는 키워드 단계 후보 버튼(카탈로그 `keyword_order` 순, 시작 전 `/state`에도 있음)이고 칸 확정의 `option_key`는 이 값 중 하나다. `typing`은 지금 입력 중 표시가 켜진 AI 자리. `ws_seq`는 스냅샷 시점까지 이 세션에 보낸 마지막 WS `seq`이고, 클라이언트는 이보다 큰 seq의 프레임만 적용한다.

## WebSocket `/ws/sessions/{id}?token=<세션 JWT>`

프레임 봉투: `{"type": <이름>, "seq": <int>, "payload": {...}}`. `seq`는 세션 단위로 1씩 늘고(서버 → 클라이언트 프레임만), 모든 서버 프레임은 **세션별 단일 송신 큐** 하나로만 나간다(순서 보장). 클라이언트는 받은 seq가 마지막 seq + 1이 아니면(빠짐) 프레임 적용을 멈추고 `/state`를 다시 읽어 `ws_seq`부터 이어 간다. 카운터는 프로세스 메모리 값이라 api 재시작 뒤 0부터 다시 시작하며, 재시작은 연결이 끊기므로 클라이언트는 재연결 뒤 항상 `/state`를 먼저 읽는다.

서버 → 클라이언트:

| type | payload |
|---|---|
| message.ack | {client_msg_id, message_id, run_id}. 메시지 저장 커밋 직후, 의도 분류 전에 보낸다 |
| message.new | Message = {id, sender: candidate∣p1∣p2∣p3∣system, content, phase, is_invite, t_min, created_at}. 합의·시간 초과 채우기 공지는 `slot.confirmed` 바로 앞에 온다 |
| typing | {participant: p1∣p2∣p3, state: "start"∣"stop"}. 화면 "OO님이 입력 중…". start 뒤 30초 안에 stop이 없으면 화면이 끈다 |
| slot.confirmed | {phase, value, filled_by, resolution: "consensus"∣"timeout", outcome: "consensus"∣"candidate_decision"∣"timeout", t_min} |
| phase.changed | {phase, previous_phase, reason: "start"∣"confirmed"∣"timeout", phase_started_at, phase_deadline_at, t_min} |
| timer | {phase, phase_deadline_at, phase_remaining_seconds, session_remaining_seconds}. 단계 전환 때와 60초마다(시계 보정). 화면은 로컬로 카운트다운 |
| materials.opened | {keyword, materials: [{material_id, title}]} |
| session.ended | {reason: "submitted"∣"timeout"∣"failed"∣"cancelled"}. submitted·timeout이면 이미 completed. 화면은 입력을 잠그고 [나가기]로 디브리핑(API 호출 없음) |
| session.replaced | {} 뒤 close 4000 |
| error | {code: `session_ending`∣`conflict`∣`invalid_input`, message} |

클라이언트 → 서버:

| type | payload |
|---|---|
| message.send | {client_msg_id, content}. 토론방 하나라 채널 없음. 같은 client_msg_id 재전송은 기존 메시지로 ack. in_progress의 모든 단계에서 허용(proposal 단계 포함) |
| typing | {state: "start"∣"stop"}. 지원자 입력 중 여부. 입력창에 글자가 있는 동안 **5초마다 `start`를 다시 보내 갱신**하고, 비거나 전송하면 `stop`. 서버는 저장하지 않고 메모리에 `candidate_typing_until = 마지막 start + 6초`를 둔다. `stop`이나 6초 동안 갱신 없음이면 입력 중이 아니다. 끼어들기 대기(최대 10초 뒤 미게시·재큐)와 스케줄러 enqueue 보류에만 쓴다 |

close code: 4401(토큰 문제 → resume 후 재연결), 4403(다른 세션, 재연결 안 함), 4000(교체됨, 재연결 안 함). 같은 세션에 WS가 둘이면 마지막만 유효. 연결 없는 구간은 `connection_gaps`에 기록(평가하지 않음. 사실 지표·확신도 참고).

## 내부 REST (`/internal`, 포트 8001, X-Internal-Token)

| 메서드 | 경로 | 요청 | 응답 | 호출자 |
|---|---|---|---|---|
| GET | /internal/sessions/{id} | | {id, status, phase, alias, display_name, position: {name, mission_id, session_minutes, scenario, catalog_version}, seats: [{seat: "candidate", display_name}, {seat, display_name, avatar_url, persona_type}], started_at, ends_at, phase_started_at, phase_deadline_at, completed_at, ended_at, t_min_now, generation, invite_delivered_phases, card_progress, connection_gaps} | debate-mcp, assessment-mcp, 워커 |
| GET | /internal/sessions/{id}/debate_state | | DebateState(아래) | debate-mcp |
| GET | /internal/sessions/{id}/messages?since_t_min=&phase=&limit=&offset=&tail= | | [Message + `meta`, `origin`, `intent`(message_intents 행 또는 null)]. 토론방(room) 메시지만. 정렬 created_at·seq, limit 기본 200·최대 1000. `tail=N`(1~1000)이면 최근 N개를 오래된 순으로 주고 limit·offset은 무시한다(debate-mcp `get_transcript`의 `tail`) | debate-mcp, assessment-mcp, 워커 |
| POST | /internal/sessions/{id}/messages | {sender: p1∣p2∣p3∣system, content, run_id, seq, expected_generation?: int, is_invite?: bool, card_ids?: [card_id], cited_material_ids?: [], meta?} | Message. (run_id, seq) 멱등(이미 있으면 generation 검사 없이 기존 행). `expected_generation`이 있고 현재 `sessions.generation`과 다르면 409 `stale_generation`(게시 안 함). is_invite=true면 그 단계를 `invite_delivered_phases`에 추가, 단계당 두 번째는 409 `conflict`. `card_ids`의 카드마다 그 `session_cards.delivered_seats`에 sender 자리를 더한다(같은 자리 중복 없음, 같은 트랜잭션). 메시지 행에는 `card_ids`로 저장 | debate-mcp |
| POST | /internal/sessions/{id}/options | {phase, label, proposer: p1∣p2∣p3, scenario_option_key?, source_message_id, run_id} | Option {option_id, phase, label, proposer, scenario_option_key, created_at, existing: bool}. 멱등 키는 위 표. 같은 scenario_option_key 행이 이미 있으면(지원자가 먼저 말한 경우 포함) 새로 만들지 않고 기존 행(`existing: true`, proposer 그대로). 현재 단계가 아니면 409 `phase_not_open` | debate-mcp |
| POST | /internal/sessions/{id}/stances | {participant: p1∣p2∣p3, option_id, stance: "support"∣"oppose", source_message_id, run_id} | {stance_id}. source_message_id는 그 입장을 말한 자기 메시지. 멱등 | debate-mcp |
| POST | /internal/sessions/{id}/slots/fill | {option_id, seat: p1∣p2∣p3, content, run_id} | {slot, message, phase: <다음 단계>}. **AI 합의 채우기 전용**(`resolution: consensus`, `filled_by` = seat). 대상 단계는 그 option의 phase다. 판정 순서: 같은 run_id로 이미 확정된 칸이 있으면 단계와 상관없이 기존 칸·공지(200) → option의 phase가 현재 단계가 아니면 409 `phase_not_open` → 칸이 이미 confirmed면 409 `slot_confirmed` → `consensus.judge` 결과가 이 option_id가 아니면 409 `no_consensus`. 성공은 한 트랜잭션: 칸 confirmed → `content`를 공지 메시지로 저장(sender = seat, run_id, seq 5, `meta.kind = "consensus_fill"`) → `advance_phase`(generation +1). 커밋 뒤 WS `message.new` → `slot.confirmed` → `phase.changed` → `timer`(keyword면 `materials.opened`). 409면 아무것도 저장하지 않는다. 시간 초과 채우기는 api 스케줄러가 직접 하므로 이 경로가 없다 | debate-mcp |
| GET | /internal/sessions/{id}/proposal | | Proposal(in_progress면 현재 초안, completed 이후면 제출본. `submitted_at`·`auto_submitted` 포함) | debate-mcp, assessment-mcp, 워커 |
| GET | /internal/sessions/{id}/materials | | {catalog_version, locked, keyword_key∣null, materials: [{material_id, title}]} | rag-mcp |
| GET | /internal/sessions/{id}/materials/{material_id} | | {material_id, title, content} 또는 423 `not_released`. 채용 건 `catalog_version`의 `materials` 행 | rag-mcp |
| POST | /internal/sessions/{id}/observations | {card_id, phase, trigger_message_id?, run_id} | {observation_id, fired_at, t_min}. (session_id, card_id) 멱등. 카드의 첫 발언 게시 뒤(`trigger_message_id` = 그 메시지), `honesty_credit`은 기획안 단계 `phase_started`에서(`trigger_message_id` = 단계 시작 시스템 안내). element는 api가 카드에서 정한다 | assessment-mcp |
| GET | /internal/sessions/{id}/observations | | [{observation_id, card_id, element, phase, fired_at, t_min, trigger_message_id, delivered: bool}] (`delivered`는 `session_cards` 기준) | assessment-mcp, 워커 |
| GET | /internal/sessions/{id}/transcript_span?message_id=&before=5&after=3 | | {target: Message, before: [Message], after: [Message]}. room 메시지만, meta·intent 포함. 기본 앞 5·뒤 3. 리포트 근거의 앞뒤 맥락 표시용(평가 입력을 자르는 용도가 아님) | assessment-mcp |
| GET | /internal/sessions/{id}/contributions | | Contributions(아래) | assessment-mcp |
| GET | /internal/sessions/{id}/rubric | | {rubric_version, elements: [{element, name, dimensions: [{dimension_id, name, definition, core_cards: [card_id], levels: [{level: 1~5, anchor, reviewer_hint}]}]}], no_record_reasons: [{code, label}], cards: [{card_id, element, stage_id, window: {start: stage_start∣card_message, end: "stage_end:<phase>"∣submit, label}}]} (`positions.scenario`에 복사된 BARS 척도, 5요소·19차원, 형식은 `rubric.md`. `window`는 `cards.yaml` 값 그대로이며 관찰 창이지 평가 입력을 자르는 경계가 아니다) | assessment-mcp |
| POST | /internal/sessions/{id}/evaluations | `save_evaluation` 입력에서 session_id를 뺀 본문(아래 EvaluationSave) | {run_id, existing: bool, saved: int}. `evaluation_runs` 1행 + `evaluations` 차원 행을 **한 트랜잭션**으로 저장. (session_id, run_id)에 행이 있으면 저장하지 않고 `existing: true`(재시도 이어하기). api 검증 실패 422 `invalid_input`(아래 "검증 경계") | assessment-mcp |
| GET | /internal/sessions/{id}/evaluations?run_id= | | {run_id, rubric_version, prompt_versions, model, elements: [ElementSummary], dimensions: [DimensionEvaluation], has_failed: bool, created_at}. run_id 생략 시 최신 실행. 요소 요약이 함께 오므로 저장 직후 장애가 나도 재실행이 체크포인트 없이 복구한다 | 워커 |
| GET | /internal/sessions/{id}/facts | | {<지표 id>: 값} (`rubric.md` 6장 사실 지표의 규칙 계산 값. 평가 결과를 쓰지 않음) | assessment-mcp, 워커 |
| GET | /internal/sessions/{id}/slots | | [slot 전체 필드 + support] | assessment-mcp, 워커 |
| GET | /internal/sessions/{id}/assistant_calls | | [{id, request_message_id, response_message_id, request, response, cited_material_ids, created_at}]. `request`·`response`는 어시스턴트 대화 원문(text)이고 워커가 Report `ai_usage`의 `request_quote`·`response_quote`를 여기서 만든다(내부 messages는 토론방만 준다) | 워커 |
| POST | /internal/sessions/{id}/report/draft | {content, usage?} | {status: "report_ready"} (멱등) | 워커 |
| POST | /internal/sessions/{id}/report/final | {content} | {status: "reviewed", reviewed_at}. content는 승인된 draft content 그대로(조정 병합하지 않음). 해시가 draft와 다르면 409 `draft_mismatch` | 워커 |
| POST | /internal/sessions/{id}/report_failed | {error} | {status: "failed"} | 워커 |
| POST | /internal/test/sessions | {session_minutes: 60∣15, alias?, company_id?, admin_email?, start_at?: entry∣keyword∣problem∣solution∣proposal∣ended, stage?} | {session_id, token, invite_url, phase, session_token?, debrief_token?, admin_report_url?}. `start_at` 기본 `entry`(초대만 만든 상태). 그 밖이면 단계 시드 `scenarios/e2e/stages/<stage∣start_at>.yaml`의 행동을 SessionService로 재생해(가짜 시계, LLM 없음) 그 단계가 막 시작된 in_progress 세션을 만들고 `session_token`을 준다. `ended`는 제출까지 재생한 completed 세션이고 `debrief_token`·`admin_report_url`을 준다(리포트는 워커가 평소대로 만든다). 단계 마감은 재생이 끝난 시각 기준으로 다시 잡는다 | e2e, stage-kit |
| POST | /internal/test/sessions/{id}/advance | {seconds?: int, to?: deadline∣idle∣"card:<card_id>"} | {shifted_seconds, phase, phase_deadline_at, ends_at}. in_progress 세션의 `started_at`·`phase_started_at`·`phase_deadline_at`·`ends_at`을 같은 초만큼 앞당겨 시간이 흐른 것처럼 만든다(스키마 변경 없음, 카드 예정 시각은 시작 시각 기준이라 함께 당겨짐). `to`는 그 시점에 닿는 초를 api가 계산한다(`deadline` = 현재 단계 마감, `idle` = 침묵 초대 조건, `card:<id>` = 그 카드 예정 시각). 처리는 다음 스케줄러 틱이 평소대로 한다. 둘 다 없거나 둘 다 있으면 422 | e2e, stage-kit |

`/internal/test/*`는 `ENABLE_TEST_API=1`일 때만 열리고 아니면 404다(운영 compose에서는 끈다). 내부 읽기는 상태 제한이 없다. 내부 쓰기는 세션이 in_progress일 때만 받고 아니면 409 `conflict`(이미 저장된 키의 재전달은 기존 결과). 단, `evaluations`·`report/*`는 completed 이후에만 받는다.

### DebateState

```json
{"phase":"problem","generation":12,"phase_deadline_at":"...","phase_remaining_seconds":840,
 "slot":{"phase":"problem","status":"empty","value":null},
 "options":[{"option_id":"...","label":"도심 폭우·침수 피해 증가","proposer":"p3","scenario_option_key":"water_p2","created_at":"...",
             "supporters":["p1","p3"],"opposers":["candidate"]}],
 "catalog_options":[{"scenario_option_key":"water_p1","label":"...","spoken":false}],
 "current_support":{"candidate":"...","p1":"...","p2":null,"p3":"..."},
 "consensus_option_id":null,"timeout_option_id":"...",
 "candidate":{"spoke_in_phase":true,"last_message_t_min":11.2,"typing":false},
 "invite_delivered":false,"last_room_message_t_min":11.4,
 "confirmed":[{"phase":"keyword","value":"물","option_id":"...","resolution":"consensus","filled_by":"candidate"}],
 "card_progress":[{"card_id":"<card_id>","locked_option_id":"...","delivered":["p1"]}],
 "cost_left":1.79}
```

`consensus_option_id`는 합의 판정 결과(없으면 null), `timeout_option_id`는 지금 마감되면 고를 안. 턴 매니저는 이 값을 그대로 쓴다. `card_progress`는 `session_cards` 행(처리가 시작된 카드)의 잠긴 기준안과 전달된 자리이고, 결정적 노드가 아직 전달되지 않은 담당 화자를 다음 run의 화자로 이어서 넣는다. **페르소나 컨텍스트에는 `card_progress`·`cost_left`를 넣지 않는다**(카드 brief와 자기 입장 계획만 그 화자에게). `cost_left` = `SESSION_COST_HARD_USD`(기본 $2) − `sessions.debate_cost_usd`(리포트 비용 제외, `services/budget.py`가 계산)이고 0 이하면 페르소나는 LLM 없이 고정 안전 문구만 게시한다. 그래프 `load`는 위 필드를 걸러 낸 DebateState를 페르소나 컨텍스트에 미리 넣어 조회 도구 왕복을 줄인다.

### Contributions

```json
{"options":[{"option_id":"...","phase":"problem","label":"도심 폭우·침수 피해 증가","first_proposer":"p2","source_message_id":"...","t_min":12.3,"adopted":true}],
 "slots":[{"phase":"problem","option_id":"...","first_proposer":"p2","filled_by":"candidate","resolution":"consensus"}]}
```

최초 제안자 = 그 안 행의 proposer(안 행은 처음 말한 순간 한 번만 만들어진다). 정직 대조의 근거.

### SessionRecord (`get_session_record` 출력)

평가 에이전트의 입력 묶음이다. **세션 대화 전체**를 담고 카드 관찰 창으로 자르지 않는다(`rubric.md` 1.1).

```json
{"session":{"id":"...","elements":["persuasion","listening","inclusion","flexibility","honesty"],"session_minutes":60,"started_at":"...","completed_at":"...","connection_gaps":[]},
 "seats":[{"seat":"candidate","display_name":"김지원"},{"seat":"p3","display_name":"서지안","persona_type":"critic"}],
 "messages":[{"id":"...","sender":"candidate","content":"...","phase":"problem","t_min":14.2,"origin":"spontaneous","is_invite":false,"card_ids":[],
              "intent":{"intent":"oppose","target_option_id":"...","addressed_to":["p2"]}}],
 "slots":[{"phase":"problem","value":"...","option_id":"...","filled_by":"candidate","resolution":"consensus","support":[],"t_min":28.0}],
 "proposal":{"sections":{"idea_credit":"..."},"submitted_at":"...","auto_submitted":false},
 "observations":[{"card_id":"listening_pressure","element":"listening","phase":"problem","t_min":13.0,"trigger_message_id":"...","delivered":true,"window":{"start_min":13.0,"end_min":28.0}}],
 "facts":{"message_count":{"total":24}},
 "contributions":{"options":[],"slots":[]}}
```

- `messages`는 room 채널 전체(시간순), 지원자 메시지에만 `origin`·`intent`. 어시스턴트 채널은 넣지 않고 `facts.assistant_calls`로만 보인다.
- `observations[].window`는 카드의 `window` 규칙(`scenario-model.md` 4.2)으로 계산한 핵심 장면 위치다. 입력 경계가 아니다. `trigger_message_id`는 카드 첫 발언(장면을 찾는 용도), `delivered`는 담당 화자 전원 게시 여부.
- `seats[].persona_type`은 장면을 찾는 용도로만 넣는다(관리자·워커 전용).

### EvaluationSave (`save_evaluation` 입력)

예시는 발췌다(실제 본문은 19개 차원 행과 5개 요소 행).

```json
{"session_id":"...","run_id":"...","rubric_version":"...","prompt_versions":{"common":"<hash>","persuasion":"<hash>","listening":"<hash>","inclusion":"<hash>","flexibility":"<hash>","honesty":"<hash>"},"model":"...",
 "dimensions":[{"dimension_id":"listen_engage","level":4,"evidence_refs":["msg:<m1>","msg:<m2>","msg:<m0>"],
                "rationale":"세 번의 압박 중 두 번은 상대 근거를 받아 답함(앵커 4).","confidence":"high"},
               {"dimension_id":"listen_civility","level":null,"no_record_reason":"no_activity","evidence_refs":[],
                "rationale":"핵심 창 안 지원자 메시지 없음.","confidence":null}],
 "elements":[{"element":"listening","level":4,"summary":"...","dimension_count":4,"no_record_count":1}]}
```

| 필드 | 값 |
|---|---|
| run_id | 평가 실행 id. 워커가 `uuid5(session_id, "evaluate:" + eval_round)`로 정한다. `eval_round`는 큐 메시지 `report.generate`의 값(첫 발행 1). 큐 재시도는 같은 round라 같은 평가를 재사용한다. 리포트 재생성 때 api는 최신 `evaluation_runs.has_failed`가 true면 `sessions.eval_round`를 +1(새 run_id로 다시 평가), 아니면 그대로(재사용) 두고 그 값으로 발행한다. 파일럿 재실행 안정성 측정만 별도 run_id를 쓴다 |
| rubric_version, prompt_versions, model | 척도 버전(`get_rubric`), 평가 프롬프트 버전 맵 `{common: prompts/evaluator/common.md 해시, <element>: prompts/evaluator/<element>.md 해시}`(5요소 모두), `MODEL_EVALUATOR` 모델 이름. 단일 `prompt_version` 필드는 없다 |
| dimensions[] (DimensionEvaluation) | `dimension_id`(19개 차원마다 정확히 한 행) · `level` 1~5 ∣ null · `no_record_reason`(level null일 때만): `no_activity` ∣ `evaluate_failed` ∣ `not_applicable` ∣ `event_not_fired` ∣ `auto_submitted_blank` · `evidence_refs[]`(위 "근거 참조" 형식) · `rationale` 1~3문장 · `confidence` `high`∣`medium`∣`low`, 기록 없음이면 null |
| elements[] (ElementSummary) | `element` · `level`(워커가 차원 평균 반올림, .5 올림, 모두 기록 없음이면 null) · `summary`(평가 에이전트 1~2줄) · `dimension_count` · `no_record_count` |

**검증 경계** (항목마다 실행 주체 하나):

| 검증 | 주체 | 실패 시 |
|---|---|---|
| 본문 스키마·타입, 19개 차원이 빠짐없이 한 행씩(중복·없는 id 없음), level 1~5와 `no_record_reason` 배타·사유 코드 값, 기록 없음이면 confidence null, 요소 5행 | api(저장 전) | 422 `invalid_input`, 저장 안 함 |
| 모든 `evidence_refs`가 형식 4종이고 **같은 세션의 실제 행** | api(저장 전) | 422 `invalid_input` |
| LLM 출력 형식 오류(파싱·스키마, 위 api 항목과 같은 규칙을 저장 전에 미리 봄), level이 있는데 지원자 근거 단위 0개(`rubric.md` 2.2) | 워커(저장 전) | 그 **요소**를 차원별 거부 사유와 함께 1회 다시 요청 → 그래도 실패한 차원만 `evaluate_failed`(`rationale`에 사유 코드) |
| level 4·5인데 서로 다른 지원자 근거 단위 1개(`rubric.md` 2.2) | 워커 | 거부하지 않고 level 3·confidence 최대 medium으로 깎는다, `rationale` 끝에 상한 적용 표시 |
| 확신도 상한(`rubric.md` 2.4) | 워커 | 거부하지 않고 상한으로 깎는다(clamp), `rationale`은 그대로 |
| 요소 level = 차원 평균 반올림(.5 올림) | 워커가 계산해 채움 | — (모델 값을 쓰지 않음) |
| `rationale`·`summary` 금지어(합격·불합격·순위·추천·점수) | 워커 | 그 요소 1회 재요청 → 실패 차원 `evaluate_failed`, 실패한 summary는 고정 문장 |

차원 행은 `evaluations`, 실행 메타와 요소 요약(`elements`)은 `evaluation_runs`에 한 트랜잭션으로 저장한다. draft는 `GET /evaluations`에서 둘을 함께 읽어 만든다(체크포인트에 의존하지 않음).

**평가 호출 규칙**: 요소마다 별도 LLM 호출(`MODEL_EVALUATOR`, temperature 0~0.2), 다른 요소의 결과는 입력에 넣지 않는다. 재요청은 **요소 단위 1회**(형식 오류·근거 부재일 때)이고, 그래도 실패한 차원은 `level: null, no_record_reason: "evaluate_failed"`(화면 문구는 `rubric.md` 5장)로 저장한다. **LLM 전송 실패·타임아웃은 저장하지 않고** 예외로 올려 큐 재시도(`attempt+1`)에 맡긴다. 워커는 근거를 고쳐 쓰지 않는다. 예외는 근거 1개인 수준 4·5의 상한(수준 3·확신도 최대 medium)과 확신도 clamp뿐이다.

## MCP 도구

세 서버 모두 Python FastMCP, Streamable HTTP. 도구 함수는 모두 `async def`다(FastMCP는 동기 도구를 워커 스레드에서 실행한다). 클라이언트(api 그래프·report-worker)는 env로 접속한다: `DEBATE_MCP_URL`(기본 `http://debate-mcp:9101/mcp`), `RAG_MCP_URL`(기본 `http://rag-mcp:9102/mcp`), `ASSESSMENT_MCP_URL`(기본 `http://assessment-mcp:9103/mcp`, 토큰 `ASSESSMENT_MCP_TOKEN`). MCP 서버는 `API_INTERNAL_URL`(기본 `http://api:8001`)과 `INTERNAL_TOKEN`으로 내부 API를 부른다. 각 도구는 Pydantic 입력 모델과 한 문단 설명·인자 설명을 가진다. session_id는 그래프가 주입한다(모델이 바꿀 수 없음).

### 공통 응답 형식

```json
{"ok": true, "data": {...}}
{"ok": false, "error": {"code": "not_found", "message": "session not found", "retryable": false}}
```

코드: `invalid_input`, `not_found`, `forbidden`, `conflict`, `not_released`, `upstream_unavailable`(retryable), `internal`. api 매핑: 404 not_found, 403 forbidden, 409 conflict, 422 invalid_input, 423 not_released, 5xx·연결 실패 upstream_unavailable(1회 재시도, 타임아웃 10초). **409의 api 오류 코드(`no_consensus`·`stale_generation`·`slot_confirmed`·`phase_not_open`)는 MCP `message`에 그대로 담는다**(예: `{"code": "conflict", "message": "no_consensus"}`). 결정적 노드는 이 message로 분기한다.

### debate-mcp (`http://debate-mcp:9101/mcp`)

| 도구 | 입력 | 출력 data | 내부 API | 구분 |
|---|---|---|---|---|
| get_debate_state | {session_id} | DebateState + {seats: [{seat: "candidate", display_name}, {seat, display_name, avatar_url}]} (페르소나 유형 없음). 결정적 노드(load) 전용이고 페르소나에는 바인딩하지 않는다(페르소나는 load가 걸러 주입한 DebateState만 본다) | GET /debate_state, GET /sessions/{id} | 조회 |
| get_transcript | {session_id, since_t_min?, phase?, limit?=30} | [{id, sender, content, phase, is_invite, t_min}] (meta·intent·origin 없음) | GET /messages | 조회 |
| get_draft | {session_id} | {sections, revision, updated_at} | GET /proposal | 조회 |
| post_message | {session_id, sender: p1∣p2∣p3∣system, content, run_id, seq, expected_generation?, is_invite?, card_ids?, cited_material_ids?, meta?} | Message. 409 `stale_generation`이면 게시 안 됨 | POST /messages | 변경 |
| propose_option | {session_id, phase, label, proposer: p1∣p2∣p3, scenario_option_key?, source_message_id, run_id} | Option(`existing` 포함) | POST /options | 변경 |
| set_stance | {session_id, participant: p1∣p2∣p3, option_id, stance: support∣oppose, source_message_id, run_id} | {stance_id} | POST /stances | 변경 |
| fill_slot | {session_id, option_id, seat: p1∣p2∣p3, content, run_id} | {slot, message, phase}. 합의 채우기 전용. 칸 확정·공지 메시지 저장(seq 5)·단계 전환을 api가 한 트랜잭션으로 한다. `resolution`은 api가 consensus로 정하고 인자로 받지 않는다. 같은 run_id 재호출은 기존 결과 | POST /slots/fill | 변경 |

- 지원자의 안·입장은 api 메일박스가 의도 분류로 직접 저장하므로 MCP 도구의 proposer·participant에 `candidate`는 없다.
- 그래프의 페르소나 게시는 항상 `expected_generation`(실행 시작 때 값)을 넣는다. 합의 채우기 공지는 `post_message`로 따로 게시하지 않는다. `fill` 노드의 `announce_fill` 분기가 공지 문장을 `fill_slot`의 `content`로 넘기고, api가 칸 확정과 같은 트랜잭션에서 저장한다. `fill_slot`이 409(`no_consensus`·`slot_confirmed`·`phase_not_open`)면 칸도 공지도 없이 run을 끝낸다.

### rag-mcp (`http://rag-mcp:9102/mcp`)

| 도구 | 입력 | 출력 data | 구분 |
|---|---|---|---|
| search_materials | {session_id, query, top_k?=3} | [{material_id, title, chunk, score}]. 내부 GET /materials로 잠금·키워드·catalog_version 확인 후 열린 자료의 같은 버전 청크만. 잠겨 있으면 `not_released` | 조회 |
| get_material | {session_id, material_id} | {material_id, title, content}. 내부 GET /materials/{material_id}(같은 catalog_version 본문). 열린 자료가 아니면 `not_released` | 조회 |
| reindex_materials | {mission_id?} | {indexed, model, dim, catalog_version}. 현재 카탈로그 자료를 그 catalog_version으로 `material_chunks`에 색인(관리용, 이전 버전 행은 지우지 않음). 원문 `materials` 행은 `scripts/seed.py`가 같은 버전으로 시드. 에이전트에 노출하지 않음 | 변경 |

### assessment-mcp (`http://assessment-mcp:9103/mcp`, X-Assessment-Token 필수)

| 도구 | 입력 | 출력 data | 내부 API | 구분 |
|---|---|---|---|---|
| record_observation | {session_id, card_id, phase, trigger_message_id?, run_id} | {observation_id, fired_at, t_min}. 카드 첫 발언 게시 **뒤에** 한 번 | POST /observations | 변경 |
| get_rubric | {session_id} | {rubric_version, elements(차원·수준 앵커), no_record_reasons, cards} | GET /rubric | 조회 |
| get_session_record | {session_id} | SessionRecord(아래). 평가 입력 묶음 | GET /sessions/{id}, /messages(전체, 페이지 반복), /slots, /proposal, /observations, /facts, /contributions | 조회 |
| get_transcript_span | {session_id, message_id, before?=5, after?=3} | {target, before, after} (intent·origin 포함). 리포트 근거의 앞뒤 맥락 표시용 | GET /transcript_span | 조회 |
| get_contributions | {session_id} | Contributions | GET /contributions | 조회 |
| save_evaluation | EvaluationSave(아래) | {run_id, existing, saved} | POST /evaluations | 변경 |

토큰이 없거나 다르면 `forbidden`.

### 도구 허용 목록

| 주체 | 허용 도구 | 호출 방식 |
|---|---|---|
| 턴 매니저 결정적 노드(load·cards·apply·fill) | debate-mcp 전부, assessment-mcp `record_observation` | 코드가 직접 호출 |
| 턴 매니저 turn(LLM) | 없음 | 주입된 DebateState만 |
| 페르소나 respond | `get_transcript`, `get_draft`(proposal 단계에서만 바인딩), `search_materials`, `get_material` | 모델 도구 호출, 응답당 3회. `get_debate_state`는 바인딩하지 않는다(DebateState는 load가 `card_progress`·`cost_left`를 걸러 컨텍스트에 주입). 최근 대화도 미리 들어가므로 `get_transcript`는 보통 부르지 않는다 |
| 어시스턴트 | `search_materials`, `get_material` | 모델 tool-calling 루프, 요청당 최대 3회, 답에 인용 자료 id |
| report-worker | `get_rubric`, `get_session_record`, `get_transcript_span`, `get_contributions`, `save_evaluation` | 코드가 직접 호출(평가 에이전트 LLM에는 도구를 바인딩하지 않고 입력 묶음을 주입). 평가 결과 재조회(`GET /evaluations`)·리포트 저장은 내부 REST |

페르소나 respond의 출력은 구조화 `{content, proposes?: {scenario_option_key∣label}, stance?: {option_id, stance}}`이고, 결정적 `apply`가 guard 통과 뒤 `post_message` → `propose_option`/`set_stance` 순으로 반영한다(source_message_id = 방금 게시한 메시지). 카드 발언이면 `post_message`에 `card_ids`를 넣고(전달 기록, 공동 전달이면 여러 개), 그중 첫 발언인 카드마다 이어서 `record_observation`. 자리의 고정 안과 입장 변경 허용 범위는 시나리오 규칙(`stance_plan`)으로 노드 `stance_check`가 **게시 전에** 검사한다: 계획 밖 입장(자기 계획 안에 `oppose`하거나 문장으로 반대하는 것 포함, 또는 문장이 계획과 다른 입장을 말함)이면 응답 전체를 1회 재생성하고, 그래도 어긋나면 계획과 맞는 자리별 고정 문구(프롬프트 `stance_fallback`)로 바꿔 게시한다. 결과는 `messages.meta.stance_check`(`pass`∣`regenerated`∣`fallback`)에 남긴다. 게시 문장과 기록 입장은 항상 일치한다(문장만 게시하고 입장을 버리는 경우는 없다).

## 큐 메시지

| 큐 | 본문 | 발행 | 소비 |
|---|---|---|---|
| report.generate | {session_id, attempt, eval_round} (attempt는 1부터, 실패 시 +1 재발행, 3에서도 실패하면 DLQ. eval_round는 위 EvaluationSave `run_id` 규칙) | api `submit()` 직후(eval_round 1)와 regenerate. 미발행은 스케줄러가 60초마다 재발행 | 워커. 리포트 그래프 `collect → aggregate → evaluate → draft` → draft 저장 성공 후 ack(`interrupt`에서 멈춤) |
| report.approve | {session_id, attempt, eval_round} (eval_round = 승인한 draft를 만든 `sessions.eval_round`) | api `/admin/sessions/{id}/review`. 미발행은 60초마다 재발행 | 워커. 그 eval_round thread의 `interrupt` 재개 → `finalize`(승인된 draft content를 그대로 final로 저장, 해시 동일) 성공 후 ack |
| report.dlq | 원본 + error | 워커(attempt ≥ 3) | dlq 소비자가 `report_failed` 호출 뒤 ack |

리포트 그래프 thread_id = `report:{session_id}:{eval_round}`. 새 eval_round는 새 thread라 이전 회차의 interrupt 체크포인트(이전 draft)를 재사용하지 않고 collect부터 다시 실행한다. 같은 eval_round의 큐 재시도만 그 thread의 체크포인트에서 이어 간다(interrupt에 멈춰 있으면 draft 저장부터).

persistent, publisher confirm 뒤 `*_enqueued_at` 기록, manual ack, 같은 session_id 중복은 stage로 멱등. 재시도는 `attempt+1` 재발행 후 원본 ack(백오프 5·15·45초).
