"""시계 주입. 시간 로직(마감·카드·침묵 초대·만료)은 이 시계로만 now를 읽어 가짜 시계로
테스트한다."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 10, 21, 1, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> datetime:
        self.current += timedelta(**delta)
        return self.current

    def set(self, value: datetime) -> None:
        self.current = value


class MonotonicClock:
    """행 생성 시각이 겹치지 않게(메시지·입장 정렬은 created_at) 1µs씩 앞으로만 가는 시계."""

    def __init__(self, base: Clock) -> None:
        self.base = base
        self._last: datetime | None = None

    def now(self) -> datetime:
        value = self.base.now()
        if self._last is not None and value <= self._last:
            value = self._last + timedelta(microseconds=1)
        self._last = value
        return value
