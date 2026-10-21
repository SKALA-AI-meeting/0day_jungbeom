"""LLM access layer. `OpenAILLM` for real runs, `MockLLM` (MOCK_LLM=1 or no key) for tests/demo.

Three roles, all given the same transcript but different jobs:
  - director : decides who replies to the candidate (1-2 personas)
  - persona  : writes one persona's chat line (never evaluates the candidate)
  - observer : silently extracts behaviour evidence for C01/C02/C03/C05
"""
import os
import re
from typing import Literal

from pydantic import BaseModel, Field

from .scenarios import COMPANY, COMPETENCIES, MILESTONES

LABEL = {m["key"]: m["label"] for m in MILESTONES}
COMP_LINES = "\n".join(f"- {c['id']} {c['name']}: {c['desc']}" for c in COMPETENCIES)


# ---------- structured outputs ----------
class PlanItem(BaseModel):
    persona: Literal["lead", "peer"]
    intent: str = Field(description="이 발화자가 이번 턴에 하려는 일 (예: 질문으로 되묻기, 반대 의견 보태기)")


class TurnPlan(BaseModel):
    speakers: list[PlanItem] = Field(description="발화 순서대로 1~2명")


class ObsItem(BaseModel):
    competency: Literal["C01", "C02", "C03", "C05"]
    behavior: str = Field(description="지원자가 한 행동을 중립적으로 한 문장으로 서술")
    quote: str = Field(description="근거가 되는 지원자 발화의 원문 일부(그대로 복사)")
    signal: Literal["positive", "neutral", "risk"] = Field(
        description="positive=역량을 보여주는 행동, risk=확인이 필요한 행동, neutral=관찰만. 판정이나 점수가 아님"
    )


class ObsList(BaseModel):
    items: list[ObsItem]


class SummaryOut(BaseModel):
    C01: str
    C02: str
    C03: str
    C05: str


def fmt_transcript(messages: list[dict], names: dict[str, str], limit: int = 40) -> str:
    """Context component: recent messages verbatim within the token budget, older ones folded into a digest."""
    from .harness import context

    return context.transcript(messages[-limit:] if limit else messages, names)


def persona_mode(scn: dict, pid: str) -> str:
    cond = scn.get("condition") or {}
    return cond.get(pid) or ("collaborating" if pid == "lead" else "compromising")


def company_of(scn: dict) -> str:
    return scn.get("company_name") or "루프랩"


def persona_system(scn: dict, pid: str) -> str:
    """Persona card (prompts/persona.md): identity + scenario stance + conflict mode + universal guardrails."""
    from .harness import instructions
    from .personas import IDENTITY, SPEECH, mode_block

    p = scn["personas"][pid]
    other = scn["personas"]["peer" if pid == "lead" else "lead"]
    return instructions.render(
        "persona", name=p["name"], role=p["role"], identity=IDENTITY[pid], company=scn.get("company") or COMPANY,
        background=scn["background"], character=p["character"], stance=p["stance"], mode_block=mode_block(persona_mode(scn, pid)),
        speech=SPEECH, other_name=other["name"], other_given=other["name"][1:], other_role=other["role"], other_stance=other["stance"],
    )


# Small models keep closing with service-desk filler despite the prompt; drop such trailing sentences.
_OFFER = re.compile(r"언제든|필요하(시|신)?면|필요(한|하신)\s?\S{0,6}\s?(부분|사항|점)|도움이\s?필요|도와\s?드릴\s?수|추가(로|적인)\s?(지원|도움)")
_ASK = re.compile(r"(말씀|이야기|알려|연락|요청)\s?(해|하여)?\s?주(세요|십시오|시면)|말씀해\s?주세요|편하게\s?말씀")
_SENT = re.compile(r"[^.!?。]+[.!?。]?")


def strip_boilerplate(text: str) -> str:
    sents = [x.strip() for x in _SENT.findall(text) if x.strip()]
    while len(sents) > 1 and _OFFER.search(sents[-1]) and _ASK.search(sents[-1]):
        sents.pop()
    return " ".join(sents) if sents else text


