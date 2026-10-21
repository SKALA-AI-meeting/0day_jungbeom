"""장애 주입(단언 10)과 그 단언.

- 프록시: 워커 → api 내부 앱(8001) 사이에 끼우는 ASGI 앱. 규칙에 걸린 요청은 503으로 돌려주고,
  지나간 요청은 전부 `log`에 남긴다(워커가 어떤 내부 API를 몇 번 불렀는지가 관측값이다).
- 흐름: (a) 큐 DLQ — 리포트 draft 저장이 3번 실패 → failed(report) → regenerate → report_ready,
  (b) LLM timeout — 페르소나 타임아웃은 그 발언만 생략, 평가 타임아웃은 저장 없이 큐 재시도 뒤 성공.
- 스택 쪽 약속(`stack`이 줘야 하는 것): `fail_report_draft(times)`, `set_llm_fault(role, times)`,
  `worker_log() -> list[dict]`, `restart_api()`. 실 스택은 stack.LocalStack, mock은
  fake_stack.FakeStack.
"""

import asyncio
import re
import time
from pathlib import Path
from typing import Any

import httpx

from e2e import asserts, records
from e2e import script as scripts
from e2e.client import Target
from e2e.run import Runner

RULES = {
    "report_draft": ("POST", r"/internal/sessions/[^/]+/report/draft$"),
    "report_final": ("POST", r"/internal/sessions/[^/]+/report/final$"),
    "evaluations": ("POST", r"/internal/sessions/[^/]+/evaluations$"),
}
PERSONA_ATTEMPTS = 3  # 발언 하나가 LLM을 부르는 횟수(최초 + 재시도 2회)


class Proxy:
    """ASGI 포워더. fail(name, times)로 다음 times번의 일치 요청을 503으로 돌려준다."""

    def __init__(self, upstream: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.client = httpx.AsyncClient(base_url=upstream, timeout=60, transport=transport)
        self.rules: list[dict[str, Any]] = []
        self.log: list[dict[str, Any]] = []

    def fail(self, name: str, times: int) -> None:
        method, pattern = RULES[name]
        self.rules.append({"method": method, "pattern": re.compile(pattern), "times": times})

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        method, path = scope["method"], scope["path"]
        rule = next(
            (
                r
                for r in self.rules
                if r["times"] > 0 and r["method"] == method and r["pattern"].search(path)
            ),
            None,
        )
        if rule:
            rule["times"] -= 1
            status, content, headers = (
                503,
                b'{"error":{"code":"injected","message":"injected"}}',
                {},
            )
        else:
            query = scope["query_string"].decode()
            headers_in = {
                k.decode(): v.decode()
                for k, v in scope["headers"]
                if k not in (b"host", b"content-length")
            }
            upstream = await self.client.request(
                method, path + (f"?{query}" if query else ""), content=body, headers=headers_in
            )
            status, content = upstream.status_code, upstream.content
            headers = {"content-type": upstream.headers.get("content-type", "application/json")}
        self.log.append(
            {
                "method": method,
                "path": path,
                "status": status,
                "injected": rule is not None,
                "at": time.time(),
            }
        )
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            }
        )
        await send({"type": "http.response.body", "body": content})


# ---- 단언 10 ----------------------------------------------------------------------------------


def _count(log: list[dict[str, Any]], suffix: str, *, injected: bool | None = None) -> int:
    return sum(
        1
        for e in log
        if e["method"] == "POST"
        and e["path"].endswith(suffix)
        and (injected is None or e["injected"] == injected)
    )


def assert_10a_dlq(b: dict[str, Any]) -> list[str]:
    fault, out = b["fault"], []
    log = fault["log"]
    if _count(log, "/report/draft", injected=True) != 3:
        out.append(
            f"draft 저장 주입 실패가 3회가 아님: {_count(log, '/report/draft', injected=True)}"
        )
    if not b["failed_seen"]:
        out.append("3회 실패 뒤 failed(report)가 보이지 않음")
    if not b["regenerated"] or not b.get("draft"):
        out.append("regenerate 뒤 report_ready에 이르지 못함")
    before, after = b.get("eval_before_regen") or {}, b.get("evaluations") or {}
    if before.get("run_id") != after.get("run_id"):
        out.append("regenerate가 평가를 다시 실행함(run_id 달라짐)")
    if any(d.get("no_record_reason") == "evaluate_failed" for d in after.get("dimensions", [])):
        out.append("평가 실행에 evaluate_failed가 있는데 같은 run_id를 재사용함")
    if _count(log, "/evaluations") != 1:
        out.append(
            f"평가 저장 호출이 1회가 아님(재생성에서 평가 LLM 미호출 위반): "
            f"{_count(log, '/evaluations')}"
        )
    return out


