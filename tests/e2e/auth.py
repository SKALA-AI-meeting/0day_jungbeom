"""단언 8: 인증 경계를 한 번에 확인하고 records/<일시>-auth/auth.md에 남긴다.

준비(세션 2개, 회사 2개, 완료 세션 1개)는 공개 API와 내부 API(테스트 세션·complete)로
만든다. 타 기업 접근은 존재를 숨기는 404다(testing.md). 만료 JWT는 .env의 JWT_SECRET으로
서명만 하고 값은 남기지 않는다.
"""

import time
from pathlib import Path
from typing import Any

import jwt

from e2e import records
from e2e.client import Api, Target, Transcript
from scripts import make_session

ALL = ["responsibility", "planning", "adaptability", "collaboration", "honesty"]
DIVISION = {1: "candidate", 2: "candidate", 3: "both", 4: "colleague", 5: "colleague"}


async def _start(api: Api, made: make_session.Made) -> str:
    r = await api.call("POST", f"/s/{made.invite_token}/consent")
    token = r.json()["session_token"]
    await api.call("POST", f"/s/{made.invite_token}/start", token=token)
    return token


async def checks(api: Api) -> list[dict[str, Any]]:
    """[{name, want, got}]. got은 실제 HTTP 상태."""
    a = await make_session.make(api.public, api.internal, ALL, 6, alias="auth-a")
    b = await make_session.make(api.public, api.internal, ALL, 6, alias="auth-b")
    other = await make_session.signup(api.public, "e2e 다른 회사")
    token_a, token_b = await _start(api, a), await _start(api, b)
    sid = a.session_id
    for part, assignee in DIVISION.items():
        await api.call(
            "PUT", f"/sessions/{sid}/tasks/{part}", token=token_a, json_body={"assignee": assignee}
        )
    mine = await api.call("GET", f"/sessions/{sid}/my-documents", token=token_a)
    candidate_doc = next(d["doc_id"] for d in mine.json()["documents"] if d["part_no"] == 1)
    # 완료 세션: b의 관리자 초대 세션(채용 건 b.position_id)을 시작 → 제출 → 내부 complete
    invited = make_session.Made(
        b.admin, b.position_id, "", "", b.invite_session_id, b.invite_link_token
    )
    token_done = await _start(api, invited)
    await api.call("POST", f"/sessions/{b.invite_session_id}/submit", token=token_done)
    await api.call("POST", f"/internal/sessions/{b.invite_session_id}/complete", internal=True)
    expired = jwt.encode(
        {
            "role": "candidate",
            "sub": sid,
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 60,
        },
        make_session.env().get("JWT_SECRET", ""),
        algorithm="HS256",
    )
    fresh = await make_session.make(api.public, api.internal, ALL, 6, alias="auth-c")
    other_auth = {"Authorization": f"Bearer {other.token}"}

    async def status(method: str, path: str, **kwargs: Any) -> int:
        return (await api.call(method, path, **kwargs)).status_code

    results = [
        (
            "타 기업 관리자 채용 건(지원자 목록)",
            404,
            await status("GET", f"/admin/positions/{a.position_id}/candidates", headers=other_auth),
        ),
        (
            "타 기업 관리자 리포트",
            404,
            await status("GET", f"/admin/sessions/{sid}/report", headers=other_auth),
        ),
        (
            "타 기업 관리자 전체 기록",
            404,
            await status("GET", f"/admin/sessions/{sid}/record", headers=other_auth),
        ),
        ("타 세션 JWT로 /state", 403, await status("GET", f"/sessions/{sid}/state", token=token_b)),
        ("동의 전 /state", 401, await status("GET", f"/sessions/{fresh.session_id}/state")),
        ("만료 JWT로 /state", 401, await status("GET", f"/sessions/{sid}/state", token=expired)),
    ]
    bare = api.internal.build_request("GET", f"/internal/sessions/{sid}")
    del bare.headers["X-Internal-Token"]
    results.append(
        ("X-Internal-Token 없이 /internal", 401, (await api.internal.send(bare)).status_code)
    )
    results += [
        ("공개 포트에서 /internal", 404, await status("GET", f"/internal/sessions/{sid}")),
        (
            "지원자 문서 doc_id로 내부 docs/send",
            403,
            await status(
                "POST",
                f"/internal/sessions/{sid}/docs/send",
                internal=True,
                json_body={
                    "doc_id": candidate_doc,
                    "content": "e2e",
                    "channel": "team",
                    "run_id": "00000000-0000-4000-8000-000000000e2e",
                    "seq": 10,
                },
            ),
        ),
        (
            "완료 세션 재초대(previous_session_id)",
            422,
            await status(
                "POST",
                f"/admin/positions/{b.position_id}/invites",
                headers={"Authorization": f"Bearer {b.admin.token}"},
                json_body={
                    "alias": "auth-retry",
                    "email": "e2e@example.com",
                    "previous_session_id": b.invite_session_id,
                },
            ),
        ),
    ]
    return [{"name": n, "want": w, "got": g} for n, w, g in results]


async def run(target: Target, out: Path) -> bool:
    api = Api(target, Transcript())
    try:
        results = await checks(api)
    finally:
        await api.aclose()
    path = records.folder(out, "auth")
    lines = ["# 인증 경계(단언 8)", "", "| 경계 | 기대 | 실제 | 결과 |", "|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['want']} | {r['got']} | "
            f"{'통과' if r['want'] == r['got'] else '실패'} |"
        )
    (path / "auth.md").write_text("\n".join(lines) + "\n", "utf-8")
    return all(r["want"] == r["got"] for r in results)
