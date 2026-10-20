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
    lines = [f"[{names.get(m['speaker'], m['speaker'])}] {m['text']}" for m in messages if m["speaker"] != "system"]
    return "\n".join(lines[-limit:]) or "(대화 없음)"


def persona_mode(scn: dict, pid: str) -> str:
    cond = scn.get("condition") or {}
    return cond.get(pid) or ("collaborating" if pid == "lead" else "compromising")


def persona_system(scn: dict, pid: str) -> str:
    """Persona card: identity + scenario stance + conflict mode (personas.py) + universal guardrails."""
    from .personas import IDENTITY, SPEECH, mode_block

    p = scn["personas"][pid]
    oid = "peer" if pid == "lead" else "lead"
    other = scn["personas"][oid]
    return f"""[페르소나 카드]
이름/역할: {p['name']} ({p['role']}) — {IDENTITY[pid]}
회사: {scn.get('company') or COMPANY}
진행 상황: {scn['background']}
배경 성격: {p['character']}
이 상황에서의 입장: {p['stance']}
{mode_block(persona_mode(scn, pid))}
말투: {SPEECH}

[채널]
지원자(같은 팀원), 너, {other['name']}({other['role']}) 3명이 있다. {other['name']}의 입장: {other['stance']}
- 대화 상대는 지원자이며, 필요하면 {other['name']}에게도 '{other['name'][1:]}님'이라고 불러 직접 말한다.
- '입장'은 무엇을 주장하는지, '갈등 대처 유형'은 어떻게 말하는지다. 유형과 상관없이 너의 입장과 반대되는 주장을 먼저 하지 않는다(수용형·회피형이라도 물으면 원래 입장을 말한다).
- 갈등 대처 유형의 행동 규칙을 대화 내내 일관되게 지키되, 규칙에 든 예시 문구를 그대로 쓰지 말고 매번 다른 표현으로 같은 태도를 보인다. 너의 직전 발화와 같은 말로 시작하지 않는다.
- 지원자의 말을 그대로 따라 말하지 않고, '필요하면 말씀해 주세요' 같은 인사말로 끝내지 않는다.
- 아직 안건이 아닌 너의 사정은 먼저 털어놓지 않는다(유형 규칙이 더 엄격하면 그것을 따른다). 직접 물으면 답한다.

[절대 규칙]
- 지원자를 평가하거나 점수·합격·관찰·시뮬레이션·테스트·성향 같은 말을 꺼내지 않는다.
- 새로운 숫자·사실을 지어내지 않는다. 회사/진행 상황에 적힌 것만 근거로 쓴다.
- 이름 머리글([이름])이나 따옴표 없이 대사만 출력한다."""


# Small models keep closing with service-desk filler despite the prompt; drop such trailing sentences.
_OFFER = re.compile(r"언제든|필요하(시|신)?면|필요한\s?\S{0,6}\s?(부분|사항|점)|도움이\s?필요|도와\s?드릴\s?수|추가(로|적인)\s?(지원|도움)")
_ASK = re.compile(r"(말씀|이야기|알려|연락|요청)\s?(해|하여)?\s?주(세요|십시오|시면)|말씀해\s?주세요|편하게\s?말씀")
_SENT = re.compile(r"[^.!?。]+[.!?。]?")


def strip_boilerplate(text: str) -> str:
    sents = [x.strip() for x in _SENT.findall(text) if x.strip()]
    while len(sents) > 1 and _OFFER.search(sents[-1]) and _ASK.search(sents[-1]):
        sents.pop()
    return " ".join(sents) if sents else text


class BaseLLM:
    async def plan(self, scn, milestone: str, messages, names, user_text: str) -> TurnPlan: ...
    async def speak(self, scn, pid: str, messages, names, directive: str) -> str: ...
    async def observe(self, scn, milestone: str, messages, names, user_text: str) -> list[ObsItem]: ...
    async def summarize(self, scn, observations: list[dict], notes: str) -> SummaryOut: ...


