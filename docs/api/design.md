# api 설계 (FastAPI + LangGraph 모듈)

## 구조와 소유

```
services/api/app/
  main.py              FastAPI 앱 2개: 공개 /admin,/s,/sessions,/ws · 내부 /internal                     [foundation]
  run.py               uvicorn Server 두 개(8000, 8001)를 한 asyncio 루프에서 실행. hub·Lock·스케줄러 공유   [foundation]
  config.py, db.py     env, SQLAlchemy async                                                   [foundation]
  models/              테이블 모델                                                              [foundation]
  auth.py              JWT, 역할 의존성, bcrypt, 초대 토큰 해시                                  [foundation]
  services/session.py  SessionService: 상태 전이의 유일한 소유자                                 [foundation]
  services/scenario.py 미션 카탈로그(`scenarios/missions/<id>/`) 로드(버전 해시), 요소→카드 조립, 이벤트·공개 예약 펼치기  [foundation]
  hub.py               세션별 WS 연결, broadcast                                                [foundation]
  queue.py             RabbitMQ publish(persistent), 재발행 재탐색                               [foundation]
  masking.py           전화번호·이메일 마스킹                                                    [foundation]
  agent/runner.py      AgentRunner Protocol + FakeAgentRunner                                   [foundation]
  routers/admin.py     /admin/*                                                                 [api-admin]
  routers/internal.py  /internal/*                                                              [api-admin]
  routers/candidate.py /s/*, /sessions/*                                                        [api-candidate]
  routers/ws.py        /ws/sessions/{id}                                                        [api-candidate]
  scheduler.py         5초 루프                                                                 [api-candidate]
  agent/               세션·어시스턴트 그래프, observe, prompts                                   [agent-session, agent-assistant, prompts]
  Dockerfile, pyproject.toml, /health                                                           [foundation]
```

## 인증
`docs/common/contracts.md`의 인증 생명주기 표가 정본. 의존성 `require_admin`, `require_candidate(session_id 일치)`, `require_internal`. 내부 앱은 8001 포트에 따로 띄우고 compose에서 공개하지 않는다.

## SessionService
`create_for_invite`, `consent`, `start`(이벤트·공개 예약 펼치기, 지원자 파트 문서 5개·최종본·section_owners 5행(owner null) 생성. 할 일은 만들지 않음), `confirm_division`(아래 문서와 보드), `submit(reason, message?)`(아래 제출 처리. 끝에서 바로 `complete`를 부름), `complete(reason)`(AgentRunner end(고정 run_id, 세션 Lock을 잡으므로 진행 중 run이 끝난 뒤 실행. 열린 창 닫기와 collab_help promise_kept 확정 포함) → 재사용 추정 계산 → `completed_at` 저장·completed 커밋 → 큐 발행(confirm 후 enqueued_at) → session.ended), `mark_report_ready`, `approve`(approving 커밋 → report.approve 발행 → approve_enqueued_at 기록), `mark_reviewed`, `cancel`(invited·in_progress에서 담당자가 취소. 시작 후 취소는 중도 포기로 기록하고 session.ended reason=cancelled), `fail(reason)`, `regenerate_report`(failed_stage=report인 세션을 completed로 되돌리고 report.generate 재발행). 모든 전이는 현재 상태를 검사하고 멱등이다.

세션 상태: `invited → in_progress → completed → report_ready → approving → reviewed`, 어디서든 `failed`, 시작 전·진행 중 `cancelled`. 제출과 종료 사이에 대기 단계는 없다. `sessions.completed_at`이 실제 종료 시각의 유일한 원천이며 관찰 창 끝·디브리핑 기한·리포트가 모두 이 값을 쓴다.

채용 건(`positions`)은 `mission_id`(MVP는 기획안 미션 하나)와 `elements`(1~5개, 중복 없음)를 가진다. 조립은 선택 요소의 카드만 넣고, 흐름 카드(kickoff, division, review, report_request)는 요소 미선택이어도 관찰 없이 항상 넣는다(선택 시 planning_division·honesty_report로 승격). 배치 규칙은 `docs/common/scenario-model.md`.

