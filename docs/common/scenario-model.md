# 시나리오 모델

## 미션 카탈로그 (`scenarios/missions/<id>/`)

카탈로그는 미션 단위다. 채용 건은 `mission_id` 하나를 가리키고(MVP는 `planning` 하나), 같은 채용 건·같은 미션의 지원자는 같은 시나리오를 받는다. 미션 폴더 구성:

| 파일 | 내용 |
|---|---|
| `mission.yaml` | 미션 이름, `company`(회사·팀장·동료 이름), `parts`(파트 번호·제목·`depends_on`), `candidate_role: primary`(호칭 "주담당"), `default_division`, `division_min`, `final_template`(최종본 섹션 골격·분량·형식, 킥오프에서 전달), `documents` 목록 |
| `documents/*.md` | 회사 문서 본문 |
| `cards.yaml` | `elements[]`(요소 → `cards[]`), `flow_cards[]`, `texture[]`, `rubric_rules`, `common_labels`, `timing` |
| `persona.yaml` | 동료·팀장 values, style, must, must_not_preempt, in_window_help, identity, must_not |
| `prompts/*.md` | 페르소나 system prompt, `observe_labels.md`(레이블 7세트, 이름은 `rubric.md` 표와 동일), 디브리핑 문장 |

요소 5개: `responsibility`(책임감/성실성), `planning`(계획성/꼼꼼함), `adaptability`(적응성/유연성), `collaboration`(협업/조율), `honesty`(정직/공정한 보고). 요소는 `{id, name, meaning, how_we_see(2~3줄), cards: [...]}`이고 카드 하나의 필드:

| 필드 | 뜻 |
|---|---|
| `id` | `planning_division`, `planning_checkin`, `collab_help`, `collab_disagree`, `responsibility_delay`, `adaptability_change`, `honesty_report` |
| `name` | 카드 이름(리포트 소섹션 제목) |
| `slot` | `fixed`(at_fraction 고정) 또는 `middle`(중간 슬롯. 순서는 `timing.middle_order`) |
| `at_fraction` | fixed 카드의 시점 비율. `attach_to: review`면 리뷰와 같은 시점 |
| `actor` | `colleague`, `system`, `manager` |
| `channel` | `team`, `dm`, `notice` |
| `brief` | 페르소나에게 주는 전달 내용 골격(문장은 LLM이 생성). system 카드는 `text`(고정 문장)와 `sender_label`·`recipient_label`을 가진다. 카드별 내용은 아래 "카드 내용" |
| `sends_document` | 동료가 카드 실행 때 보내는 문서. planning_checkin은 `{parts: colleague_all, version: 1}`(동료 담당 파트 전부의 초안 v1, 같이(both) 파트는 골격 v1 포함), review는 `{parts: colleague_all, version: 2}` |
| `effects` | 부수 효과. 예: `release_document: interview_summary, delay_fraction: 0.0833` |
| `labels`, `label_texts`, `aux` | 관찰 레이블·리포트 문장·보조 판정 키(이름은 `rubric.md` 표가 정본) |
| `metrics`, `aux_facts` | 규칙 지표 목록 |
| `rubric` | 항목 `{id, text, when, only_if?, basis, evidence_types, pilot_value?}` |
| `unselected` | 미선택 시 처리. 예: planning_division `flow: true`(흐름 카드로 남고 점수 없음), responsibility_delay `release_at_start: interview_summary`, honesty_report `flow: true` |
| `requires_docs` | 필요한 회사 문서 id |
| `situation`, `debrief` | 리포트 장면 설명, 디브리핑 문장 |

흐름 카드(`kickoff`, `division`, `review`, `report_request`)는 `flow: true`로 항상 포함된다. `division`은 계획성 선택 시 `planning_division`으로, `report_request`는 정직 선택 시 `honesty_report`로 **승격**되어 같은 시점에 요소 카드로 실행된다(흐름 행과 요소 행을 따로 두지 않고 요소 카드 하나만 예약). `collab_disagree`는 `attach_to: review`로 리뷰와 같은 시점에 별도 행으로 실행된다. `texture`(`midpoint_draft`, 동료 초안 v1 보내기)는 계획성 미선택일 때만 L/2에 예약되며 관찰 창 경계에 들어가지 않는다(계획성 선택 시 같은 장면이 `planning_checkin` 카드다). 동료 진행 공유 texture 1~2개를 더 둘 수 있다(관찰 없음).

### 카드 내용