RAG_TOOL = {
    "type": "function",
    "function": {
        "name": "search_company_docs",
        "description": "회사 문서(회사 소개, 운영 정책·규정, 지표 현황, 회의록)에서 질문과 가까운 조항을 찾는다. 규정·절차·수치를 말하기 전에 쓴다.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "찾을 내용 한 가지"}}, "required": ["query"]},
    },
}


class BaseLLM:
    async def plan(self, scn, milestone: str, messages, names, user_text: str) -> TurnPlan: ...
    async def speak(self, scn, pid: str, messages, names, directive: str, meta: dict | None = None) -> dict: ...
    async def observe(self, scn, milestone: str, messages, names, user_text: str) -> list[ObsItem]: ...
    async def summarize(self, scn, observations: list[dict], notes: str) -> SummaryOut: ...
    async def review_account(self, account: dict): ...


def clean_line(text: str) -> str:
    return strip_boilerplate(re.sub(r"^\[[^\]]+\]\s*", "", (text or "").strip()).strip('"“”'))


class OpenAILLM(BaseLLM):
    """Model calls go through the harness: Instructions (prompts/*.md), Recovery (retry + fallback),
    Observability (span per call with tokens), Agent Loop (model-call cap), Tools (RAG via rag-mcp)."""

    def __init__(self) -> None:
        from langchain_openai import ChatOpenAI

        self._mk = lambda model, temp: ChatOpenAI(model=model, temperature=temp, timeout=45, max_retries=0, stream_usage=True)

    async def _llm(self, name: str, model: str, fn):
        from .harness import runtime

        ctx = runtime.current()
        if ctx is None:
            res, _ = await fn()
            return res
        ctx.model_calls += 1
        ctx.limits.check_model_call(ctx.model_calls)
        async with ctx.tracer.span("llm", name, model=model) as span:
            res, usage = await fn()
            if usage:
                span["tokens_in"], span["tokens_out"] = usage.get("input_tokens"), usage.get("output_tokens")
            return res

    def _cfg(self, name: str) -> dict:
        from .harness import runtime

        ctx = runtime.current()
        return ctx.tracer.run_config(name) if ctx else {}

    async def _structured(self, name: str, schema, messages):
        from .harness.recovery import with_recovery

        async def make(model):
            async def fn():
                out = await self._mk(model, 0.1).with_structured_output(schema, include_raw=True).ainvoke(messages, config=self._cfg(name))
                if out.get("parsed") is None:
                    raise ValueError(f"structured output parse failed: {out.get('parsing_error')}")
                return out["parsed"], getattr(out.get("raw"), "usage_metadata", None)

            return await self._llm(name, model, fn)

        return await with_recovery(make)

    async def plan(self, scn, milestone, messages, names, user_text):
        from .harness import instructions

        sys = instructions.render(
            "director", lead_name=scn["personas"]["lead"]["name"], peer_name=scn["personas"]["peer"]["name"], milestone=LABEL[milestone],
            lead_stance=scn["personas"]["lead"]["stance"], peer_stance=scn["personas"]["peer"]["stance"],
            lead_mode=persona_mode(scn, "lead"), peer_mode=persona_mode(scn, "peer"),
        )
        human = instructions.render("director_input", transcript=fmt_transcript(messages, names), user_text=user_text)
        return await self._structured("director", TurnPlan, [("system", sys), ("human", human)])

    async def _stream(self, name, msgs, bind_tools: bool, pid: str, meta: dict | None):
        from .harness import runtime
        from .harness.recovery import with_recovery

        async def make(model):
            async def fn():
                m = self._mk(model, 0.8)
                if bind_tools:
                    m = m.bind_tools([RAG_TOOL])
                if meta:
                    await runtime.emit("TOKEN", {**meta, "speaker": pid, "reset": True, "delta": ""})
                full = None
                async for chunk in m.astream(msgs, config=self._cfg(name)):
                    full = chunk if full is None else full + chunk
                    if chunk.content and meta:
                        await runtime.emit("TOKEN", {**meta, "speaker": pid, "delta": chunk.content})
                return full, getattr(full, "usage_metadata", None)

            return await self._llm(name, model, fn)

        return await with_recovery(make)

    async def speak(self, scn, pid, messages, names, directive, meta=None):
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        from .harness import guardrails, instructions, runtime, tools

        msgs = [SystemMessage(persona_system(scn, pid)),
                HumanMessage(instructions.render("persona_turn", transcript=fmt_transcript(messages, names), directive=directive))]
        sources: list[dict] = []
        use_rag = tools.enabled("rag") and os.getenv("RAG_DISABLED") != "1"
        text = ""
        for step in range(2):  # at most one tool round, then the answer
            resp = await self._stream(f"persona.{pid}", msgs, use_rag and step == 0, pid, meta)
            calls = getattr(resp, "tool_calls", None) or []
            if calls and step == 0:
                msgs.append(resp)
                for tc in calls[:2]:
                    query = (tc.get("args") or {}).get("query", "")
                    out, data = await tools.call_for_model("rag", "search_docs", {"query": query, "company": company_of(scn), "k": 3})
                    for hit in (data or {}).get("results", []) if isinstance(data, dict) else []:
                        src = {"doc": hit.get("doc"), "section": hit.get("section")}
                        if src not in sources:
                            sources.append(src)
                    msgs.append(ToolMessage(content=out, tool_call_id=tc["id"]))
                continue
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            break
        text = clean_line(text)
        if guardrails.violates_output_policy(text):  # output guard: one non-streamed rewrite
            ctx = runtime.current()
            if ctx:
                ctx.tracer.note("output_guard")
            msgs.append(HumanMessage("방금 대사에 평가·점수·시뮬레이션 관련 표현이 있었다. 그런 표현 없이 같은 뜻으로 다시 써라. 대사만 출력:"))
            resp = await self._stream(f"persona.{pid}.rewrite", msgs, False, pid, meta)
            text = clean_line(resp.content if isinstance(resp.content, str) else str(resp.content))
        return {"text": text, "sources": sources}

    async def observe(self, scn, milestone, messages, names, user_text):
        from .harness import instructions

        sys = instructions.render("observer", competencies=COMP_LINES, milestone=LABEL[milestone], look_for=scn["beats"][milestone]["look_for"])
        human = instructions.render("observer_input", transcript=fmt_transcript(messages[:-1], names, 12), user_text=user_text)
        out = await self._structured("observer", ObsList, [("system", sys), ("human", human)])
        return out.items

    async def summarize(self, scn, observations, notes):
        from .harness import instructions

        rows = "\n".join(f"- {o['competency']} ({LABEL[o['milestone']]}, {o['signal']}) {o['behavior']} / \"{o['quote']}\"" for o in observations)
        sys = instructions.render("summarize", competencies=COMP_LINES)
        human = instructions.render("summarize_input", rows=rows or "(없음)", notes=notes or "(없음)")
        return await self._structured("summarize", SummaryOut, [("system", sys), ("human", human)])


    async def review_account(self, account):
        from .account_review import Plausibility
        from .harness import instructions

        sys = instructions.render("account_review")
        human = instructions.render("account_review_input", nickname=account.get("nickname"), email=account.get("email"),
                                    desired_job=account.get("desired_job"), industry=account.get("industry") or "(없음)",
                                    experience_years=account.get("experience_years"), bio=account.get("bio") or "(없음)")
        return await self._structured("account_review", Plausibility, [("system", sys), ("human", human)])


