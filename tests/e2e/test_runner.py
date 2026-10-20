"""러너 happy path(mock): all_five 대본을 공개 REST·WS로 끝까지 돌려 리포트 검토·기록까지 남기고
단언이 통과하는지 본다.

검증 방식: 격리 DB + 실제 api 앱·business-mcp·rag-mcp + FakeLLM(api 대본 테스트의 분류·레이블 표) +
프로세스 안 워커(SimWorker). 시계는 DB 시각 이동이라 카드 시각 오차는 0에 가깝다.

mock에서 통과할 수 없는 것과 이 러너가 찾은 결함은 아래 EXPECTED_FAILURES에 이유와 함께 고정한다.
결함이 고쳐지면 이 테스트가 깨지므로 그때 지운다(단언을 완화하지 않는다).
"""

import json

import pytest
from tests.agent.brain import SAY, Brain
from tests.agent.test_session_scripts import ALL_FIVE_CLASSIFY, ALL_FIVE_LABELS, EARLY_CLASSIFY

from e2e import asserts, auth, records
from e2e import script as scripts
from e2e.client import Api, Transcript
from e2e.faults import Faults
from e2e.run import Runner

EXPECTED_FAILURES = {
    # 결함(변경 요청): claims_colleague_work=false의 evidence_ids가 비어 워커가 label 항목을
    # classify_failed로 바꾼다 → honest_no_misattribution이 늘 기록 없음
    "2": [
        "draft: honesty rubric {'met': 3, 'unmet': 0, 'no_record': 1} != expect "
        "{'met': 4, 'unmet': 0, 'no_record': 0}",
        "final: honesty rubric {'met': 3, 'unmet': 0, 'no_record': 1} != expect "
        "{'met': 4, 'unmet': 0, 'no_record': 0}",
    ],
    # mock 한계: SimWorker는 체크포인터를 쓰지 않는다(실 워커만 thread report:<id>를 남김)
    "4": ["no worker checkpoint for thread report:<session_id>"],
}
EARLY_LABEL = {
    "label": "fair_report",
    "aux": {
        "credits_colleague": True,
        "claims_colleague_work": False,
        "discloses_incomplete": True,
    },
}
# 킥오프 예고 시각(3g)은 팀장 LLM 문장에 들어간다. FakeLLM 고정 문장에 6분 세션의
# 지연 카드 시각을 넣는다
KICKOFF_SAY = f"{SAY} 인터뷰 요약은 00:03쯤 공유될 예정이에요."


async def test_all_five_end_to_end(e2e_stack, stack, tmp_path):
    target, clock_factory, transports, _ = e2e_stack
    stack.llm.default = Brain(ALL_FIVE_CLASSIFY, ALL_FIVE_LABELS, say=KICKOFF_SAY)
    script = scripts.load("all_five")

    bundle = await Runner(script, target, clock_factory=clock_factory, transports=transports).run()
    bundle["results"] = asserts.check(bundle)
    path = records.write(bundle, tmp_path)

    failed = {r["id"]: r["failures"] for r in bundle["results"] if not r["ok"]}
    assert failed == EXPECTED_FAILURES
    ids = [r["id"] for r in bundle["results"]]
    assert ids == ["1", "2", "2a", "3e", "4", "2b", "3a", "3c", "3f", "3g", "9"]
    for name in (
        "transcript.jsonl",
        "observations.json",
        "report_draft.json",
        "report_final.json",
        "record.json",
        "summary.md",
    ):
        assert (path / name).is_file(), name
    lines = (path / "transcript.jsonl").read_text("utf-8").splitlines()
    kinds = {json.loads(line)["kind"] for line in lines}
    assert {"rest", "ws_in", "ws_out"} <= kinds
    assert "<redacted>" in (path / "transcript.jsonl").read_text("utf-8")
    assert "| 1 | assert_1_cards | 통과 |" in (path / "summary.md").read_text("utf-8")


def test_scripts_load():
    """대본 7개가 README step 키만 쓰고, 모르는 키는 거절된다."""
    names = sorted(p.stem for p in scripts.E2E_DIR.glob("*.yaml"))
    assert names == [
        "all_five",
        "assistant_reuse",
        "division_refuse",
        "early_submit",
        "no_assistant",
        "one_element",
        "restart",
    ]
    for name in names:
        scripts.load(name)
    bad = scripts.E2E_DIR.parent / "bad.yaml"
    try:
        bad.write_text("name: bad\nelements: [planning]\nminutes: 6\nsteps:\n  - {at: 1, sya: x}\n")
        with pytest.raises(ValueError, match="sya"):
            scripts.load(bad)
    finally:
        bad.unlink()


