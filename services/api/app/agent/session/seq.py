"""노드별 고정 seq 슬롯(docs/agent/design.md 재실행 멱등 규칙).

seq는 순서 카운터가 아니라 슬롯이다. 같은 (run_id, seq) 메시지는 한 번만 저장되므로
재실행해도 결과가 한 벌로 수렴한다. inject는 묶음 안 카드 순번을 더한다(스케줄러가 묶음 전체를
카드 순서로 넘기는 것과 짝).
"""

KICKOFF_MANAGER = 1
KICKOFF_GREETING = 2
INJECT = 1  # + 묶음 안 카드 순번
RESPECT_EXTRA = 2
REVIEW_SHARE = 1
REVIEW_COMMENT = 2
RESPOND = 1
FALLBACK = 9