| 카드 | 전달 내용(brief·text) |
|---|---|
| kickoff | 미션·대상·마감, 최종본 템플릿(오른쪽 최종본 탭에 있음을 안내, 섹션당 분량), 주담당 지정, 인터뷰 요약 공유 예고 시각 `{interview_expected_time}`(책임감 미선택이면 "시작 시 공유됨"), "초안 수준이면 된다" |
| planning_division | 동료가 어떻게 나눌지 묻는다. 힌트는 파트 목록과 의존("3번은 2번 자료가 필요")뿐이고 안·순서·시점을 먼저 내지 않는다. 지원자가 섹션 담당을 채팅으로만 정하면 "분업안을 공유해 주시면 좋겠다"고 한 번 말한다. 할 일 생성은 선택이므로 요구하지 않는다 |
| collab_help | 동료 담당 파트 중 첫 번째(기본 분담이면 4번)의 기준이 헷갈려 "채팅으로 기준 두세 개만 10분 정도 같이 봐 줄 수 있을까요?"라고 청한다. 거절하면 "알겠어요, 혼자 정리해 볼게요"로 받는다 |
| planning_checkin | 동료 담당 파트 전부의 초안 v1(같이 파트는 골격 v1)을 팀 채널에 보내며 "방향 봐 주세요"와 주담당 진행을 묻고, "2번 자료는 언제쯤 볼 수 있을까요? 3번 골격 잡으려면 필요해서요"를 함께 묻는다. 재촉·자료 요청은 이 한 번뿐이다 |
| responsibility_delay | system `notice`. `sender_label: "리서치 담당"`, `recipient_label: "나에게만"`. `text`: "사용자 인터뷰 요약 공유가 약 10분 늦어집니다 ({release_time} 공개 예정). 담당 파트 2번에 필요한 자료입니다." 공개 시 같은 알림 채널에 "「사용자 인터뷰 요약」이 공개됐어요" 줄이 온다. 팀 채널·동료·팀장에게는 아무것도 가지 않는다 |
| adaptability_change | 팀장이 팀 채널에서: "대표님과 이야기해 보니 핵심 기능을 **'첫 모임 뒤 48시간 안에 후속 모임을 제안하는 기능' 한 가지로 좁히고**, 출시 일정은 다음 분기에서 **이번 분기**로 당겨 주세요. 대상 사용자(첫 참여자)·인터뷰·지표·템플릿은 그대로이고 마감도 그대로예요." 3번(핵심 기능)과 5번(일정)의 내용·분담 재조정이 필요해지며 자료는 그대로 쓸 수 있다 |
| review | 동료 담당 파트 완성본 v2(지시·피드백 반영)를 팀 채널에 보내며 "주담당 파트도 보내 주시면 볼게요"라고 청한다 |
| collab_disagree | 리뷰와 같은 시점. `fixed_opinions`는 **1번 문제 정의의 원인 가정**(예: "다음 모임 일정을 놓쳐서"가 주원인이라는 가정 vs "아는 사람이 없어 어색해서"가 주원인이라는 가정)에 대한 고정 의견 1개와, 지원자가 같은 방향이면 쓰는 두 번째 의견이다. 적응성 변경(핵심 기능·일정)과 겹치지 않는다. 지원자가 보낸 1번 문서가 있으면 그 문장을 인용하고, 없으면 분업 때 정한 방향 또는 킥오프 기본 가정에 대해 말한다 |
| honesty_report | [TBD, CX-12: 01:50 요청 카드는 유지(세부 설계 제안): 완료 전이면 팀 채널 재촉, 조기 완료로 앞당겨 실행되면 한서윤 DM 요청. 완료 전 메시지는 마감 보고로 인정하지 않음. 구현 전 사용자 확인 필요. 조기 완료 시 발화는 한서윤 DM으로 옮겨 실행하므로 "완료 뒤 팀 채널 재촉 없음"과 충돌하지 않음. 완료 시 안내는 "최종본이 한서윤에게 전달되었고 한서윤 DM에서 보고하면 된다"로 바뀜] 이전 초안: 팀장이 팀 채널에서 보고를 요청하며 "다 됐다고 전해도 되죠?"를 붙인다. 같은 시점에 시스템 줄 "최종본은 오른쪽 탭에서 제출합니다. 제출하면 세션이 끝납니다"가 붙는다. 만료 자동 제출 뒤의 요청에는 "한 줄이면 됩니다. 안 써도 제출은 유효합니다" |

## 조립 (`positions.scenario`)

채용 건 생성 시 api가 한 번 계산해 저장한다. 미션 폴더(`scenarios/missions/<mission_id>/`) 전체 내용의 해시를 `catalog_version`으로(문서·프롬프트 본문만 바뀌어도 버전이 바뀜), 카드 내용·회사 문서 본문·프롬프트 본문을 scenario JSON에 복사해 고정한다. 실행 시 그래프는 scenario의 복사본만 읽는다. 계산은 `scenarios/version.py`의 `catalog_version(mission_id)` 하나를 api와 rag-mcp가 함께 쓴다(foundation 소유, 두 서비스가 `scenarios/`를 읽기 전용으로 마운트). 이후 카탈로그를 고쳐도 진행 중 채용 건은 바뀌지 않는다. RAG 색인도 같은 `catalog_version`을 키로 보존되므로(rag-mcp 설계) 검색은 채용 건에 고정된 버전의 청크만 본다.

