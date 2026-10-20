"""시드: 관리자 가입(이미 있으면 로그인) → 채용 건 생성 → rag-mcp 재색인.

httpx만 쓰는 독립 스크립트다. api(8000)와 rag-mcp(9102)가 떠 있어야 한다.
    make seed
    uv run --project services/api python scripts/seed.py --elements planning,collaboration
"""

import argparse
import json
import sys

import httpx

ALL_ELEMENTS = "responsibility,planning,adaptability,collaboration,honesty"
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def admin_token(client: httpx.Client, email: str, password: str, company: str) -> str:
    response = client.post(
        "/admin/auth/signup", json={"email": email, "password": password, "company_name": company}
    )
    if response.status_code == 409:  # 이미 가입됨
        response = client.post("/admin/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    return response.json()["token"]


def create_position(client: httpx.Client, token: str, name: str, elements: list[str]) -> dict:
    response = client.post(
        "/admin/positions",
        json={"name": name, "elements": elements},
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    return response.json()


def _rpc_result(response: httpx.Response) -> dict:
    """Streamable HTTP 응답(JSON 또는 SSE의 data: 줄)에서 마지막 JSON-RPC result를 꺼낸다."""
    response.raise_for_status()
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        data = [line[5:] for line in response.text.splitlines() if line.startswith("data:")]
        payload = json.loads(data[-1])
    else:
        payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload["result"]


def call_mcp_tool(url: str, tool: str, arguments: dict) -> dict:
    with httpx.Client(timeout=300) as client:
        init = client.post(
            url,
            headers=MCP_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "dayzero-seed", "version": "0.1"},
                },
            },
        )
        _rpc_result(init)
        headers = dict(MCP_HEADERS)
        if session := init.headers.get("mcp-session-id"):
            headers["mcp-session-id"] = session
        client.post(
            url, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        result = _rpc_result(
            client.post(
                url,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": arguments},
                },
            )
        )
    if result.get("isError"):
        raise RuntimeError(result)
    payload = result.get("structuredContent")
    if payload is None:  # 구조화 출력이 없으면 첫 텍스트 블록의 JSON
        text = next((c["text"] for c in result.get("content", []) if c.get("type") == "text"), "{}")
        payload = json.loads(text)
    # 도구 공통 응답 {ok, data | error}. 업무 오류(ok=false)도 실패로 본다.
    if payload.get("ok") is False:
        raise RuntimeError(payload.get("error"))
    return payload.get("data", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--rag", default="http://localhost:9102/mcp")
    parser.add_argument("--email", default="admin@loop.example")
    parser.add_argument("--password", default="dayzero-seed")
    parser.add_argument("--company", default="데모 회사")
    parser.add_argument("--position", default="프로덕트 기획자")
    parser.add_argument("--elements", default=ALL_ELEMENTS)
    parser.add_argument("--skip-reindex", action="store_true")
    args = parser.parse_args()

    with httpx.Client(base_url=args.api, timeout=30) as client:
        token = admin_token(client, args.email, args.password, args.company)
        position = create_position(client, token, args.position, args.elements.split(","))
    print(f"position {position['id']} catalog_version={position['catalog_version']}")

    if not args.skip_reindex:
        indexed = call_mcp_tool(args.rag, "reindex_documents", {})
        print(f"reindex {indexed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
