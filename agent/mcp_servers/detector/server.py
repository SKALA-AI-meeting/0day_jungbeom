"""detector-mcp: external, observer-independent judgement of candidate messages.

Two layers:
  1. rules.py  - deterministic Korean linguistic features (auditable, reproducible)
  2. model     - rubric judgement by a DIFFERENT model family (Gemini) than the in-graph observer (OpenAI),
                 to reduce same-model self-agreement. Falls back to rules-only if unavailable.

Tools (query / mutation):
  describe_rubric          (query)    rubric, lexicons, model id
  detect_message           (mutation) judge one message and store the result
  get_session_detections   (query)    stored results for a session
  delete_session_detections(mutation) remove a session's results (e.g. before re-running)

Run:  uv run --python 3.12 python -m mcp_servers.detector.server     (Streamable HTTP, :9103/mcp)
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from .rules import LEX, features, rule_estimate

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
MODEL = os.getenv("DETECTOR_MODEL", "gemini-3.5-flash")
FALLBACK_MODELS = [m for m in os.getenv("DETECTOR_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-flash-latest").split(",") if m]
DB = Path(os.getenv("DETECTOR_DB", Path(__file__).resolve().parents[2] / "detector.db"))
MAX_TEXT = 2000
_lock = threading.Lock()

RUBRIC = {
    "assertiveness": "1=자기 입장·제안이 거의 없음/모호, 3=입장은 있으나 약함, 5=입장·제안·약속이 분명하고 관철하려 함",
    "cooperativeness": "1=상대 입장 무시·비난, 3=중립, 5=상대 입장 인정·질문·공동 해결 시도가 분명함",
    "focus": "solution=해결·다음 행동 중심, blame=사람·잘못 탓 중심, neutral=그 외",
    "competencies": {
        "C01": "모호한 요구를 질문하거나 핵심 정보를 정리·공유",
        "C02": "역할·의견 차이를 조율하거나 필요한 도움을 요청",
        "C03": "진행·지연·미해결 사항을 공유하거나 일정·맡은 일을 구체적으로 약속",
        "C05": "변경 조건·피드백을 확인하고 계획·결과물 수정을 밝힘",
    },
    "commitment_specificity": "0=약속 없음, 1=모호한 약속('최대한 해볼게요'), 2=누가·무엇을·언제가 분명한 약속",
}


class CompJudge(BaseModel):
    id: Literal["C01", "C02", "C03", "C05"]
    present: bool
    quote: str = Field(description="present=true일 때 근거가 되는 원문 일부를 그대로 복사, 아니면 빈 문자열")


class Judge(BaseModel):
    assertiveness: int = Field(ge=1, le=5)
    cooperativeness: int = Field(ge=1, le=5)
    focus: Literal["solution", "blame", "neutral"]
    commitment_specificity: int = Field(ge=0, le=2)
    competencies: list[CompJudge]
    rationale: str = Field(description="한국어 한 문장")


def _db() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS detections (session_id TEXT, msg_idx INTEGER, doc TEXT, ts REAL, PRIMARY KEY(session_id, msg_idx))")
    return c


_gclient = None


def _gemini():
    global _gclient
    if _gclient is None:
        from google import genai

        key = os.getenv("GOOGLE_API_KEY")
        if not key or os.getenv("DETECTOR_RULES_ONLY") == "1":
            return None
        _gclient = genai.Client(api_key=key)
    return _gclient


async def _model_judge(text: str, context: str, milestone: str) -> tuple[Judge, str] | None:
    client = _gemini()
    if client is None:
        return None
    from google.genai import types

    prompt = f"""너는 채용 대화의 외부 평가 보조자다. 아래 '지원자 발화' 하나만 루브릭으로 판정한다.