class OpenAILLM(BaseLLM):
    def __init__(self) -> None:
        from langchain_openai import ChatOpenAI

        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.chat = ChatOpenAI(model=model, temperature=0.8, timeout=45, max_retries=2)
        self.cold = ChatOpenAI(model=model, temperature=0.1, timeout=45, max_retries=2)

    async def plan(self, scn, milestone, messages, names, user_text):
        sys = f"""너는 3자 대화방(지원자, {scn['personas']['lead']['name']} 팀장, {scn['personas']['peer']['name']} 개발자)의 진행 감독이다.
지금 마일스톤은 '{LABEL[milestone]}' 단계이다. 지원자의 마지막 발화에 누가 어떻게 답할지 정한다.
- 지원자가 특정인을 이름으로 부르면 그 사람이 먼저 답한다.
- 두 사람의 입장이 충돌하는 주제라면 두 번째 발화자가 의견을 보태거나 반박하게 해 지원자가 조율해야 하게 만든다.
- 지원자 발화가 짧거나 단순 확인이면 한 명만 답해도 된다.
- 팀장은 'lead', 개발자/동료는 'peer'이다.
- 두 사람의 입장: lead={scn['personas']['lead']['stance']} / peer={scn['personas']['peer']['stance']}
- 두 사람의 갈등 대처 유형: lead={persona_mode(scn, 'lead')} / peer={persona_mode(scn, 'peer')}. avoiding(회피형)은 직접 불리거나 꼭 필요할 때만 답하고, competing(경쟁형)은 반대 의견이 나오면 끼어든다."""
        out = await self.cold.with_structured_output(TurnPlan).ainvoke(
            [("system", sys), ("human", f"대화:\n{fmt_transcript(messages, names)}\n\n지원자의 마지막 발화: {user_text}")]
        )
        return out

    async def speak(self, scn, pid, messages, names, directive):
        out = await self.chat.ainvoke(
            [("system", persona_system(scn, pid)), ("human", f"지금까지의 대화:\n{fmt_transcript(messages, names)}\n\n이번에 해야 할 일: {directive}\n대사만 출력:")]
        )
        text = out.content if isinstance(out.content, str) else str(out.content)
        return strip_boilerplate(re.sub(r"^\[[^\]]+\]\s*", "", text.strip()).strip('"“”'))

    async def observe(self, scn, milestone, messages, names, user_text):
        look = scn["beats"][milestone]["look_for"]
        sys = f"""너는 대화에 끼지 않는 조용한 관찰자다. 지원자의 '마지막 발화'에서 아래 4개 역량과 관련된 행동만 근거와 함께 추출한다.
{COMP_LINES}
현재 단계: {LABEL[milestone]} / 이 단계에서 특히 볼 것: {look}
규칙:
- 점수나 합격 판단을 하지 않는다. 행동을 중립적으로 서술하고 signal만 붙인다.
- behavior는 역량 정의를 복사하지 말고, 지원자가 이 발화에서 '구체적으로 무엇을 했는지'를 한 문장으로 쓴다. (예: '개발 쪽 지연 여부를 팀장에게 되물어 확인함', '푸시를 다음 배포로 미루는 대안과 문서화 계획을 제시함')
- signal 기준: positive=질문·정리·대안 제시·책임 있는 공유처럼 해당 역량에 도움이 되는 구체적 행동, risk=책임 회피·비난·모호한 약속·상대 의견 무시처럼 사람이 면접에서 확인해 볼 만한 행동, neutral=그 밖의 관찰.
- quote는 지원자 마지막 발화에 실제로 있는 문장을 그대로 복사한다. 없는 말을 만들지 않는다.
- 관련 행동이 없으면 빈 목록을 낸다. 억지로 채우지 않는다. 한 발화당 최대 3개."""
        out = await self.cold.with_structured_output(ObsList).ainvoke(
            [("system", sys), ("human", f"맥락:\n{fmt_transcript(messages[:-1], names, 12)}\n\n지원자 마지막 발화: {user_text}")]
        )
        return out.items

    async def summarize(self, scn, observations, notes):
        rows = "\n".join(f"- {o['competency']} ({LABEL[o['milestone']]}, {o['signal']}) {o['behavior']} / \"{o['quote']}\"" for o in observations)
        sys = f"""아래 관찰 기록을 역량별로 한국어 2문장 이내로 요약한다. 점수·등급·합격 표현을 쓰지 않고, 기록에 없는 내용을 추가하지 않는다.
관찰이 없는 역량은 정확히 '해당 상황에서 관련 행동이 기록되지 않음'이라고만 쓴다.
역량:\n{COMP_LINES}"""
        return await self.cold.with_structured_output(SummaryOut).ainvoke(
            [("system", sys), ("human", f"관찰 기록:\n{rows or '(없음)'}\n\n지원자 노트:\n{notes or '(없음)'}")]
        )


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

    async def speak(self, scn, pid, messages, names, directive):
        if "BEAT:" in directive:
            return directive.split("BEAT:", 1)[1].strip()
        pool = self.LINES[persona_mode(scn, pid)]
        return pool[len(messages) % len(pool)]

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

    async def summarize(self, scn, observations, notes):
        def line(cid):
            n = sum(1 for o in observations if o["competency"] == cid)
            return f"관찰 {n}건이 기록됨 (mock 요약)" if n else "해당 상황에서 관련 행동이 기록되지 않음"

        return SummaryOut(C01=line("C01"), C02=line("C02"), C03=line("C03"), C05=line("C05"))


def get_llm() -> BaseLLM:
    if os.getenv("MOCK_LLM") == "1" or not os.getenv("OPENAI_API_KEY"):
        return MockLLM()
    return OpenAILLM()