## 스케줄러 (5초)
```
events:   status=pending AND due_at<=now → 같은 due_at 행을 card order로 묶어 하나의 run_id 생성·fired 커밋 → agent_runs started → runner.run(event, event_ids, run_id) → ok면 행마다 자기 event_id의 메시지가 있는지 확인해 done / 실패 시 attempts+1(총 3회까지 같은 run_id로 재실행, 아니면 failed+세션 fail)
runs:     agent_runs.status=started AND started_at < now-120s → 같은 run_id로 재실행
retry:    status=fired AND fired_at < now-60s → 재실행 (재시작 복구)
releases: release_at<=now AND released_at null → 기록 → document.released
timeouts: in_progress AND ends_at<=now AND submitted_at null → submit("timeout")
closing:  in_progress AND submitted_at not null AND completed_at null → complete() (제출 처리 중 중단된 세션. 종료 run_id 고정, 멱등)
outbox:   status=completed AND report_enqueued_at null → report.generate 재발행
          status=approving AND approve_enqueued_at null → report.approve 재발행
purge:    completed_at(또는 failed·cancelled 시각) + 90일 지난 세션의 메시지·문서·관찰·리포트와 invites 이메일·sessions 행 삭제. 삭제 예정일 `purge_at`은 목록에 표시
```
세션별 Lock으로 메시지 자극과 직렬화. 같은 due_at 이벤트는 card order로 한 run에 처리.

세션별 due_at 직렬 처리(2026-10-20 리뷰 반영): events·retry의 카드 실행은 세션마다 "미완료(fired) 또는 due된 pending 중 due_at이 가장 이른 묶음" 하나만 다룬다. 그 묶음이 done·failed·skipped가 되기 전에는 뒤 묶음을 fired로 만들지 않는다. 미완료 묶음은 이 프로세스에서 실행 중이면 기다리고, 아니면(재시작) fired_at < now-60s일 때 같은 run_id로 재실행한다. 카드의 최종 failed와 세션 fail은 한 트랜잭션이고, failed 필수 카드가 남은 in_progress 세션은 다음 tick이 fail로 수렴시킨다. runs(120초) 재실행은 메시지 실행만 대상이다. 시작 공개 문서는 `start()`가 released_at을 바로 기록하므로 releases는 지연 공개만 다룬다.

## 제출 처리
`/submit {message?}`(한서윤에게 보내기) 또는 timeout → `submit(reason, message)`. 종료 규칙은 하나다: **제출하면 같은 요청 안에서 종료한다.**
- 세션 Lock 안에서 `submitted_at` 커밋, 최종본 version 생성. 이후 문서·최종본·보드·어시스턴트 쓰기는 409 `session_ending`, 메시지는 WS `session_ending`.
- 한서윤 DM(`manager_dm`)에 제출 메시지 저장: sender candidate, 본문은 `message`(없으면 빈 문자열), `meta.shared_doc`에 최종본 version, `meta.classification.kind = report`(api가 붙임, 분류기 거치지 않음). timeout은 본문 없이 같은 처리.
- 한서윤 고정 답장 "받았어요, 수고하셨어요."를 manager_dm에 저장(LLM 없음, 실패 처리 불필요).
- `honesty_report`(또는 흐름 `report_request`) 행이 아직 pending이면 DM을 보내지 않고 `fired_at=done_at=submitted_at`으로 done 처리한다. 정직 창은 이 시각부터다.
- 이어서 `complete("submitted"∣"timeout")`: end run(마지막 창 닫기·promise_kept 확정) → `assistant_reuse` 계산 → `completed_at` 저장·completed 커밋 → 큐 발행 → WS `session.ended`. 중간에 죽으면 스케줄러 closing 항목이 다시 부른다.
- 재입장: `POST /s/{token}/resume`은 in_progress만 허용한다. 접속 끊김 구간은 WS 연결 해제·재연결 시각을 `connection_gaps`(session_id, disconnected_at, reconnected_at)에 기록하고 notice 채널에 시스템 줄로 남긴다(관찰 근거 아님, 리포트 사실).

