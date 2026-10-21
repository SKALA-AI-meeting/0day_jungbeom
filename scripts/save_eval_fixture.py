"""실 스택에서 끝난 세션의 SessionRecord를 eval 픽스처로 저장한다.

    uv run --project services/api python scripts/save_eval_fixture.py <session_id> [--out DIR]

assessment-mcp `get_session_record`(평가 에이전트의 입력 묶음, contracts.md "SessionRecord")를
그대로 받아 `tests/eval/fixtures/sessions/<session_id>.json`에 쓴다. 평가 에이전트를 세션 없이
다시 돌려 보는 경로는 이것 하나다(그래프·워커 단독 실행기는 두지 않는다). 토큰은
env(`ASSESSMENT_MCP_TOKEN`)에서만 읽고 출력하지 않는다.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "tests" / "eval" / "fixtures" / "sessions"
RECORD_KEYS = {
    "session",
    "seats",
    "messages",
    "slots",
    "proposal",
    "observations",
    "facts",
    "contributions",
}

Fetch = Callable[[str], Awaitable[dict[str, Any]]]


async def fetch_record(session_id: str, url: str, token: str) -> dict[str, Any]:
    """assessment-mcp(Streamable HTTP) get_session_record 호출. 응답의 data를 돌려준다."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url, headers={"X-Assessment-Token": token}) as (
        read,
        write,
        _,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_session_record", {"session_id": session_id})
    body = json.loads(" ".join(getattr(c, "text", "") for c in result.content))
    if not body.get("ok"):
        raise RuntimeError(f"get_session_record failed: {body.get('error')}")
    return body["data"]


def check_shape(record: dict[str, Any]) -> None:
    missing = RECORD_KEYS - set(record)
    if missing:
        raise ValueError(f"SessionRecord에 {sorted(missing)}가 없음")


async def save(session_id: str, fetch: Fetch, out: Path = DEFAULT_OUT) -> Path:
    record = await fetch(session_id)
    check_shape(record)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{session_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return path


def main() -> None:
    sys.path[:0] = [str(REPO_ROOT / "tests")]
    from e2e.client import env

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("session_id")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    values = env()
    url = values.get("E2E_ASSESSMENT_MCP_URL") or values.get(
        "ASSESSMENT_MCP_URL", "http://localhost:9103/mcp"
    )
    token = values.get("ASSESSMENT_MCP_TOKEN", "")

    async def fetch(session_id: str) -> dict[str, Any]:
        return await fetch_record(session_id, url, token)

    print(asyncio.run(save(args.session_id, fetch, args.out)))


if __name__ == "__main__":
    main()
