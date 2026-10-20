"""러너가 api를 부르는 길: REST(공개·내부)와 WebSocket. 오간 것은 전부 transcript에 남긴다.

토큰 값(세션 JWT·관리자 JWT·내부 토큰)은 기록하지 않는다. 응답 본문의 토큰 필드는 가린다.
"""

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import websockets

SECRET_FIELDS = {"token", "session_token", "debrief_token"}


def _redact(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: "<redacted>" if k in SECRET_FIELDS else _redact(v) for k, v in body.items()}
    if isinstance(body, list):
        return [_redact(v) for v in body]
    return body


@dataclass
class Transcript:
    """transcript.jsonl 한 줄 = 한 사건. at은 벽시계(초), 지연 p95 계산에도 쓴다."""

    lines: list[dict[str, Any]] = field(default_factory=list)

    def add(self, kind: str, **data: Any) -> dict[str, Any]:
        line = {"at": time.time(), "kind": kind, **data}
        self.lines.append(line)
        return line


@dataclass(frozen=True)
class Target:
    """대상 스택. 내부 토큰은 .env에서 읽어 넘기고 출력하지 않는다."""

    public_url: str
    internal_url: str
    internal_token: str
    database_url: str | None = None

    def ws_url(self, session_id: str, token: str) -> str:
        base = self.public_url.replace("http://", "ws://").replace("https://", "wss://")
        return f"{base}/ws/sessions/{session_id}?token={token}"


class Api:
    """REST 호출. token을 주면 Bearer, internal=True면 내부 앱과 X-Internal-Token."""

    def __init__(
        self,
        target: Target,
        transcript: Transcript,
        *,
        transports: dict[str, httpx.AsyncBaseTransport] | None = None,
    ) -> None:
        transports = transports or {}
        self.target = target
        self.transcript = transcript
        self.public = httpx.AsyncClient(
            base_url=target.public_url, timeout=60, transport=transports.get("public")
        )
        self.internal = httpx.AsyncClient(
            base_url=target.internal_url,
            timeout=60,
            headers={"X-Internal-Token": target.internal_token},
            transport=transports.get("internal"),
        )

    async def aclose(self) -> None:
        await self.public.aclose()
        await self.internal.aclose()

    async def call(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        internal: bool = False,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        log: bool = True,
    ) -> httpx.Response:
        client = self.internal if internal else self.public
        headers = dict(headers or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        started = time.time()
        response = await client.request(method, path, json=json_body, headers=headers)
        if log:
            try:
                body = response.json()
            except ValueError:
                body = response.text[:500]
            self.transcript.add(
                "rest",
                method=method,
                path=path,
                internal=internal,
                status=response.status_code,
                ms=round((time.time() - started) * 1000),
                request=_redact(json_body),
                response=_redact(body),
            )
        return response


class Socket:
    """WS 하나. 받은 프레임은 frames에 쌓고 wait_for로 조건을 기다린다."""

    def __init__(self, transcript: Transcript) -> None:
        self.transcript = transcript
        self.frames: list[dict[str, Any]] = []
        self.close_code: int | None = None
        self._ws: Any = None
        self._reader: asyncio.Task | None = None
        self._changed = asyncio.Condition()
        self._seq = 0

    async def connect(self, url: str) -> None:
        self._ws = await websockets.connect(url, max_size=None)
        self.close_code = None
        self.transcript.add("ws_open")
        self._reader = asyncio.create_task(self._read(self._ws))

    async def _read(self, ws: Any) -> None:
        try:
            async for raw in ws:
                frame = json.loads(raw)
                frame["_at"] = time.time()
                self.frames.append(frame)
                self.transcript.add("ws_in", frame=frame)
                async with self._changed:
                    self._changed.notify_all()
        except websockets.ConnectionClosed:
            pass
        finally:
            self.close_code = ws.close_code
            self.transcript.add("ws_close", code=ws.close_code)
            async with self._changed:
                self._changed.notify_all()

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            if self._reader is not None:
                await self._reader
            self._ws = None

    async def wait_for(
        self, match: Callable[[dict[str, Any]], bool], timeout: float, since: int = 0
    ) -> dict[str, Any] | None:
        """since 번째 프레임부터 match를 만족하는 첫 프레임. 시간 안에 없으면 None."""

        def found() -> dict[str, Any] | None:
            return next((f for f in self.frames[since:] if match(f)), None)

        async def wait() -> dict[str, Any]:
            async with self._changed:
                await self._changed.wait_for(lambda: found() is not None)
            return found()

        try:
            return await asyncio.wait_for(wait(), timeout)
        except TimeoutError:
            return found()

    async def send_message(
        self, channel: str, content: str, reply_to_doc: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """message.send 후 ack payload(없으면 None)."""
        self._seq += 1
        client_msg_id = f"e2e-{self._seq}-{int(time.time() * 1000)}"
        payload = {"client_msg_id": client_msg_id, "channel": channel, "content": content}
        if reply_to_doc:
            payload["reply_to_doc"] = reply_to_doc
        since = len(self.frames)
        frame = {"type": "message.send", "payload": payload}
        self.transcript.add("ws_out", frame=frame)
        await self._ws.send(json.dumps(frame, ensure_ascii=False))
        ack = await self.wait_for(
            lambda f: (
                (f["type"] == "message.ack" and f["payload"].get("client_msg_id") == client_msg_id)
                or f["type"] == "error"
            ),
            timeout=30,
            since=since,
        )
        return ack["payload"] if ack and ack["type"] == "message.ack" else None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