```
L = session_minutes
fixed: kickoff 0, division L/12 (planning 선택 시 planning_division), review 3L/4,
       collab_disagree 3L/4 (collaboration 선택 시, attach_to review),
       report_request 11L/12 또는 제출 시 먼저 (honesty 선택 시 honesty_report)
middle = timing.middle_order 중 선택된 카드  # 도움 → 중간 점검 → 지연 → 변경
N = len(middle)
시점: L/4 + i*(L/2)/N  (i=0..N-1)      # N==1이면 L/4
planning 미선택: midpoint_draft texture L/2
responsibility_delay: 자료 공개 release_at_min = 카드 시각 + L/12
```

모든 시점(at_min, release_at_min)은 0.01분 단위로 반올림한다(비율 0.0833 → L=120에서 10). 킥오프 브리프의 `{interview_expected_time}`은 조립된 지연 카드의 **카드 시각**(`scenario.vars`, "01:00" 형식. 팀장이 예고한 시각이고 알림이 이 시각에 온다)이며, 실제 공개는 `release_at_min`(`{release_time}`, "01:10")이다. 책임감 미선택이면 "시작 시 공유됨"이다.

L=120, 5개 전부 선택: planning_division 10, collab_help 30, planning_checkin 45, responsibility_delay 60(공개 70), adaptability_change 75, review·collab_disagree 90, honesty_report 110(또는 제출 시).
L=120, 3개(협업·책임·적응): division(흐름) 10, collab_help 30, responsibility_delay 50(공개 60), midpoint_draft(texture) 60, adaptability_change 70, review·collab_disagree 90, report_request(흐름) 110.
L=120, 1개(계획성): planning_division 10, planning_checkin 30, review 90, report_request 110.
L=6, 5개 전부: 0.5, 1.5, 2.25, 3(공개 3.5), 3.75, 4.5, 5.5분.

저장 형식:

```json
{"mission_id": "planning", "session_minutes": 120,
 "cards": [
  {"card_id":"kickoff","at_min":0,"flow":true},
  {"card_id":"planning_division","element":"planning","at_min":10,"window_start_min":0},
  {"card_id":"collab_help","element":"collaboration","at_min":30},
  {"card_id":"planning_checkin","element":"planning","at_min":45,"sends_document":{"parts":"colleague_all","version":1}},
  {"card_id":"responsibility_delay","element":"responsibility","at_min":60,"effects":{"release_document":"interview_summary","release_at_min":70}},
  {"card_id":"adaptability_change","element":"adaptability","at_min":75},
  {"card_id":"review","at_min":90,"flow":true,"sends_document":{"parts":"colleague_all","version":2}},
  {"card_id":"collab_disagree","element":"collaboration","at_min":90,"attach_to":"review"},
  {"card_id":"honesty_report","element":"honesty","at_min":110,"or_on_submit":true}],
 "parts": {"1":{"title":"문제 정의와 대상 사용자"},"2":{"title":"사용자 인터뷰에서 찾은 근거"},"3":{"title":"핵심 기능 제안","depends_on":[2]},"4":{"title":"비슷한 서비스 사례"},"5":{"title":"성공 지표와 출시 일정"}},
 "division_min": {"2": ["candidate"], "3": ["colleague", "both"], "any_colleague_only": [4, 5]},
 "final_template": {"sections":[{"part_no":1,"title":"문제 정의와 대상 사용자"},{"part_no":2,"title":"..."}],"length":"섹션당 5~10줄, 1~2쪽"},
 "vars": {"interview_expected_time":"01:00","release_time":"01:10"},
 "releases_at_start": ["company_intro","metrics","policy","meeting_notes"]}
```

`division_min`(분업 최소 조건): 2번은 지원자(candidate), 3번(2번에 의존)은 동료(colleague) 또는 같이(both), 4·5번 중 하나 이상은 동료 단독(colleague). 책임감 카드(2번 자료 지연이 동료 파트에 영향)와 정직 카드(동료 문서와 최종본 출처 대조)의 전제가 모든 분업에서 성립하게 한다. 동료가 되돌리는 횟수는 1회이고 이유는 의존 관계("3번이 2번 자료를 받아 이어 쓰는 흐름")다.

