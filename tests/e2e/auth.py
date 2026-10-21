"""단언 8 인증 경계. 결과는 `records/<일시>-auth/auth.md`.

타 기업 관리자의 채용 건·리포트·기록 조회 404, 타 세션 JWT로 /state 403, 동의 전 /state 401,
만료 JWT 401, X-Internal-Token 없이 /internal 401, 공개 포트 8000에서 /internal 404,
assessment-mcp 토큰 없이 `forbidden`, 진행 중 세션 previous_session_id 재초대 422,
재발급 뒤 옛 링크 404.
"""

import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import jwt

from e2e import records
from e2e.client import Api, Target, Transcript

McpProbe = Callable[[str], Awaitable[str]]
PASSWORD = "e2e-password-1234"


async def assessment_without_token(url: str, session_id: str) -> str:
    """토큰 없이 assessment-mcp 도구를 불러 응답(또는 거절 사유) 문자열을 돌려준다."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_rubric", {"session_id": session_id})
                return " ".join(getattr(c, "text", "") for c in result.content)
    except Exception as error:  # noqa: BLE001 - 접속 거절도 거절 사유로 본다
        return repr(error)


async def run(
    target: Target,
    out: Path,
    *,
    transports: dict[str, Any] | None = None,
    mcp_probe: McpProbe | None = None,
) -> bool:
    transcript = Transcript()
    api = Api(target, transcript, transports=transports)
    stamp = int(time.time() * 1000)
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    async def admin(tag: str) -> str:
        body = {
            "email": f"auth-{tag}-{stamp}@example.com",
            "password": PASSWORD,
            "company_name": f"co-{tag}",
        }
        return (await api.json("POST", "/admin/auth/signup", json_body=body))["token"]

    async def invite(token: str, position: str, tag: str, **extra: Any) -> dict[str, Any]:
        body = {"alias": f"auth-{tag}-{stamp}", "email": "auth@example.com", **extra}
        return await api.call(
            "POST", f"/admin/positions/{position}/invites", token=token, json_body=body
        )

    try:
        token_a, token_b = await admin("a"), await admin("b")
        position = await api.json(
            "POST",
            "/admin/positions",
            token=token_a,
            json_body={"name": "auth", "session_minutes": 15},
        )
        first = (await invite(token_a, position["id"], "1")).json()
        second = (await invite(token_a, position["id"], "2")).json()
        third = (await invite(token_a, position["id"], "3")).json()
        link = lambda invited: invited["invite_url"].rstrip("/").split("/")[-1]  # noqa: E731
        sid1, sid3 = first["session_id"], third["session_id"]

        for label, path in (
            ("채용 건 지원자 목록", f"/admin/positions/{position['id']}/candidates"),
            ("리포트", f"/admin/sessions/{sid1}/report"),
            ("전체 기록", f"/admin/sessions/{sid1}/record"),
        ):
            status = (await api.call("GET", path, token=token_b)).status_code
            record(f"타 기업 관리자의 {label} 조회", status == 404, f"HTTP {status} (기대 404)")

        jwt1 = (await api.json("POST", f"/s/{link(first)}/consent", json_body={}))["session_token"]
        jwt2 = (await api.json("POST", f"/s/{link(second)}/consent", json_body={}))["session_token"]
        status = (await api.call("GET", f"/sessions/{sid1}/state", token=jwt2)).status_code
        record("타 세션 JWT로 /state", status == 403, f"HTTP {status} (기대 403)")
        status = (await api.call("GET", f"/sessions/{sid3}/state")).status_code
        record("동의 전(토큰 없이) /state", status == 401, f"HTTP {status} (기대 401)")
        if target.jwt_secret:
            expired = jwt.encode(
                {
                    "sub": sid1,
                    "session_id": sid1,
                    "kind": "candidate",
                    "exp": int(time.time()) - 60,
                },
                target.jwt_secret,
                "HS256",
            )
            status = (await api.call("GET", f"/sessions/{sid1}/state", token=expired)).status_code
            record("만료 JWT로 /state", status == 401, f"HTTP {status} (기대 401)")
        else:
            record("만료 JWT로 /state", False, "JWT_SECRET을 읽지 못해 만료 토큰을 만들 수 없음")
        status = (
            await api.call(
                "GET", f"/internal/sessions/{sid1}", internal=True, use_internal_token=False
            )
        ).status_code
        record("X-Internal-Token 없이 /internal", status == 401, f"HTTP {status} (기대 401)")
        status = (
            await api.call(
                "GET",
                f"/internal/sessions/{sid1}",
                headers={"X-Internal-Token": target.internal_token},
            )
        ).status_code
        record("공개 포트 8000의 /internal", status == 404, f"HTTP {status} (기대 404)")

        probe = mcp_probe or (
            lambda sid: assessment_without_token(target.assessment_mcp_url or "", sid)
        )
        answer = await probe(sid1)
        record("assessment-mcp 토큰 없이 호출", "forbidden" in answer.lower(), answer[:120])

        await api.json("POST", f"/s/{link(first)}/start", token=jwt1)
        again = await invite(token_a, position["id"], "re", previous_session_id=sid1)
        code = again.json().get("error", {}).get("code")
        record(
            "진행 중 세션의 previous_session_id 재초대",
            again.status_code == 422 and code == "invalid_previous_session",
            f"HTTP {again.status_code} {code}",
        )

        old = link(third)
        await api.json("POST", f"/admin/sessions/{sid3}/reissue", token=token_a, json_body={})
        status = (await api.call("GET", f"/s/{old}")).status_code
        record("재발급 뒤 옛 링크", status == 404, f"HTTP {status} (기대 404)")
    finally:
        await api.aclose()

    path = records.folder(out, "auth")
    lines = ["# 인증 경계 (단언 8)", "", "| 항목 | 결과 | 응답 |", "|---|---|---|"]
    lines += [f"| {name} | {'통과' if ok else '실패'} | {detail} |" for name, ok, detail in checks]
    (path / "auth.md").write_text("\n".join(lines) + "\n", "utf-8")
    return all(ok for _, ok, _ in checks)
