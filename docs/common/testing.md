# 테스트와 기록

## 단위
- `observe` 규칙 함수(순수 함수), `guard`, 시나리오 조립, 재사용 판별은 pytest로 고정 입력 테스트.
- MCP 도구는 api를 mock한 상태로 입력 검증과 오류 형식 테스트.

## e2e

### 세션 조립
```
python scripts/make_session.py --elements cooperation,responsibility,flexibility,respect --minutes 6
```
내부 테스트 API로 채용 건·초대·세션을 즉시 만들고 토큰을 출력한다.

### 대본 (`scenarios/e2e/*.yaml`)
```yaml
name: all_four
elements: [cooperation, responsibility, flexibility, respect]
minutes: 6
steps:
  - at: kickoff            # 카드 id 또는 분
    say: {channel: team, content: "안녕하세요, 잘 부탁드립니다."}
  - at: division
    say: {channel: dm, content: "분담안 좋아요. 그대로 갈게요."}
  - at: cooperation
    say: {channel: dm, content: "지금 2번 쓰는 중인데 10분 뒤에 같이 볼까요?"}
  - at: responsibility
    say: {channel: team, content: "인터뷰 자료가 늦어서 2번이 조금 늦어질 것 같아요. 1번 먼저 끝내 둘게요."}
    write: {part_no: 1, content: "..."}
  - at: 2.0
    assistant: "지표 현황 기준으로 재참여율 문제를 요약해줘"
  - at: report_request
    say: {channel: team, content: "기획안 공유드립니다."}
    submit: true
```
기본 대본 3개: `all_four`, `one_element`(협력만), `division_refuse_3x`.

### 러너 (`tests/e2e/run.py`)
세션을 만들고 WS·REST로 대본을 진행한다. 카드 발생은 `message.new`의 `event_id`로 감지한다. 종료 후 리포트가 `report_ready`가 될 때까지 대기(최대 120초).

### 기록 (`tests/e2e/records/<YYYYMMDD-HHMM>-<name>/`)
- `transcript.jsonl`: 모든 WS 이벤트와 REST 호출
- `observations.json`, `report.json`
- `summary.md`: 카드별 예정·실제 시각과 오차, 단언 결과, LangSmith trace URL

### 단언
1. 선택 카드가 모두 발생하고 오차 ±10초
2. 미선택 카드 미발생, 미선택 요소 섹션 없음
3. 리포트에 금지어 없음(점수, 합격, 불합격, 순위, 점 등 패턴)
4. 어시스턴트 미사용 대본에서 `ai_usage.used=false`
5. 세션 상태가 report_ready 도달
6. `restart` 대본: 중간에 api 컨테이너 재시작 후 `/state`가 이어지고 남은 카드가 발생