세션 시작 시 api가 `cards`를 `session_events`로(collab_disagree도 별도 행, review와 같은 due_at), `releases_at_start`와 지연 공개를 `document_releases`로, 파트별 지원자 문서와 최종본을 `documents`로, 보드는 빈 상태로 둔다(CX-02, 2026-10-21. 할 일은 사용자가 만들고, 섹션 담당은 `division.parts`에 별도로 둔다). 같은 due_at의 이벤트는 카드 순서대로 한 실행에서 처리한다. `or_on_submit` 카드는 제출 시 아직 pending이면 그 자리에서 실행된다(`data-model.md`의 `reporting` 상태).

**분업 확정 경로**: 지원자가 섹션 담당 5개를 정하고 **분업안 공유**를 누르면 `division_min`을 검사해 api가 division을 확정한다(decided_by=candidate, WS `division.confirmed`, 동료 그래프에 stimulus). 할 일(task)은 주담당이 자유롭게 만들고, 섹션당·총 개수는 공유 검사 대상이 아니다. 할 일 담당은 실행 담당이며 섹션 담당을 자동으로 바꾸지 않는다(2026-10-21 결정). 할 일 담당과 섹션 담당의 불일치 방지 규칙만 TBD. 채팅으로 정한 섹션 담당은 동료의 `set_division` 도구가 섹션 담당 draft에 쓰고, 지원자 확인 뒤 같은 검사를 거쳐 스냅샷을 만든다(할 일 행은 만들지 않음). 확정 뒤 섹션 담당 변경은 draft에 저장되고 새 분업안 공유로 스냅샷을 만들 때 적용된다(설계 선택, decisions 2026-10-21). 다음 요소 카드까지 미확정이면 동료가 `default_division`을 섹션 담당 draft에 쓰고 같은 검사로 스냅샷(decided_by=colleague_default)을 만든다. 할 일 행은 만들지 않는다.

## 관찰 창

창은 **카드 단위**다. 요소 카드의 창은 그 카드가 실행된 시각부터 **다음 요소 카드(어느 요소든)의 실행**까지다. 예외는 `planning_division`으로, 창은 **세션 시작(0)**부터 첫 중간 카드까지다(카드 전에 정한 계획도 같은 창 안. `window_start_min: 0`). 흐름 카드와 texture는 창을 닫지 않으며, 같은 시각에 흐름 카드와 요소 카드가 함께 있으면(리뷰 + collab_disagree) 요소 카드 기준으로 창을 연다. 마지막 창은 **종료**(`completed_at`: 종료 버튼 시각, 종료 버튼이 없으면 제출 후 5분 자동 종료 시각. 2026-10-21 fallback)까지라 마감 보고 메시지도 들어간다. 그래프 State의 `current_card`가 열린 창을 가리키고, 요소 카드 경계와 종료에서 열린 창을 닫아 관찰을 기록한다(키 `(session_id, card_id, window_start)`). 창 안의 지원자 메시지, 지원자 문서의 자동 저장(document_revisions)·보낸 버전(document_shares), 받은 문서 열기(document_opens), 보드 변경(task_events), 회사 문서 열람(doc_views), 어시스턴트 호출이 observe의 입력이다. 창 밖 근거는 메시지 타입만 `related_card`로 허용한다. 흐름 카드 자체는 관찰 요소가 없다. AI 활용은 창과 무관하게 세션 전체를 본다. 약속 이행(`promise_kept`)만 세션 종료 때 다시 계산해 갱신한다(`rubric.md`).

## 회사 문서 (`scenarios/missions/planning/documents/`)

| id | 파일 | 역할 |
|---|---|---|
| `company_intro` | company_intro.md | 루프랩·모아런 소개 |
| `metrics` | metrics.md | 재참여율 22% 등 지표 |
| `interview_summary` | interview_summary.md | 첫 참여자 8명 인터뷰. responsibility_delay 카드의 지연 대상, 2번 파트의 자료 |
| `policy` | policy.md | 운영 정책. 배경 제약(관찰 대상 아님) |
| `meeting_notes` | meeting_notes.md | 재참여율을 최우선 과제로 정한 회의 |

## 디브리핑

`session_events`에서 `element`가 있고 status가 done인 행만 골라 scenario에 고정된 `debrief` 문장(카드별 7문장)을 보여 준다. collab_disagree도 별도 행이므로 빠지지 않는다. 제출로 실행된 honesty_report도 done이면 포함된다. 함께 보여 주는 것: 점수를 보여 주지 않는 이유, 기업이 보는 것(대화·어시스턴트 요청 원문), 응답 시간 항목의 리모트 맥락 한 줄, 끊긴 구간이 있었으면 담당자에게 알리라는 안내, 기록 보관 90일, 문의 창구(담당자 이메일), 제출한 최종본 읽기 전용 열람·복사(종료 후 7일, `debrief_token`), 종료 설문 2문항(자연스러웠는지·공정했는지, 1~5).
