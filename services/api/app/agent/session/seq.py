"""노드별 고정 seq 슬롯(docs/agent/design.md 재실행 멱등 규칙).

seq는 순서 카운터가 아니라 슬롯이다. 같은 (run_id, seq) 메시지는 한 번만 저장되므로 재실행해도
결과가 한 벌로 수렴한다. 카드 묶음의 주 메시지는 INJECT + 묶음 안 카드 순번이라 review(1)와
collab_disagree(2)가 겹치지 않는다. 문서 카드 메시지는 파트 번호×10(doc_seq).
"""

KICKOFF_MANAGER = 1
KICKOFF_GREETING = 2
INJECT = 1  # + 묶음 안 카드 순번
REVIEW_SHARE = 1
REVIEW_COMMENT = 2
CARD_NOTE = 3  # 카드에 붙는 시스템 줄(보고 요청의 "제출하면 종료")
DEFAULT_DIVISION = 4  # 미합의 중 카드 도래: "아직 안 정해져서 일단 이렇게 진행할게요"
RESPOND = 1
FALLBACK = 9


def doc_seq(part_no: int | str) -> int:
    return int(part_no) * 10