`estimate_reuse(response: str, revisions: list[Revision]) -> (applied: bool, part_no, revision)` (순수 함수, `app/services/reuse.py`). 결과는 "어시스턴트 응답이 어느 파트에 반영됐는가"라는 사실 표시에만 쓰고, 등급·비율은 리포트에 내지 않는다:
- 정규화: 공백·구두점 제거, 소문자. 응답 정규화 길이가 20자 미만이면 applied=false.
- 비교 대상: 그 호출 **이후** 지원자가 저장한 모든 지원자 문서(파트 문서·최종본)의 모든 `document_revisions`(스냅샷 본문).
- ratio = (응답과 revision의 공통 부분 문자열 중 길이 20자 이상인 것들의 합) / 응답 정규화 길이. `difflib.SequenceMatcher.get_matching_blocks` 사용. 파트·revision 중 최대 ratio가 0.3 이상이면 applied=true이고 그 (part_no, revision)을 돌려준다.
- 저장: `assistant_reuse`에는 호출×파트별 `applied`만 저장한다(ratio·revision 컬럼 없음). 내부 `GET /assistant_reuse`는 `[{call_id, doc_id, part_no}]`로 반영된 파트만 돌려준다.

## 문서와 보드
문서 주고받기 모델(`docs/frontend/design-direction.md`). 문서마다 주인이 하나라 충돌이 없다.

