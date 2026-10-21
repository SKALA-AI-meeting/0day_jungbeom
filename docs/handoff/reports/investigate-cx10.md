# investigate-cx10 보고: 인터뷰 요약 질문에 동료가 진행 현황으로 답한 원인

읽기 전용 조사. 코드·문서 변경 없음. 실제 LLM이나 네트워크는 호출하지 않았다. 규칙 함수와 템플릿 함수만 로컬에서 실행해 확인했다.

## 1. 재현 경로

1. **메시지**: 팀 채널에 주담당이 "왜 사용자 인터뷰 요약이 안올까요?"를 보냈다(약 22분).
2. **수신자 결정** `services/api/app/agent/session/classify.py:63-77`: 팀 채널 메시지에 이름이나 호칭이 없고 `_MANAGER_TOPIC`(마감·기한·보고·범위·일정)에도 해당하지 않아 `colleague`가 된다. 로컬 실행 결과도 `colleague`였다.
3. **kind 분류** `classify.py:173-258`, 호출 위치 `nodes.py:136-148`
   - LLM 입력(`classify.py:212`)은 `[카드 목록]`과 `[메시지]`뿐이다. 회사 문서 제목, 공개 여부, 킥오프 공지 일정은 들어가지 않는다.
   - `CLASSIFY_SYSTEM`(`classify.py:33-60`)은 progress_query를 "동료 파트의 진행 상황을 묻는다"로만 정의한다(`:45`). 회사 자료가 언제 공개되는지 묻는 질문을 어떻게 분류할지는 적혀 있지 않다.
   - LLM 결과를 사후 보정하는 경우는 report를 강등할 때뿐이다(`:238-240`). progress_query를 다시 검증하는 경로는 없다.
4. **노드 분기** `nodes.py:167-183`: negotiate 조건에 해당하지 않아 `respond`로 간다.
5. **respond** `nodes.py:471-473`: `persona == "colleague" and kind == "progress_query"`이면 `_progress_reply`(`:341-380`)로 바로 간다.
   - 이 경로는 LLM 응답 생성, 문서 검색, 최근 대화(킥오프 공지 포함), 미공개 문서 확인(`_unreleased_asked`, `:484-488`), "아직 공유되지 않은 자료" 고정 문장(`:519-521`)을 **모두 건너뛴다**.
   - `part_no`가 없으므로 동료 담당 파트 전체(3·4·5)가 대상이 된다. 비어 있는 `progress`는 별도 LLM 호출(`:357-373`)로 명사구를 만들어 채운다.
   - 결과는 `progress_text` 템플릿(`:334-338`) "지금 N번은 …, …이에요."로 만들어진다.

## 2. 원인

### 확인된 것
- 관찰된 답변은 `progress_text` 출력과 글자 단위로 일치한다. `progress_text({3:'후속 모임 기능 아이디어 정리 중',4:'사례 조사 중',5:'기능 설계 초안 작성 중'})`를 로컬에서 실행해 같은 문장이 나오는 것을 확인했다. 따라서 응답은 `nodes.py:471-473`의 progress_query 분기에서 나왔다.
- 규칙 분류 폴백 `rule_kind`(`classify.py:123-135`)는 이 메시지를 `question`으로 본다(`_PROGRESS` 정규식이 일치하지 않음, 로컬 실행으로 확인). 따라서 progress_query는 **LLM 분류 결과**다. 규칙 폴백으로 분류됐다면 question 경로를 탔을 것이다.
- question으로 분류됐다면 현재 코드도 올바르게 답했을 것이다. `guard_patterns.yaml:136`의 별칭('인터뷰 요약')으로 `_unreleased_asked`가 미공개 문서를 찾고, "사용자 인터뷰 요약 문서는 아직 공유되지 않은 자료예요."가 앞에 붙는다. LLM은 최근 대화의 킥오프 공지(`cards.yaml:25`, "{interview_expected_time}쯤 공유 예정")와 `common_rules.md:38`("킥오프에서 공지한 일정은 공지된 그대로만 말한다")을 근거로 답할 수 있다.
- 지연 알림(`cards.yaml:79-89`)은 `channel: notice`로 지원자에게만 간다. `prompts.py:15`의 `VISIBLE_CHANNELS`가 notice를 제외하므로 동료 컨텍스트에는 들어가지 않는다. 현재도 지연 사실이 누설되는 경로는 없다.

### 추정(미확인)
- LLM이 progress_query를 고른 이유: 분류기는 "사용자 인터뷰 요약"이 회사 문서 제목이라는 것과 아직 공개되지 않았다는 사실을 모른다. 그래서 "왜 ~ 안 올까요"를 동료에게서 와야 할 산출물을 기다리는 말로 읽었을 가능성이 높다. 2번 파트 제목 '사용자 인터뷰에서 찾은 근거'와 이름이 겹친다는 점도 영향을 줬을 수 있다.
- 실제 세션의 `messages.meta.classification`(DB)은 조회하지 않았다. 확인하려면 `/internal/sessions/{id}/messages`에서 해당 메시지의 `kind = progress_query`를 보면 된다.

