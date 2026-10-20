"""입력 예산용 토큰 계산(gpt-4o-mini 인코딩, tiktoken).

한국어는 글자당 토큰 수가 글자마다 크게 달라서(예: '가' 1, '힣' 2) 글자 수로 근사하지 않고 실제
인코딩으로 센다. 메시지 하나의 형식 오버헤드는 OpenAI 채팅 형식 기준으로 더한다.
"""

from functools import lru_cache

import tiktoken

from app.agent.llm import MODEL

MESSAGE_OVERHEAD = 4  # 메시지마다 붙는 역할·구분 토큰
REPLY_PRIMING = 3  # 응답 시작 토큰


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.encoding_for_model(MODEL)


def count(text: str) -> int:
    return len(_encoding().encode(text, disallowed_special=()))


def truncate(text: str, limit: int) -> str:
    """앞에서부터 limit 토큰까지. 끝에서 잘린 글자(바이트 일부)는 버린다."""
    tokens = _encoding().encode(text, disallowed_special=())
    if len(tokens) <= limit:
        return text
    return _encoding().decode(tokens[: max(limit, 0)]).rstrip("�")


def messages_total(contents: list[str]) -> int:
    """모델에 보내는 메시지 목록의 입력 토큰(본문 + 형식 오버헤드)."""
    return sum(count(c) + MESSAGE_OVERHEAD for c in contents) + REPLY_PRIMING