- `documents`(session_id, owner ∈ candidate∣colleague, part_no 또는 final, revision, content). 세션 시작 시 지원자 파트 문서 5개와 최종본(섹션 5개 골격, 킥오프 템플릿)을 만들고(분업과 무관, 안 쓰는 파트는 빈 채로 남음), 동료 문서는 첫 send_document에서 만든다.
- 저장: `PUT /sessions/{id}/my-documents/{part_no∣final}`은 내 문서만. revision+1 하고 `document_revisions`(doc_id, revision, by, content, length, diff_ratio, created_at)에 자동 저장마다 append한다. 최종본 섹션 편집·가져오기도 revisions에 남긴다(관찰·재사용 추정이 과거 본문을 복원하는 유일한 원천). 내부 `GET /internal/sessions/{id}/document_revisions`로 읽는다.
- 보내기: `POST /sessions/{id}/my-documents/{part_no}/share {channel}`은 `document_versions`에 현재 revision을 가리키는 vN(version+1)을 고정하고 `document_shares`(문서·버전·채널·시각) 행과 채널의 문서 카드 메시지(`meta.shared_doc {doc_id, version}`)를 한 트랜잭션으로 만든다. 동료 쪽은 내부 `POST /internal/sessions/{id}/docs/send {doc_id∣part_no, content, channel, event_id, seq, run_id}`로 문서 revision+1·버전 고정·문서 카드 메시지 1건(event_id·seq 포함)을 같은 트랜잭션에서 만든다. 멱등은 문서 (doc_id, run_id)·메시지 (run_id, seq)이고 seq는 파트별 고정(파트 번호×10)이라 같은 run에서 여러 파트를 보내도 겹치지 않는다. 같은 키 재요청은 기존 version과 message_id를 돌려준다.
- 열기: `POST /sessions/{id}/documents/{doc_id}/open {version}`은 동료가 보낸 버전만 돌려주고 `document_opens`(문서·버전·시각)를 기록한다. 공유되지 않은 버전은 404. 내부 `GET /internal/sessions/{id}/docs/shared`가 동료·팀장 도구 `get_shared_documents`의 원천이고(지원자 문서는 보낸 버전만), `GET /internal/sessions/{id}/docs`가 워커·observe용 전체다.
- 최종본: `PUT /sessions/{id}/my-documents/final {sections}`(직접 편집, 바뀐 섹션만 edited=true)와 `PUT /sessions/{id}/final/sections/{part_no}/import {source_doc_id, version}`(그 버전 내용으로 섹션을 **덮어쓰고** source_doc_id·source_version 기록, edited=false. 뒤에 붙이기는 없음). 제출은 최종본을 한서윤에게 보내는 것이고 섹션 출처 스냅샷이 리포트 산출물이 된다.
- 보드: `tasks`(id, section_part_no 필수 1~5, title, assignee ∈ candidate∣colleague∣both∣null, status, order?, due_min?)와 `task_events`. 세션 시작 시 0행이다. 지원자 `POST /sessions/{id}/tasks`로 만들고(섹션 연결 필수) `PUT /sessions/{id}/tasks/{task_id}`로 바꾸며 바뀐 필드마다 task_event를 남긴다. 섹션 담당은 `PUT /sessions/{id}/sections/{part_no}/owner`(draft)로 따로 정한다. depends_on은 미션 `parts`에서 온다(3번은 2번). 동료 `update_task`는 보드에 있는 동료 실행 담당 할 일의 status만 바꾼다(분업 확정 때 doing, 그 섹션 v2를 보낸 뒤 done). 할 일이 없으면 부르지 않는다.
- 분업 확정(`confirm_division`, 분업안 공유가 정상 경로): `POST /sessions/{id}/division/share`가 섹션 담당 draft 5개와 `division_min`(2번 candidate, 3번 colleague 또는 both, 4·5 중 하나 colleague 단독)을 한꺼번에 검사해 불변 스냅샷을 만들고(decided_by=candidate, task_event, 팀 채널 분업안 메시지, WS `division.confirmed`, AgentRunner에 `division` 자극) 위반이면 422 `invalid_division`과 `details.violations`(어긴 섹션 전부)를 돌려준다. 채팅으로 정한 분업은 동료의 `set_division`(내부 `PUT /division`)이 같은 검사로 스냅샷을 만든다(할 일 행은 만들지 않음). 확정 뒤 변경은 draft 수정 후 재공유로 적용한다. 미확정이면 다음 카드에서 동료가 기본안을 set_division으로 확정한다(decided_by=colleague_default). 내부 `GET /internal/sessions/{id}/board`가 보드의 원천.
- submitted_at 이후 문서·최종본·보드 쓰기는 409 `session_ending`. 회사 문서 본문 조회는 `doc_views` 기록. 공개 예정 시각은 `/state`와 `GET /sessions/{id}/documents`의 `documents[].release_at_min`으로 준다(아직 공개 전인 지연 공개만. 지연 알림 전에는 킥오프 예고 시각, 알림 뒤에는 실제 공개 시각. 선택 요소 수에 따라 달라지므로 화면이 고정 시각을 쓰지 않게). `/state`의 `session`에는 `alias`·`session_minutes`·`office_start`·`office_end`·`completed_at`이 있다.
- 정직 사실: `GET /internal/sessions/{id}/honesty_facts`가 contracts.md의 형태(`shares, final_sections, section_owners, empty_sections, tasks_not_done, changed_after_adaptability`)를 돌려준다. empty_sections는 본문이 빈 최종본 섹션 전부(담당과 무관), tasks_not_done은 사용자가 만든 할 일 중 done이 아닌 것(점수 무관 추가 사실, 할 일이 없으면 빈 배열), changed_after_adaptability는 적응성 카드 뒤 지원자 문서 revision·share 유무(적응성 미선택이면 null). 그래프 observe는 같은 서비스 함수를 직접 부르고, report-worker는 이 GET으로 받는다.
- 종료 설문: `POST /sessions/{id}/debrief/survey {answers: [{q, value}]}`(2문항, 납득도)를 `debrief_surveys`에 저장한다. 세션 JWT 또는 debrief_token, 한 번만(재요청은 기존 값).

