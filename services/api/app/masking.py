"""지원자 메시지의 민감정보 마스킹. 저장 전에 적용한다."""

import re

EMAIL_MASK = "[이메일]"
PHONE_MASK = "[전화번호]"

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 휴대전화·지역번호·국제(+82) 형식. 구분자는 공백·하이픈·점.
_PHONE = re.compile(
    r"(?<!\d)(?:\+82[-.\s]?(?:0?1[016789]|0?[2-6]\d?)|01[016789]|0[2-6]\d?)"
    r"[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"
)


def mask(text: str) -> str:
    return _PHONE.sub(PHONE_MASK, _EMAIL.sub(EMAIL_MASK, text))
