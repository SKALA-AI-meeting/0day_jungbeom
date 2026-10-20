# 개발 전 리뷰 3종 반영 지시서 (2026-10-20)

원문: `review-redesign.md`(Codex), `review-candidate-view.md`(지원자 관점), `review-admin-view.md`(담당자 관점). 아래는 오케스트레이터 결정. "사용자 결정"으로 표시된 항목은 사용자 답을 받아 채웠다. 반영 트랙은 이 파일을 체크리스트로 쓴다.

## A. 설계 결정 (Codex 차단 A1~A12 + 지원자·담당자 겹침)

| # | 결정 | 반영 문서 |
|---|---|---|
| A1 | **보고는 팀 채널.** honesty_report 요청은 팀 채널, 지원자 보고 감지(kind=report)는 팀 채널 또는 팀장 DM 둘 다. reporting 상태에서 채널 잠금 없음. 보고 요청 시스템 줄에 "최종본은 오른쪽 탭에서 제출, 제출하면 종료" 안내. `notified_in_team`도 팀 채널 또는 팀장 DM(이름을 `notified_where_manager_sees`로) | PRD 6.4·7.3, contracts, api, agent, frontend, rubric |
| A2 | **레이블·aux·근거 타입의 단일 표는 rubric.md.** 카드별 레이블 7세트, aux 키(promised_t_min, is_specific, has_alternative, target_applied, credits_colleague, discloses_incomplete …), 근거 타입 message·document·share·open·task_event·doc_view·assistant_call을 rubric.md 한 표로 두고 agent·contracts(observations evidence 허용 타입)·worker·testing이 그 이름을 그대로 쓴다 | rubric, agent, contracts, worker, testing |
| A3 | **저장 이력 복원.** `document_revisions`(doc_id, revision, by, content, length, diff_ratio, created_at)를 자동 저장마다 append. `document_versions`는 보낸 시점의 revision을 가리킨다. 최종본 섹션 편집·가져오기도 revisions에 남긴다. observe와 assistant_reuse는 revisions를 읽는다 | data-model, contracts(내부 GET document_revisions 유지), api, agent, worker |
| A4 | **보드가 분업의 정상 경로.** 세션 시작 시 tasks 5행을 assignee=null로 생성. 지원자가 PUT으로 담당을 채우고(복수 담당 `both` 허용), 5행이 다 차고 division_min을 만족하는 순간 api가 division을 확정(decided_by=candidate, task_event 기록, WS division.confirmed, 동료 그래프에 stimulus). 채팅으로 정한 분업은 동료의 set_division 도구가 같은 tasks를 채운다. 확정 뒤 재배정도 task_event + 동료 stimulus(work_notes 갱신). 미확정이면 다음 이벤트에서 동료가 기본안을 tasks에 채움 | PRD 6.2, contracts, api, agent, frontend, data-model |
| A5 | **계획성 창은 킥오프부터.** planning_division 카드는 L/12에 동료가 묻는 것이고, 관찰 창은 세션 시작(0)부터 첫 중간 카드까지. 카드 전에 정한 계획도 같은 창 안 | scenario-model, rubric, agent |
| A6 | **약속 이행은 세션 종료 시 확정.** collab_help 관찰 행은 창 닫힘에 저장하되 `promise_kept`는 null. 종료(finalize) 단계에서 related_card 메시지로 다시 계산해 그 지표만 갱신(관찰 PUT 허용, 같은 run_id 멱등). 창 밖 근거는 메시지만 | rubric, agent, contracts(observations PATCH), worker |
| A7 | **적응성 "반영" 항목 조건.** `document_changed_after` AND aux `target_applied`(LLM이 변경 대상이 문서에 반영됐는지 예/아니오, 품질 아님). 말없이 반영은 문서 근거(document)로 증명 | rubric, agent |
| A8 | **정직 전제를 지표로.** metrics `has_colleague_shares`, `has_incomplete_facts`, `has_report_message`. honesty_facts에 `empty_sections: [part_no]`, `tasks_not_done`, `changed_after_adaptability: bool|null`(적응성 미선택이면 null, 미완료로 안 봄) | rubric, contracts, api, worker |
| A9 | **경로·멱등 통일.** 계약 이름(`/internal/.../docs/shared`, `/docs/send`, `GET /board`)으로 api·mcp 문서를 맞춤. send_document는 event_id·seq를 받아 메시지 1건을 만들고 파트별 고정 seq(파트 번호×10) | contracts, api, mcp, agent |
| A10 | **division_min에 의존 보장.** 2번은 지원자, 3번(2번 의존)은 동료 또는 같이, 4·5 중 하나는 동료 단독. 그래도 영향이 없는 분업이면 해당 항목은 not_applicable | PRD 6.2, scenario-model, rubric, agent |
| A11 | **동료 문서 전송 실패.** 1회 재시도 후 실패면 카드 status=failed(필수 카드 실패 3회 규칙 적용)이고, 그 문서에 의존하는 항목은 사유 `document_missing`으로 기록 없음. 사유 목록에 추가 | harness, rubric, contracts, agent, worker |
| A12 | **reporting 재입장.** resume은 in_progress·reporting 모두 허용, state에 deadline_at, 보고 대기 중 재연결을 완료 기준에 | contracts, api, frontend, testing |