## 관리자 보충
- 재초대(`previous_session_id`)는 이전 세션이 failed(session)·만료·cancelled일 때만 받고 아니면 422 `invalid_previous_session`. 같은 채용 건의 별칭 중복은 409 `conflict`(재초대는 이전 응시의 별칭을 잇는다). 리포트 실패(failed_stage=report)는 재초대가 아니라 `POST /admin/sessions/{id}/report/regenerate`로 `regenerate_report`를 부른다.
- `POST /admin/sessions/{id}/cancel`은 invited뿐 아니라 in_progress도 받는다(시작 후 취소 = 중도 포기).
- 목록 `GET /admin/positions/{id}/candidates`는 score를 세 수 `{met, unmet, no_record}`(분모 만점 없음)로, 상태 묶음 `display_group ∈ 대기∣진행∣검토 필요∣완료∣문제`, `started_at`·`ends_at`·`email`·`last_activity_at`·`message_count`·`purge_at`을 함께 준다.
- 리포트 GET은 저장된 draft/final에 `rubric` 항목별 `reviewer`·`memo`·`adjusted`와 `review {memo, reviewer_name, reviewed_at}`, `notes[]`를 병합한다. 검토 후 메모 `POST /admin/sessions/{id}/report/notes {text}`는 reviewed 뒤에도 허용하며 값은 바꾸지 않는다(`report_notes` 행 append). 리뷰 본문의 `reviewer_name`은 필수.
- 전체 기록 `GET /admin/sessions/{id}/record`는 대화(채널별)·문서 보내기/열기·보드 변경·어시스턴트 호출·접속 끊김을 한 타임라인 `[{record_ref, t_min, kind, channel?, actor, summary, payload}]`로 돌려주고, 리포트의 evidence `record_ref`가 이 항목을 가리킨다.
- 입력 검증 오류는 422(elements·mission_id·division·previous_session·요청 본문)다. 예외는 리뷰 본문 규칙 위반으로 contracts.md대로 400(`invalid_item`·`memo_required`·`duplicate_item`)을 쓴다. 샘플 리포트는 web의 정적 픽스처 페이지라 api 경로가 없다.

## 완료 기준
- foundation: `docker compose up`에서 api healthy, 모델·마이그레이션(document_revisions, connection_gaps, sessions.completed_at, tasks.section_part_no NOT NULL 포함), SessionService 단위 테스트(전이 전부·멱등, 제출 즉시 completed·cancelled·regenerate 포함), 시작 시 할 일 0행·section_owners 5행·지원자 문서 5개·최종본 생성, 조립 결과가 scenario-model.md 수치와 일치(요소 5개 선택 시 120분 기준 분업 10, 도움 30, 중간 점검 45, 지연 60·공개 70, 변경 75, 리뷰·반대 의견 90, 진행 확인 DM 110), FakeAgentRunner로 메시지→내부 저장→hub 브로드캐스트(단위 테스트, WS 라우터는 api-candidate)
- api-admin: 관리자·내부 엔드포인트가 계약 예시대로, 기업 간 격리, elements 검증(1~5개, 0개·6개·중복 422), mission_id 검증(없는 미션 422), 권한 밖 변경 403, 승인 전 final 409, 재초대는 failed·expired·cancelled에만(아니면 409), regenerate는 리포트 실패 세션만, 시작 후 cancel, 목록 세 수·시각·이메일·활동, 검토 후 notes 추가에 값 불변, record 타임라인의 record_ref가 리포트 evidence와 일치, honesty_facts 필드 전부, send의 event_id·seq 멱등(같은 run에서 파트 2개 보내도 메시지 2건·재호출에 버전 불변)
- api-candidate: 지원자 엔드포인트·WS(ack, 증분, 재연결 후 /state), 6분 테스트 세션에서 이벤트가 이벤트 시점 기준 ±10초 내 fired→done, 문서 보내기→문서 카드 메시지·버전 1 증가, 자동 저장마다 document_revisions 1행, 공유 안 된 버전 열기 404, 최종본 가져오기에 출처 기록(덮어쓰기), 할 일 0개로 분업안 공유 확정(division.confirmed·task_event·division 자극, 위반은 422와 violations 전부), section_part_no 없는 할 일 생성 422, 제출이 메시지 유무와 무관하게 바로 completed(제출 메시지 kind=report·고정 답장·completed_at 저장), 진행 확인 DM 전 제출 시 DM 없이 honesty 행 done, 진행 중 resume·/state 복원, connection_gaps 기록, 만료 시 큐 발행, 재시작 후 fired 이벤트 재실행, 미발행 세션 재발행
