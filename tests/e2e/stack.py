"""러너가 앱 프로세스를 직접 띄우는 실 스택(--manage-stack)과 장애 주입 6종(단언 6).

인프라(postgres·rabbitmq·rag-mcp)는 `make infra-up`으로 떠 있어야 한다. 러너는 이 worktree의
api·business-mcp·report-worker를 하위 프로세스로 띄우고, business-mcp·worker의 API_INTERNAL_URL을
러너 안 장애 주입 프록시(faults.Faults + Forward)로 돌린다. 끝나면 모든 앱 프로세스를 종료한다.
web은 러너가 쓰지 않으므로 띄우지 않는다.

장애 주입 방식(이 트랙이 정함):
| 이름 | 방식 |
|---|---|
| fired_kill | planning_checkin이 fired가 되는 즉시 api SIGKILL → 재기동 |
| tool_kill | 그 카드의 첫 post_message가 2xx로 지나간 직후 api SIGKILL → 재기동 |
| doc_fail | one_element 대본의 inject(send_document 2회 503) = C5 |
| publish_down | reporting 중 rabbitmq 정지 → completed 뒤 재기동(스케줄러 재탐색 재발행) |
| final_ack_kill | 워커의 report/final이 2xx로 지나간 직후 워커 SIGKILL → 재기동(재전달 멱등) |
| report_3fail | 워커의 report/draft를 3회 503 → failed(report) → regenerate → report_ready |
"""