Codex 권장 B1~B9 전부 반영: 킥오프 예고 시각 = 지연 카드 시각(60), 공개 70. 보고 타이머·최종 창 끝 규칙 하나로(요청 시각 → 보고 메시지 또는 제출+5분 → completed_at 저장). sessions.completed_at 추가. 공개 예정 시각을 state·documents에 `release_at_min`으로. 초안 범위(동료 담당 파트 전부 v1, 같이 파트 골격 포함)와 리뷰 v2. `stated_schedule`은 due_min 입력 또는 순서 2건 이상 변경 또는 채팅 시점 언급. 팀장 도구에 search_documents 추가. candidate_role=primary 통일, 안내 문구 주담당, 400/422 통일(422). 이벤트 시점 기준 fired→done ±10초, 메시지 전달 90초.

MVP 정리: `/admin/catalog`에서 rubric 미리보기·timeline·element_fraction_rule·pilot_value 삭제(meaning·how_we_see만). 최종본 append 삭제(덮어쓰기만). evaluation.md 수치 갱신(State 18, 도구 조회 4·변경 7).

계획: web-redesign 2단계(실 API 연결, 완료 기준 "실 API로 공유→열람→통합→제출→보고→리포트")를 plan에 추가. scenario-redesign 소유권에 SessionService·scheduler·business-mcp·version.py·rag 색인 키 포함. 재설계 기간 `scenarios/missions/`는 prompts 포함 scenario-redesign 소유, prompts 트랙은 그 뒤 문구 다듬기. 사용자 mock 확인이 막는 것은 web 실 연결과 agent-session 착수이고 scenario-redesign(데이터·API)은 병렬. catalog_version = 미션 폴더 전체 해시 한 함수. 최소 테스트 6건(보드만으로 분업 확정, 카드 전 계획, 창 밖 약속 이행, 무관한 편집, 문서 제공 실패, reporting 재접속)을 완료 기준에.

## B. 지원자 관점 반영

- 지연 알림은 "리서치 담당 → 나(개인 메시지)"로 표시하고 수신자가 나뿐임을 명시. 공개되면 같은 채널에 "공개됨" 줄.
- 중간 점검(45분)에서 동료가 "2번 자료 언제쯤 볼 수 있을까요?"라고 묻는다(지연 카드 60분 전이라 선점 금지와 충돌 없음). 지연이 동료가 기다리는 자료가 된다.
- 제출 확인 창: "제출 후 수정 불가, 팀장 보고 뒤 세션 종료". 만료 2분 전 경고 "지금 상태 그대로 제출됩니다". 자동 제출 뒤 보고 요청에는 "한 줄이면 됩니다".
- 대기 화면: 동료는 "사람 팀원 역할의 AI, 요청과 피드백도 업무의 일부", 팀장 DM·개인 알림·문서 주고받기·끊겨도 시간이 흐름·외부 도구 허용 여부·레이아웃 그림. 오피스 "?"로 다시 보기.
- 보드 카드 담당 복수(`both`). 같이 파트 골격 v1은 중간 점검 때 함께 옴.
- 편집 중 새 메시지 토스트(Sonner). 어시스턴트 응답 복사 버튼. 접속 끊김 구간을 기록해 시스템 줄과 리포트 사실로.
- 디브리핑에 점수 비공개 이유, 기업이 보는 것, 리모트 맥락, 종료 설문 2문항(납득도), 최종본 열람·복사 7일, 문의 창구.
- `complain_then_apply`는 비난·거부로 좁힘. 분업 되돌림 1회, 이유는 의존 관계.
- 받은 문서 버전 비교 삭제(최신 열기만, 이전 버전은 목록에서 열람 가능). 분할 보기는 polish로. "언제까지"는 남은 시간 프리셋("30분 뒤", "마감 10분 전").
- fixed_opinions 본문·5요소 meaning/how_we_see 문구는 scenario-redesign 산출물.

