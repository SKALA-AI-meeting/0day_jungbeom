# api-candidate rebase 후속 보고

- 브랜치 `track/api-candidate`(main 위로 rebase된 상태: `99cbdba` → `82f5f8b` → 새 커밋)
- 커밋: **`45c7bb1`** 시작 공개 문서를 start()가 즉시 공개하는 규칙에 맞춰 내부 문서 목록 테스트의 기대값과 주석을 고침
- 변경 파일은 `services/api/tests/routers/test_internal.py` 한 개(4줄 추가, 3줄 삭제). 다른 파일은 바꾸지 않았다. 작업 트리 깨끗함. push 안 함

## 고친 내용 (`test_documents_listing_and_release_are_idempotent`)
| 위치 | 이전 | 이후 |
|---|---|---|
| 첫 목록 단언 | `released["interview_summary"] is False  # released_at은 공개되면 기록된다` | 주석 "시작 공개 4개는 start()가 즉시 released_at을 기록하고, interview_summary만 지연 공개다" + `released["interview_summary"] is False and released["metrics"] is True` |
| 수동 공개 주석 | "시작 시 펼친 예약의 released_at은 스케줄러가 기록한다. 여기서는 직접 공개한다." | "지연 공개의 released_at은 스케줄러가 기록한다. 여기서는 직접 공개한다." |
| 공개 뒤 단언 | `flags["metrics"] is False` | `flags["metrics"] is True` |

`document.released` 1회, 재요청 멱등, 404, doc_views 빈 배열 단언은 그대로다.

## 검증
| 명령 | 결과 |
|---|---|
| `cd services/api && uv run pytest -q` | **31 passed**, 43 warnings(PyJWT 키 길이 경고 등, 실패 아님) |
| `uv run ruff check`·`ruff format --check` (고친 파일) | 통과 |

## 실시간 검증 (rebase 전 코드 `9bfe0c9`, 실제 5초 루프로 L=6 세션 6분)
명령: `cd services/api && PYTHONPATH=. uv run python /private/tmp/claude-501/-Users-zaehorang-SKALA-Day65-AI-Agent-Capstone-MCP-2-assignments-Day-0-zaeho-worktrees-api-candidate/3d4d8df8-9ea0-4d2a-bbe2-ed4b919b9a30/scratchpad/realtime_six_minutes.py` → exit 0

```
session status=completed
card            due_s  fired_s  done_s  fired-due  done-due  status
kickoff            0.0      0.0     0.0       0.0       0.0  done
division          30.0     30.1    30.2       0.1       0.2  done
cooperation       90.0     90.3    90.3       0.3       0.3  done
responsibility   150.0    150.5   150.5       0.5       0.5  done
midpoint_draft   180.0    180.5   180.6       0.5       0.6  done
flexibility      210.0    210.6   210.7       0.6       0.7  done
respect          270.0    270.8   270.8       0.8       0.8  done
review           270.0    270.8   270.8       0.8       0.8  done
report_request   330.0    330.9   331.0       0.9       1.0  done
worst |offset| = 1.0s (limit 10s)
published report.generate at +361.1s (ends_at +360s)
session.ended frames: [{'type': 'session.ended', 'payload': {'reason': 'timeout'}}]
PASS events == 9
PASS all done
PASS worst offset <= 10s
PASS completed
PASS published once
```

스크립트 결함 하나: 이 실행에서 PASS/FAIL 루프 변수가 임시 DB 이름 변수(`name`)를 덮어써 정리 단계가 다른 이름을 지웠고, 임시 DB `dayzero_rt_f7b33116`이 남았다. 내 실행이 만든 DB임을 확인하고 직접 지웠으며, 루프 변수 이름을 바꿨다(스크래치 파일, 커밋 대상 아님). 정리까지 확인하는 재실행 결과: RERUN_PLACEHOLDER