import asyncio
import contextlib
import os
import signal
import socket
import subprocess
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from e2e import asserts, records
from e2e import script as scripts
from e2e.client import Target
from e2e.faults import Faults, Forward
from scripts import make_session

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = [
    "docker",
    "compose",
    "-f",
    "infra/docker-compose.yml",
    "-f",
    "infra/docker-compose.dev.yml",
    "--env-file",
    "infra/.env",
]
STARTUP_SECONDS = 120
FAULTS = ("fired_kill", "tool_kill", "doc_fail", "publish_down", "final_ack_kill", "report_3fail")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LocalStack:
    def __init__(self, log_dir: Path) -> None:
        self.env = make_session.env()
        self.log_dir = log_dir
        self.internal_url = "http://127.0.0.1:8001"
        self.mcp_faults = Faults(Forward(self.internal_url))
        self.worker_faults = Faults(Forward(self.internal_url))
        self.procs: dict[str, subprocess.Popen] = {}
        self.servers: list[uvicorn.Server] = []
        self.tasks: list[asyncio.Task] = []

    @property
    def target(self) -> Target:
        return Target(
            public_url="http://127.0.0.1:8000",
            internal_url=self.internal_url,
            internal_token=self.env.get("INTERNAL_TOKEN", ""),
            database_url=self.env.get("E2E_DATABASE_URL") or self.env.get("DATABASE_URL"),
        )

    async def _proxy(self, app: Faults) -> str:
        port = free_port()
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.servers.append(server)
        self.tasks.append(asyncio.create_task(server.serve()))
        return f"http://127.0.0.1:{port}"

    def _spawn(self, name: str, folder: str, module: str, extra: dict[str, str]) -> None:
        env = {
            **os.environ,
            "AGENT_RUNNER": "session",
            "ASSISTANT_RUNNER": "graph",
            "ENABLE_TEST_API": "1",
            **extra,
        }
        if self.env.get("E2E_DATABASE_URL"):
            env["DATABASE_URL"] = self.env["E2E_DATABASE_URL"]
        env.pop("VIRTUAL_ENV", None)
        log = (self.log_dir / f"{name}.log").open("a")
        self.procs[name] = subprocess.Popen(
            ["uv", "run", "--quiet", "python", "-m", module],
            cwd=REPO_ROOT / "services" / folder,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    async def _wait(self, url: str) -> None:
        async with httpx.AsyncClient() as client:
            for _ in range(STARTUP_SECONDS * 4):
                with contextlib.suppress(httpx.TransportError):
                    if (await client.get(url)).status_code == 200:
                        return
                await asyncio.sleep(0.25)
        raise TimeoutError(url)

    async def start(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.mcp_url = await self._proxy(self.mcp_faults)
        self.worker_url = await self._proxy(self.worker_faults)
        await self.start_api()
        self._spawn(
            "business-mcp", "business-mcp", "business_mcp", {"API_INTERNAL_URL": self.mcp_url}
        )
        await self._wait("http://127.0.0.1:9101/health")
        await self.start_worker()

    async def start_api(self) -> None:
        self._spawn("api", "api", "app.run", {})
        await self._wait("http://127.0.0.1:8000/health")

    async def start_worker(self) -> None:
        self._spawn(
            "worker", "report-worker", "report_worker", {"API_INTERNAL_URL": self.worker_url}
        )

    def _signal(self, name: str, sig: int) -> None:
        proc = self.procs.pop(name, None)
        if proc and proc.poll() is None:
            proc.send_signal(sig)
            proc.wait(timeout=30)

    async def kill_api(self) -> None:
        self._signal("api", signal.SIGKILL)

    async def restart_api(self) -> None:
        self._signal("api", signal.SIGTERM)
        await self.start_api()

    async def kill_worker(self) -> None:
        self._signal("worker", signal.SIGKILL)

    def rabbit(self, action: str) -> None:
        subprocess.run(
            [*COMPOSE, action, "rabbitmq"], cwd=REPO_ROOT, check=True, capture_output=True
        )

    async def stop(self) -> None:
        for name in list(self.procs):
            self._signal(name, signal.SIGTERM)
        for server in self.servers:
            server.should_exit = True
        await asyncio.gather(*self.tasks, return_exceptions=True)


async def run_managed(name: str, out: Path) -> bool:
    from e2e.run import Runner

    stack = LocalStack(records.folder(out, f"stack-{name}"))
    await stack.start()
    try:
        script = scripts.load(name)
        bundle = await Runner(script, stack.target, stack=stack, faults=stack.mcp_faults).run()
    finally:
        await stack.stop()
    bundle["results"] = asserts.check(bundle)
    records.write(bundle, out)
    return asserts.passed(bundle["results"])


async def _fault(name: str, stack: LocalStack) -> dict[str, Any]:
    """장애 하나를 one_element 세션에 걸고 bundle을 돌려준다(b["fault"]에 관찰값)."""
    from e2e.run import Runner

    runner = Runner(scripts.load("one_element"), stack.target, stack=stack, faults=stack.mcp_faults)
    seen: dict[str, Any] = {"name": name}
    background: list[asyncio.Task] = []

    async def revive() -> None:
        await stack.start_api()
        await runner.reconnect()

    if name == "fired_kill":

        async def watch() -> None:
            while True:
                await asyncio.sleep(0.2)
                with contextlib.suppress(Exception):
                    await runner.refresh_events()
                    event = runner.events["planning_checkin"]
                    if event["status"] == "fired":
                        seen["run_id"] = event.get("run_id")
                        await stack.kill_api()
                        await revive()
                        return

        background.append(asyncio.create_task(watch()))
    elif name == "tool_kill":

        async def killed(body: dict[str, Any]) -> None:
            seen["run_id"] = body.get("run_id")
            await stack.kill_api()
            background.append(asyncio.create_task(revive()))

        def checkin(body: dict[str, Any]) -> bool:
            return body.get("event_id") == runner.events.get("planning_checkin", {}).get("id")

        stack.mcp_faults.after("post_message", killed, checkin)
    elif name == "publish_down":
        runner.report_wait_seconds = 300

        async def watch() -> None:
            while (await runner.refresh_events())["status"] in ("invited", "in_progress"):
                await asyncio.sleep(0.5)
            stack.rabbit("stop")
            while (await runner.refresh_events())["status"] == "reporting":
                await asyncio.sleep(0.5)
            rows = await runner.sql(
                "SELECT report_enqueued_at FROM sessions WHERE id = :s", s=runner.sid
            )
            seen["enqueued_null"] = bool(rows) and rows[0]["report_enqueued_at"] is None
            stack.rabbit("start")

        background.append(asyncio.create_task(watch()))
    elif name == "final_ack_kill":

        async def killed(body: dict[str, Any]) -> None:
            seen["killed"] = True
            await stack.kill_worker()
            await stack.start_worker()

        stack.worker_faults.after("report_final", killed)
    elif name == "report_3fail":
        runner.report_wait_seconds = 300
        runner.regenerate_on_failure = True
        stack.worker_faults.fail("report_draft", 3)

    try:
        bundle = await runner.run()
    finally:
        for task in background:
            task.cancel()
        stack.mcp_faults.rules.clear()
        stack.worker_faults.rules.clear()
    bundle["fault"] = {**seen, "regenerated": bundle.get("regenerated")}
    return bundle


async def run_faults(which: str, out: Path) -> bool:
    names = FAULTS if which == "all" else tuple(which.split(","))
    path = records.folder(out, "faults")
    stack = LocalStack(path / "logs")
    await stack.start()
    bundles = []
    try:
        for name in names:
            bundle = await _fault(name, stack)
            bundle["results"] = asserts.check(bundle)
            records.write(bundle, path)
            bundles.append(bundle)
    finally:
        await stack.stop()
    lines = ["# 장애 주입(단언 6)", "", "| 장애 | 단언 6 | 실패 |", "|---|---|---|"]
    for b in bundles:
        six = next(r for r in b["results"] if r["id"] == "6")
        lines.append(
            f"| {b['fault']['name']} | {'통과' if six['ok'] else '실패'} | "
            f"{'<br>'.join(six['failures'])} |"
        )
    (path / "faults.md").write_text("\n".join(lines) + "\n", "utf-8")
    return all(next(r for r in b["results"] if r["id"] == "6")["ok"] for b in bundles)