## C. 담당자 관점 반영

- 재초대는 세션 실패·만료·취소에만. 리포트 실패는 "리포트 다시 생성" 액션(POST /admin/sessions/{id}/report/regenerate). 시작 후 취소(중도 포기) 허용.
- 목록 점수: 충족·미충족·기록 없음 세 수 나란히, 분모 만점 표기 없이. 기록 없음 사유는 책임 주체 문장("지원자 활동 없음" / "시스템: 분류 실패" / "시스템: 메시지 지연" / "시스템: 문서 미제공" / "해당 없음").
- 리포트 맨 위 요소별 한 줄 관찰·점수 요약표, 카드 소섹션 접힘 기본. 항목마다 "기록 기반 / AI 분류 기반" 표시. 검토 완료 뒤 메모 추가 허용(값 잠금). 확인 창 문구. approve 실패 시 "조정은 저장됨". 검토자 이름 입력란. 정직 소섹션 "미완료는 보드 기준" 주석. 최종본 편집 칩은 동료 원문과 나란히.
- 상태 묶음(대기·진행·검토 필요·완료·문제)과 필터, 시작·종료 예정 시각, 이메일, 마지막 활동·메시지 수, 실패 시 담당자 행동 안내.
- 생성 화면: 기본 전체 선택, 요소를 뺐을 때 차이 한 줄, "(선택)" 꼬리표 제거, 별칭 설명·중복 방지, 초대 만료 연장(재발행=연장, 재응시 표시 아님), "요소 구성이 같으면 같은 기준" 문구.
- 90일: 관리자 화면에 삭제 예정일, purge에 invites 이메일·sessions 포함. 담당자용 FAQ 문구(AI가 평가하나요, 기록, 결과 안내, 이의 제기). 기업 약관·위탁 안내는 MVP 이후(열린 질문).
- 리포트 JSON 정리: history 삭제, 요소별 reviewer 소계 삭제, aux_facts·out_of_window를 근거 목록의 "점수 무관" 표시로 합침, 표시 상태 10종 → 접미 표기.

## D. 사용자 결정 (2026-10-20 밤)

1. **적응성 카드 내용은 자료가 살아남는 변경.** 대상 사용자(첫 참여자)는 그대로 두고, 팀장이 "핵심 기능을 '첫 모임 뒤 48시간 안 후속 모임 제안' 한 가지로 좁히고, 출시 일정을 다음 분기 → 이번 분기로 당겨 달라. 마감은 그대로"라고 바꾼다. 인터뷰·지표·템플릿은 그대로 쓰고, 3번(핵심 기능)과 5번(일정)의 분담·내용 재조정이 필요해진다. 반대 의견 카드의 고정 의견은 이 변경과 겹치지 않는 주제(예: 1번 문제 정의의 원인 가정)로 둔다.
2. **전체 기록 읽기 전용 화면을 넣고, 평가 항목에서 관련 사건으로 바로 연결한다.** 리포트의 각 근거·항목에 "기록에서 보기" 링크를 두어 전체 기록의 해당 시점으로 이동(F-05를 MVP에 포함, 하이라이트). 전체 기록은 대화(채널별)·문서 보내기/열기·보드 변경·어시스턴트 호출을 한 타임라인으로. **리포트 화면은 design-system.md 컨셉에 맞춰 다시 설계한다**: 맨 위 요소별 한 줄 관찰·점수 요약표, 카드 소섹션 접힘, 항목별 "기록 기반/AI 분류 기반" 표시, 근거마다 기록 링크, 채용 관계자가 바로 이해하는 문장. 리뷰 라운드에서 다시 본다.
3. **샘플 리포트와 인쇄·PDF 내보내기 둘 다 MVP.** 샘플은 픽스처 기반 정적 페이지(생성 화면과 리포트 목록에서 링크), 내보내기는 인쇄 CSS(브라우저 PDF). 둘째 계정은 MVP 이후.
4. **AI 활용 라벨 제거.** 위임·맥락·검증 분류와 verbatim/edited 표기를 빼고 요청·응답·인용 문서·반영된 파트를 시간순 사실로만. assistant_reuse 계산은 "반영된 파트" 사실 표시용으로만 남기고 비율 표기는 뺀다. PRD 5.3의 관찰 포인트 세 가지는 "담당자가 보는 관점" 설명으로만.