점수는 성향 기술용이며 합격 판단이 아니다. 맥락은 참고만 하고 지원자 발화에 실제로 있는 행동만 판정한다.
루브릭: {json.dumps(RUBRIC, ensure_ascii=False)}
현재 단계: {milestone or '알 수 없음'}
맥락(직전 대화): {context[-1500:] or '(없음)'}
지원자 발화: {text}"""
    import asyncio

    cfg = types.GenerateContentConfig(temperature=0, response_mime_type="application/json", response_schema=Judge)
    last: Exception | None = None
    for model in [MODEL, *FALLBACK_MODELS]:
        for attempt in range(2):  # transient 429/503: short backoff, then next model
            try:
                resp = await client.aio.models.generate_content(model=model, contents=prompt, config=cfg)
                j = resp.parsed if isinstance(resp.parsed, Judge) else Judge.model_validate_json(resp.text)
                return j, model
            except Exception as e:
                last = e
                if not any(code in str(e) for code in ("429", "500", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                    break  # not transient (e.g. 404 model retired): try the next model
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last


mcp = FastMCP("detector-mcp", instructions="지원자 발화를 관찰기와 독립적으로 판정하는 외부 디텍터. 점수는 성향 기술용이며 합격 판정에 쓰지 않는다.")


@mcp.tool
def describe_rubric() -> dict:
    """[조회] 디텍터의 루브릭, 규칙 사전(정규식), 사용 모델을 돌려준다."""
    return {"rubric": RUBRIC, "lexicons": LEX, "model": MODEL, "model_enabled": _gemini() is not None}


@mcp.tool
async def detect_message(session_id: str, msg_idx: int, text: str, context: str = "", milestone: str = "", use_model: bool = True) -> dict:
    """[변경] 지원자 발화 하나를 규칙+모델로 판정하고 저장한다. 같은 (session_id, msg_idx)는 덮어쓴다.

    반환: features(규칙 특징), rules(규칙 추정), model(모델 판정 또는 null), final(최종), source, model_error.
    """
    if not session_id or not text.strip():
        raise ToolError("session_id와 text는 비어 있을 수 없어요.")
    if msg_idx < 0:
        raise ToolError("msg_idx는 0 이상이어야 해요.")
    if len(text) > MAX_TEXT:
        raise ToolError(f"text가 너무 길어요(최대 {MAX_TEXT}자).")
    f = features(text)
    r = rule_estimate(f)
    model, err, used_model = None, None, None
    if use_model:
        try:
            out = await _model_judge(text, context, milestone)
            if out is not None:
                j, used_model = out
                comps = [c.model_dump() for c in j.competencies if not c.present or (c.quote and c.quote.strip() in text)]
                model = {**j.model_dump(), "competencies": comps}
        except Exception as e:  # model failure must degrade to rules, never fail the tool
            err = f"{type(e).__name__}: {str(e)[:160]}"
    if model:
        final = {
            "assertiveness": model["assertiveness"], "cooperativeness": model["cooperativeness"], "focus": model["focus"],
            "competencies": sorted({c["id"] for c in model["competencies"] if c["present"]}),
            "commitment_specificity": model["commitment_specificity"],
        }
        source = "rules+model"
    else:
        final = {"assertiveness": r["assertiveness"], "cooperativeness": r["cooperativeness"], "focus": r["focus"],
                 "competencies": r["competencies"], "commitment_specificity": 2 if f["concrete_commit"] else (1 if f["counts"]["vague"] else 0)}
        source = "rules"
    doc = {"session_id": session_id, "msg_idx": msg_idx, "milestone": milestone, "features": f, "rules": r, "model": model,
           "final": final, "source": source, "model_id": used_model if model else None, "model_error": err, "ts": time.time()}
    with _lock, _db() as c:
        c.execute("INSERT OR REPLACE INTO detections VALUES (?,?,?,?)", (session_id, msg_idx, json.dumps(doc, ensure_ascii=False), doc["ts"]))
    return doc


@mcp.tool
def get_session_detections(session_id: str) -> list[dict]:
    """[조회] 세션의 저장된 판정 결과를 msg_idx 순으로 돌려준다."""
    if not session_id:
        raise ToolError("session_id가 필요해요.")
    with _lock, _db() as c:
        rows = c.execute("SELECT doc FROM detections WHERE session_id=? ORDER BY msg_idx", (session_id,)).fetchall()
    return [json.loads(r[0]) for r in rows]


@mcp.tool
def delete_session_detections(session_id: str) -> dict:
    """[변경] 세션의 판정 결과를 모두 삭제한다(재판정 전에 사용)."""
    if not session_id:
        raise ToolError("session_id가 필요해요.")
    with _lock, _db() as c:
        n = c.execute("DELETE FROM detections WHERE session_id=?", (session_id,)).rowcount
    return {"deleted": n}


if __name__ == "__main__":
    mcp.run(transport="http", host=os.getenv("DETECTOR_HOST", "127.0.0.1"), port=int(os.getenv("DETECTOR_PORT", "9103")))