def assert_10b_llm_timeout(b: dict[str, Any]) -> list[str]:
    fault, out = b["fault"], []
    if fault["persona_replies_faulted"] != 0:
        out.append("페르소나 LLM 타임아웃인데 그 발언이 게시됨")
    if fault["persona_replies_after"] < 1:
        out.append("타임아웃 뒤 세션이 계속되지 않음(다음 메시지에 응답 없음)")
    if fault["status_after_persona"] != "in_progress":
        out.append(f"페르소나 타임아웃 뒤 세션 상태 {fault['status_after_persona']}")
    if not b.get("draft"):
        out.append("평가 LLM 타임아웃 뒤 큐 재시도로 리포트가 만들어지지 않음")
    if _count(fault["log"], "/evaluations") != 1:
        out.append(
            f"평가 저장 호출이 1회가 아님(타임아웃 시도에서 저장함): "
            f"{_count(fault['log'], '/evaluations')}"
        )
    return out


# ---- 흐름 -------------------------------------------------------------------------------------


def _runner(script: dict[str, Any], target: Target, stack: Any, **kwargs: Any) -> Runner:
    return Runner(
        script, target, clock="fake", stack=stack, **(getattr(stack, "runner_kwargs", {}) | kwargs)
    )


async def run_dlq(stack: Any, target: Target) -> dict[str, Any]:
    await stack.fail_report_draft(3)
    runner = _runner(
        scripts.load("timeout_all"), target, stack, report_wait=300, regenerate_on_failure=True
    )
    bundle = await runner.run()
    bundle["fault"] = {"name": "dlq", "log": stack.worker_log()}
    bundle["results"] = [*asserts.check(bundle), _result("10a", "큐 DLQ", assert_10a_dlq(bundle))]
    return bundle


async def run_llm_timeout(stack: Any, target: Target) -> dict[str, Any]:
    script = {"name": "fault_llm_timeout", "minutes": 15, "steps": []}
    runner = _runner(script, target, stack, report_wait=300)
    await runner.setup()

    async def persona_replies() -> int:
        await asyncio.sleep(runner.poll * 4)
        return sum(
            1 for f in runner.frames("message.new") if f["payload"]["sender"] in ("p1", "p2", "p3")
        )

    await stack.set_llm_fault("persona", PERSONA_ATTEMPTS)
    before = await persona_replies()
    await runner.say("저는 물로 하고 싶어요.")
    faulted = await persona_replies() - before
    await runner.say("물은 통계 자료가 많아요.")
    after = await persona_replies() - before - faulted
    status = (await runner.internal())["status"]
    await stack.set_llm_fault("evaluator", 1)
    await runner.wait_ended()
    bundle = await runner.finish()
    bundle["fault"] = {
        "name": "llm_timeout",
        "log": stack.worker_log(),
        "persona_replies_faulted": faulted,
        "persona_replies_after": after,
        "status_after_persona": status,
    }
    # 대본 없이 쓴 흐름이라 대본 단언(카드·칸)은 적용하지 않고 공통 단언 중 0·1·2·5만 본다
    bundle["results"] = [
        *(r for r in asserts.check(bundle) if r["id"] in ("0", "2", "5")),
        _result("10b", "LLM timeout", assert_10b_llm_timeout(bundle)),
    ]
    return bundle


def _result(number: str, name: str, failures: list[str]) -> dict[str, Any]:
    return {"id": number, "name": name, "ok": not failures, "failures": failures}


FLOWS = {"dlq": run_dlq, "llm_timeout": run_llm_timeout}


async def run_faults(which: str, out: Path) -> bool:
    from e2e.stack import LocalStack

    names = list(FLOWS) if which == "all" else which.split(",")
    folder = records.folder(out, "faults")
    stack = LocalStack(folder / "logs")
    await stack.start()
    lines = ["# 장애 주입(단언 10)", "", "| 장애 | 결과 | 실패 |", "|---|---|---|"]
    ok = True
    try:
        for name in names:
            stack.reset_faults()
            bundle = await FLOWS[name](stack, stack.target)
            records.write(bundle, folder)
            fail = [r for r in bundle["results"] if not r["ok"]]
            ok &= not fail
            lines.append(
                f"| {name} | {'통과' if not fail else '실패'} | "
                f"{'<br>'.join(f for r in fail for f in r['failures'])} |"
            )
    finally:
        await stack.stop()
    (folder / "faults.md").write_text("\n".join(lines) + "\n", "utf-8")
    return ok