class MockLLM(BaseLLM):
    """Deterministic stand-in; keeps the graph, SSE and UI testable offline."""

    async def plan(self, scn, milestone, messages, names, user_text):
        speakers = []
        for pid in ("lead", "peer"):
            if scn["personas"][pid]["name"] in user_text:
                speakers.append(pid)
        beat_pid = scn["beats"][milestone]["speaker"]
        first = speakers[0] if speakers else ("peer" if beat_pid == "lead" else "lead")
        second = "lead" if first == "peer" else "peer"
        items = [PlanItem(persona=first, intent="지원자 발화에 답한다")]
        if len(user_text) > 25:
            items.append(PlanItem(persona=second, intent="자기 입장에서 의견을 보탠다"))
        return TurnPlan(speakers=items)

    LINES = {
        "competing": ["그건 아니라고 봐요. 제 안대로 가야 일정이 지켜집니다.", "근거가 더 있으면 몰라도, 지금으로선 동의하기 어렵네요."],
        "collaborating": ["제 입장은 그대로지만, 걱정하시는 지점이 정확히 뭔지 여쭤봐도 될까요?", "두 안을 같이 살릴 방법이 있을지 한번 같이 보죠."],
        "compromising": ["시간이 없으니 반씩 양보하는 걸로 정리하면 어떨까요?", "이번엔 이렇게 하고, 다음엔 다른 쪽으로 가죠."],
        "avoiding": ["음, 그건 상황 봐서 다시 얘기해요.", "글쎄요, 저는 잘 모르겠어요."],
        "accommodating": ["네, 그렇게 하시죠. 저는 맞출게요.", "좋아요, 말씀하신 대로 할게요."],
    }

    async def speak(self, scn, pid, messages, names, directive, meta=None):
        from .harness import runtime, tools

        if "BEAT:" in directive:
            text = directive.split("BEAT:", 1)[1].strip()
        else:
            pool = self.LINES[persona_mode(scn, pid)]
            text = pool[len(messages) % len(pool)]
        sources = []
        if "BEAT:" in directive and tools.enabled("rag") and os.getenv("RAG_DISABLED") != "1":
            _, data = await tools.call_for_model("rag", "search_docs", {"query": text[:60], "company": company_of(scn), "k": 1})
            sources = [{"doc": h.get("doc"), "section": h.get("section")} for h in (data or {}).get("results", [])] if isinstance(data, dict) else []
        if meta:
            await runtime.emit("TOKEN", {**meta, "speaker": pid, "reset": True, "delta": text})
        return {"text": text, "sources": sources}

    async def observe(self, scn, milestone, messages, names, user_text):
        first = re.split(r"(?<=[.?!。])\s+", user_text.strip())[0][:120]
        rules = [
            ("C01", r"\?|어떻게|무엇|언제|확인", "상황이나 요구를 질문해 확인함"),
            ("C02", r"제안|대신|나눠|어때|도와|같이", "역할·의견 차이를 조율하려는 제안을 함"),
            ("C03", r"공유|알려|일정|까지|오늘|내일|마감", "진행·일정 사항을 공유함"),
            ("C05", r"수정|반영|바꾸|변경|알겠|받아", "변경 조건을 받아들이고 계획을 수정하려 함"),
        ]
        out = []
        for cid, pat, beh in rules:
            if re.search(pat, user_text):
                out.append(ObsItem(competency=cid, behavior=beh, quote=first, signal="neutral"))
        return out[:3]

    async def review_account(self, account):
        from .account_review import Plausibility

        return Plausibility(overall="clean", concerns=[])  # rules alone decide in offline tests

    async def summarize(self, scn, observations, notes):
        def line(cid):
            n = sum(1 for o in observations if o["competency"] == cid)
            return f"관찰 {n}건이 기록됨 (mock 요약)" if n else "해당 상황에서 관련 행동이 기록되지 않음"

        return SummaryOut(C01=line("C01"), C02=line("C02"), C03=line("C03"), C05=line("C05"))


def get_llm() -> BaseLLM:
    if os.getenv("MOCK_LLM") == "1" or not os.getenv("OPENAI_API_KEY"):
        return MockLLM()
    return OpenAILLM()
