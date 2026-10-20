"""compose healthcheck용 heartbeat 파일. 30초마다 갱신하고, 90초 넘게 오래되면 unhealthy다."""

import asyncio
import os
import time
from pathlib import Path

INTERVAL_SECONDS = 30


def heartbeat_path() -> Path:
    return Path(os.environ.get("HEARTBEAT_PATH", "/tmp/heartbeat"))


def beat(path: Path | None = None) -> Path:
    path = path or heartbeat_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(time.time())))
    return path


async def run(path: Path | None = None, interval: float = INTERVAL_SECONDS) -> None:
    while True:
        beat(path)
        await asyncio.sleep(interval)