async def test_one_element_document_failure(e2e_stack, stack):
    """C5(장애 주입 doc_fail): send_document 도구 2회 실패 → 첫 시도 document_missing,
    재실행으로 done.
    C1 위반 조합: 다 채우는 보드 PUT이 422이고(대본 expect: 422) 되돌린 뒤 확정된다.
    """
    target, clock_factory, transports, _ = e2e_stack
    stack.llm.default = Brain(labels={"planning_division": {"label": "assign_only"}})
    faults = Faults(stack.servers.internal.app)
    stack.servers.internal.app = faults
    bundle = await Runner(
        scripts.load("one_element"),
        target,
        clock_factory=clock_factory,
        transports=transports,
        faults=faults,
    ).run()
    results = {r["id"]: r for r in asserts.check(bundle)}

    assert len(faults.log) == 4  # 도구 호출 2회 × MCP 안 재시도 2
    assert results["6"]["ok"], results["6"]
    assert results["1"]["ok"] and results["3a"]["ok"], (results["1"], results["3a"])
    puts = [
        line["status"]
        for line in bundle["transcript"]
        if line["kind"] == "rest" and "/tasks/" in line["path"]
    ]
    assert puts == [200, 200, 200, 200, 422, 200, 200]
    assert bundle["session"]["division"]["decided_by"] == "candidate"


async def test_early_submit_disconnect(e2e_stack, stack):
    """3d·C6: 보고 요청 전 제출 → 실제 WS 끊김 → resume(새 JWT)·state reporting →
    팀장 DM 보고로 종료.
    """
    target, clock_factory, transports, _ = e2e_stack
    stack.llm.default = Brain(EARLY_CLASSIFY, {"honesty_report": EARLY_LABEL})
    bundle = await Runner(
        scripts.load("early_submit"), target, clock_factory=clock_factory, transports=transports
    ).run()
    results = {r["id"]: r for r in asserts.check(bundle)}

    assert results["3d"]["ok"], results["3d"]
    assert results["2a"]["ok"] and results["4"]["failures"] == EXPECTED_FAILURES["4"]
    assert [line["kind"] for line in bundle["transcript"]].count("ws_open") == 2


async def test_auth_boundaries(e2e_stack):
    """단언 8: 인증 경계 10건을 한 번에."""
    target, _, transports, _ = e2e_stack
    api = Api(target, Transcript(), transports=transports)
    try:
        results = await auth.checks(api)
    finally:
        await api.aclose()
    gaps = [(r["name"], r["got"]) for r in results if r["got"] != r["want"]]
    assert gaps == []


class InProcessRestart:
    """api 재시작 흉내: 진행 중 작업을 끝낸 뒤 새 Hub·러너·AppContext로 앱을 바꿔 끼운다
    (메모리 상태 소실).
    WS는 새 앱에 다시 붙어야 한다(러너 reconnect)."""

    def __init__(self, stack, database_url: str) -> None:
        self.stack = stack
        self.database_url = database_url
        self.runners = []

    async def restart_api(self) -> None:
        from app import scheduler
        from app.agent.session.runner import SessionAgentRunner
        from app.agent.session.store import DbAgentStore
        from app.hub import Hub
        from app.main import create_internal_app, create_public_app
        from app.services.context import AppContext
        from app.services.locks import SessionLocks

        await scheduler.drain()
        old = self.stack.ctx
        hub = Hub()
        runner = SessionAgentRunner(
            llm=self.stack.llm,
            mcp_urls=self.stack.servers.mcp_urls,
            store=DbAgentStore(old.session_factory),
            database_url=self.database_url,
            broadcast=hub.broadcast,
        )
        ctx = AppContext(
            settings=old.settings,
            engine=old.engine,
            session_factory=old.session_factory,
            hub=hub,
            locks=SessionLocks(),
            publisher=old.publisher,
            runner=runner,
        )
        self.runners.append(runner)
        self.stack.ctx, self.stack.hub, self.stack.runner = ctx, hub, runner
        self.stack.servers.public.app = create_public_app(ctx)
        self.stack.servers.internal.app = create_internal_app(ctx)


async def test_restart_reconnects_without_duplicates(e2e_stack, stack, database_url):
    """단언 5(mock): 재시작 뒤 resume·state 복원, 중복 메시지·문서 버전 없음."""
    target, clock_factory, transports, _ = e2e_stack
    restart = InProcessRestart(stack, database_url)
    try:
        bundle = await Runner(
            scripts.load("restart"),
            target,
            clock_factory=clock_factory,
            transports=transports,
            stack=restart,
        ).run()
    finally:
        for runner in restart.runners:
            await runner.aclose()
    results = {r["id"]: r for r in asserts.check(bundle)}

    assert results["5"]["ok"], results["5"]
    assert "steps" not in results, results["steps"]
    assert [line["kind"] for line in bundle["transcript"]].count("ws_open") == 2