### 부수 문제
- progress_query로 잘못 분류되면 그때 만든 진행 명사구가 `work_notes.progress`에 남는다. 이후 진짜 진행 질문에도 같은 답이 반복된다. 5번(성공 지표와 출시 일정)에 '기능 설계 초안 작성 중'이 붙은 것처럼 파트 제목과 맞지 않는 명사구도 그대로 굳는다.

## 3. 수정안

| 안 | 내용 | 장단점 |
|---|---|---|
| A. 프롬프트 | `CLASSIFY_SYSTEM`에서 progress_query를 "동료가 맡은 파트 작업의 진행"으로 좁히고, "회사 문서·자료의 공개 여부나 시점을 묻는 말은 question"이라고 명시한다. 분류 입력에 문서 제목 5개를 넣는다. colleague.md 7절에서도 '진행 질문'의 범위를 같은 기준으로 맞춘다 | 비용이 낮지만 LLM 판단에 기댄다(CX-03처럼 어길 수 있음) |
| B. 컨텍스트 주입 | respond의 question 경로에 결정적 '자료 상태' 메모를 추가한다: 미공개 문서 제목과 **킥오프에서 공지한 예정 시각만**(`interview_expected_time`) 넣고, 실제 공개 시각(`release_time`)과 지연 여부는 넣지 않는다. 최근 30개 대화나 요약에서 킥오프 공지가 밀려나도 답할 수 있다 | 답변 품질을 보장한다. 하지만 분류가 틀리면 이 경로에 도달하지 못한다 |
| C. 응답 검증(결정적 보정) | 분류 뒤 `guard.cited_docs(content)`가 회사 문서(특히 미공개 문서)를 가리키는데 kind가 progress_query이면 question으로 강등한다. report 강등(`classify.py:238-240`)과 같은 방식이다. fixture도 추가한다: "왜 인터뷰 요약이 안 와요?"에서 kind=question, 응답에 '아직 공유되지 않은'과 공지된 예정 시각이 있고 '늦어', '10분', 지연 후 공개 시각이 없어야 한다 | 모델 문구에 기대지 않는 보장이다. 비용이 낮다 |

**권장: C + B를 기본으로 하고 A로 보강한다.** C로 경로가 틀리지 않게 막고, B로 정직하게 답하게 하며("킥오프 때 10:00쯤이라고 들었는데 저도 아직 못 봤어요"), A로 비슷한 다른 표현에서 생기는 오분류를 줄인다. 예정 시각이 지난 뒤(지연 카드 발화 후)에도 동료는 "공지된 시각이 지났는데 아직 못 봤다"까지만 말하고 지연 이유나 새 공개 시각은 말하지 않는다.

## 4. 계약 변경 여부

- **`docs/common/contracts.md` 변경 불필요.** classification의 kind 집합(`contracts.md:224`, `tests/contract_shape.py:61`)은 그대로 쓰고 기존 `question`으로 보정한다. 새 kind(예: material_query)를 만들면 contracts.md, `docs/agent/design.md:113`, observe, 계약 테스트까지 바꿔야 하므로 권하지 않는다.
- B는 에이전트 내부 컨텍스트 변경이다. 미공개 문서는 내용 없이 제목과 공지된 예정 시각만 넣으므로 `prompts.py:119-137`의 기존 '미공개: 제목' 방식과 같다. `docs/common/harness.md`의 Context 허용 목록에 '공지된 자료 예정 시각' 한 줄을 추가하는 정도의 문서 갱신이면 충분하다.

## 5. 담당 트랙

- **flow-agent** (`services/api/app/agent/`): 주 담당. C(`session/classify.py` 강등, `nodes.py` 분기), B(`session/prompts.py` 자료 상태 블록, `nodes.py` respond), A 중 `CLASSIFY_SYSTEM`을 맡는다.
- **flow-scenario** (`scenarios/missions/`): colleague.md 7·8절의 '진행 질문'과 '자료 시점 질문' 문구, `prompts/fixtures/`(grounding·context_leak)에 CX-10 케이스 추가, 필요하면 kickoff brief의 시각 변수를 정리한다.

## 6. 새 흐름과 맞출 점

- **채널 역할(CX-01)**: 자료 공개 시점은 팀 공동 정보이므로 팀 채널에서 받은 질문은 팀 채널에서 답하는 현재 동작을 유지한다. 지연 알림은 개인 알림이므로 주담당이 직접 팀 채널이나 DM에 밝히기 전에는 어느 채널에서도 동료가 언급하지 않는다. "자료 공유 일정 언제예요?"처럼 '일정'이 들어가면 `_MANAGER_TOPIC` 때문에 팀장에게 라우팅된다. 따라서 B의 자료 상태 메모와 C의 보정은 팀장 페르소나에도 똑같이 적용해야 한다.
- **오피스 시계(CX-11, 09:00–11:00)**: 현재 `{interview_expected_time}`은 경과 시간 "01:00"이고 `prompts.py:42-46` `_clock`도 경과 시간(00:22)을 표시한다. 수정할 때는 킥오프 brief 변수, 자료 상태 메모의 예정 시각, 최근 대화 타임스탬프를 하나의 오피스 시계 포맷터로 통일해야 한다(예: "10:00쯤"). 그래야 동료의 답과 화면 시계가 같은 기준이 된다. 지연 후 공개 시각은 계속 동료·팀장 컨텍스트에 넣지 않는다.
