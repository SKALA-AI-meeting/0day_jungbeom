"""e2e 세션 조립: 관리자 토큰 → 채용 건(요소 선택) → 초대 → 내부 test/sessions → 초대 토큰 출력.

    python scripts/make_session.py --minutes 6 \
        --elements responsibility,planning,adaptability,collaboration,honesty

test/sessions는 admin_email로 관리자 회사의 채용 건에 만든다(api-fix 병합 뒤 동작. 그 전 api는
이 필드를 무시하고 고정 테스트 회사에 만든다). 초대(120분 채용 건)는 인증 경계 단언
(타 기업·재초대)에 쓰는 관리자 쪽 자원이다. 토큰 값은 출력 대상(초대 토큰)만 찍고
내부 토큰은 출력하지 않는다.
러너(tests/e2e/run.py)가 같은 함수를 쓴다.
"""

import argparse
import asyncio
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "e2e-password-1234"


def env() -> dict[str, str]:
    """infra/.env.local → infra/.env 순(먼저 것이 이김), 환경변수가 가장 우선."""
    values: dict[str, str] = {}
    for name in (".env", ".env.local"):
        path = REPO_ROOT / "infra" / name
        if path.is_file():
            values.update({k: v for k, v in dotenv_values(path).items() if v is not None})
    values.update(os.environ)
    return values


@dataclass
class Admin:
    email: str
    token: str


@dataclass
class Made:
    admin: Admin
    position_id: str
    invite_session_id: str
    invite_link_token: str  # 관리자 초대(채용 건 position_id)의 링크 토큰
    session_id: str
    invite_token: str


async def signup(public: httpx.AsyncClient, company: str) -> Admin:
    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
    r = await public.post(
        "/admin/auth/signup",
        json={"email": email, "password": PASSWORD, "company_name": company},
    )
    r.raise_for_status()
    return Admin(email, r.json()["token"])


async def make(
    public: httpx.AsyncClient,
    internal: httpx.AsyncClient,
    elements: list[str],
    minutes: int,
    *,
    admin: Admin | None = None,
    alias: str = "e2e",
) -> Made:
    admin = admin or await signup(public, "e2e 회사")
    auth = {"Authorization": f"Bearer {admin.token}"}
    r = await public.post(
        "/admin/positions", json={"name": "e2e", "elements": elements}, headers=auth
    )
    r.raise_for_status()
    position_id = r.json()["id"]
    r = await public.post(
        f"/admin/positions/{position_id}/invites",
        json={"alias": alias, "email": "e2e@example.com"},
        headers=auth,
    )
    r.raise_for_status()
    invite_session_id = r.json()["session_id"]
    invite_link_token = r.json()["invite_url"].rstrip("/").rsplit("/", 1)[-1]
    r = await internal.post(
        "/internal/test/sessions",
        json={
            "elements": elements,
            "session_minutes": minutes,
            "alias": alias,
            "admin_email": admin.email,
        },
    )
    r.raise_for_status()
    body = r.json()
    return Made(
        admin, position_id, invite_session_id, invite_link_token, body["session_id"], body["token"]
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--elements", required=True, help="쉼표 구분 요소 id")
    parser.add_argument("--minutes", type=int, default=6)
    args = parser.parse_args()
    values = env()
    public_url = values.get("E2E_PUBLIC_URL", "http://localhost:8000")
    internal_url = values.get("E2E_INTERNAL_URL", "http://localhost:8001")
    headers = {"X-Internal-Token": values.get("INTERNAL_TOKEN", "")}
    async with (
        httpx.AsyncClient(base_url=public_url, timeout=30) as public,
        httpx.AsyncClient(base_url=internal_url, timeout=30, headers=headers) as internal,
    ):
        made = await make(public, internal, args.elements.split(","), args.minutes)
    print(f"session_id={made.session_id}")
    print(f"invite_token={made.invite_token}")
    print(f"admin_email={made.admin.email}")


if __name__ == "__main__":
    asyncio.run(main())
