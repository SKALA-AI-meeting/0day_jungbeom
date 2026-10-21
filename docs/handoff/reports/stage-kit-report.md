# stage-kit 보고서

## 만든 것

- 단계 시드 5개 `scenarios/e2e/stages/{keyword,problem,solution,proposal,ended}.yaml`. 각 파일은 그 단계 직전까지를 독립적으로 재생한다(키워드 물 → 문제 상황 `water_p2` → 해결책 `water_s1`, 강한결·서지안은 `fire`·`water_p1`·`water_s2` 등 다른 안을 냄, ended는 기획안 칸 + 제출). `keyword`는 `steps: []`.
- `scripts/make_session.py`: 옛 요소 선택 버전을 교체. `--start-at`·`--stage`·`--minutes 15|60`·`--llm fake|live`·`--alias`·`--admin-email`. 내부 `POST /internal/test/sessions` 한 번만 부르고 `session_id`·`invite_url`·`phase`·(`session_token`·`debrief_token`·`admin_report_url`)과 LLM 스택 안내 한 줄을 출력한다.
- `scripts/stage_advance.py`: `--sid`, `--to deadline|idle|card:<id>|<초>`.
- Makefile `stage`·`stage-advance`(`.PHONY` 포함). `scripts/README.md` 두 줄(시드 직후 `session_cards.locked_option_id`·`card_progress`가 비고 problem 기준안은 첫 card_due 때 잠긴다는 한 줄 포함).

## 명령

```
make stage STAGE=problem [MIN=15] [LLM=fake|live]
make stage-advance SID=<세션 id> TO=deadline|idle|card:listening_pressure|90
```

## 검증 (격리 DB, 실 스택 미사용)

- `services/api/tests/test_stage_seeds.py` 7건 통과: 시드 4단계가 각각 in_progress·해당 phase·앞 단계 칸 confirmed, `ended`는 completed + debrief_token·admin_report_url, problem 시드에서 `advance TO=deadline` + 스케줄러 틱 뒤 문제 상황 칸이 `resolution=timeout`, 두 스크립트 인자 파싱.
- `make test` 전부 통과(root 125, api 143, debate-mcp 15, rag-mcp 10, assessment-mcp 20, report-worker 30, web 25). `make lint` 통과.

## 알아 둘 것

- 옛 `make_session.make(public, internal, elements, minutes, ...)`·`Made`·`signup`·`Admin`은 제거했다. `tests/e2e/auth.py`·`tests/eval/evaluate.py`가 아직 이를 import한다(e2e 트랙 소유, 요소 선택 폐지에 맞춰 e2e 트랙이 고쳐야 한다).
- 시드의 `at`은 15분 세션 기준 분이다. 60분 세션도 같은 값으로 재생하므로 앞쪽에 몰린다(재생 뒤 단계 마감은 api가 다시 잡는다).
- api 버그는 찾지 못했다.

## 실 스택에서 확인할 것

- `LLM_FAKE=1` 스택에서 `make stage STAGE=<단계>`로 만든 초대 링크가 해당 단계 화면으로 열리는지, 시드 직후 그래프가 phase_started 발언을 내는지.
- `make stage-advance TO=idle`(침묵 초대 1건), `TO=card:<id>`(카드 발언), `TO=deadline`(시간 초과 R7 문구).
- `ended` 시드의 리포트가 워커에서 만들어져 관리자 리포트 링크가 열리는지.
- `LLM=fake|live` 전환은 스택 env(`LLM_FAKE`) 재기동이 필요하다(스크립트는 안내만).
