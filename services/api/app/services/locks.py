"""세션별 asyncio Lock. 메시지 자극·이벤트·종료 실행을 세션 단위로 직렬화한다.

api가 단일 프로세스라는 전제에서만 유효하다.
"""

import asyncio
import uuid
from collections import defaultdict


class SessionLocks:
    def __init__(self) -> None:
        self._locks: defaultdict[uuid.UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

    def __call__(self, session_id: uuid.UUID) -> asyncio.Lock:
        return self._locks[session_id]
