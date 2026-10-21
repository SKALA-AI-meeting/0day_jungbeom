"""Agent-managed candidate accounts: ACCOUNT_REVIEW graph.

    START -> load -> schema -> normality -> decide --(clean)----------------------> apply -> END
                                                   |--(schema invalid)-------------> apply
                                                   `--(ambiguous) -> approval (interrupt) -> apply

- schema    : the signup schema is satisfied (required fields, types, ranges, enums)  — deterministic
- normality : the values look like a real person's input (rules + model judgement), and the account fits the
              company's target (주니어: 경력 0~3년). Anything unclear is escalated, never auto-rejected.
- apply     : business.decide_account. Guardrails allow it without a person only for auto_clean / auto_schema;
              every other decision needs the admin's approval first (Human-in-the-loop inbox).
"""
from __future__ import annotations

import re
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .graph import traced
from .harness import runtime, tools

JOBS = {"pm", "dev", "design", "sales", "data"}
INDUSTRIES = {"fintech", "health", "commerce", "saas", "mobility"}
TARGET_EXPERIENCE = (0, 3)  # PRD 4: 평가 대상은 주니어(신입~3년차)
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
DISPOSABLE = {"mailinator.com", "10minutemail.com", "guerrillamail.com", "tempmail.com", "temp-mail.org", "yopmail.com", "sharklasers.com",
              "trashmail.com", "getnada.com", "dispostable.com"}
RESERVED = {"example.com", "example.org", "example.net", "test.com", "localhost"}
PLACEHOLDER = re.compile(r"^(test|tester|테스트|admin|관리자|null|none|없음|user|guest|abc|aaa|qwe|asd|sample|샘플|ㅇㅇ|.)\d*$", re.I)
MASH = re.compile(r"(asdf|qwer|zxcv|ㅁㄴㅇㄹ|ㅂㅈㄷㄱ|ㅋㅋㅋ|ㅎㅎㅎ|(.)\2{3,})", re.I)
JAMO_ONLY = re.compile(r"^[ㄱ-ㅎㅏ-ㅣ\s]+$")
INJECTION = re.compile(r"(ignore (all|previous)|이전 지시|시스템 프롬프트|system\s*:|승인\s?해\s?(줘|주세요|라)|승인하(세요|십시오|라)|approve (me|this)|규칙을 무시)", re.I)
URL = re.compile(r"https?://|www\.", re.I)
YEARS_IN_TEXT = re.compile(r"(\d{1,2})\s*(년\s?차|년\s?경력|years?)")


class FieldConcern(BaseModel):
    field: Literal["nickname", "email", "bio", "experience_years", "desired_job", "industry"]
    concern: str = Field(description="어느 내용이 왜 우려되는지 한국어 한 문장")


class Plausibility(BaseModel):
    overall: Literal["clean", "ambiguous"]
    concerns: list[FieldConcern]


class ReviewState(TypedDict, total=False):
    account_id: int
    account: dict
    checks: list[dict]
    schema_errors: list[dict]
    flags: list[dict]
    route: str  # clean | invalid | ambiguous
    decision: dict
    result: dict


async def _progress(stage: str, label: str, status: str = "running") -> None:
    await runtime.emit("PROGRESS", {"stage": stage, "label": label, "status": status})


def schema_errors(a: dict) -> list[dict]:
    errs = []

    def need(cond, field, msg):
        if not cond:
            errs.append({"field": field, "message": msg})

    nick = (a.get("nickname") or "").strip()
    need(2 <= len(nick) <= 20, "nickname", "별칭은 2~20자여야 해요.")
    need(bool(EMAIL.match(a.get("email") or "")), "email", "이메일 형식이 아니에요.")
    need(a.get("desired_job") in JOBS, "desired_job", "희망 직무가 목록에 없어요.")
    need(a.get("industry") in (None, "", *INDUSTRIES), "industry", "관심 산업이 목록에 없어요.")
    exp = a.get("experience_years")
    need(isinstance(exp, int) and 0 <= exp <= 40, "experience_years", "경력은 0~40 사이 정수여야 해요.")
    need(len(a.get("bio") or "") <= 300, "bio", "자기소개는 300자 이하여야 해요.")
    need(a.get("consent") is True, "consent", "평가 안내 동의가 없어요.")
    return errs


def rule_flags(a: dict) -> list[dict]:
    flags = []
    nick = (a.get("nickname") or "").strip()
    if PLACEHOLDER.match(nick) or MASH.search(nick) or JAMO_ONLY.match(nick) or nick.isdigit():
        flags.append({"field": "nickname", "source": "rule", "message": f"별칭 '{nick}'이 자리표시 값이나 의미 없는 문자열로 보여요."})
    email = (a.get("email") or "").lower()
    domain = email.split("@")[-1] if "@" in email else ""
    if domain in DISPOSABLE:
        flags.append({"field": "email", "source": "rule", "message": f"일회용 메일 도메인({domain})이에요."})
    if domain in RESERVED:
        flags.append({"field": "email", "source": "rule", "message": f"예시용으로 예약된 도메인({domain})이에요."})
    exp = a.get("experience_years")
    lo, hi = TARGET_EXPERIENCE
    if isinstance(exp, int) and not (lo <= exp <= hi):
        flags.append({"field": "experience_years", "source": "rule", "message": f"경력 {exp}년은 이번 평가 대상(신입~{hi}년차) 밖이에요."})
    bio = a.get("bio") or ""
    if INJECTION.search(bio):
        flags.append({"field": "bio", "source": "rule", "message": "자기소개에 검토자에게 지시하는 문장이 있어요."})
    if len(URL.findall(bio)) >= 2:
        flags.append({"field": "bio", "source": "rule", "message": "자기소개에 링크가 여러 개 있어요."})
    m = YEARS_IN_TEXT.search(bio)
    if m and isinstance(exp, int) and abs(int(m.group(1)) - exp) >= 2:
        flags.append({"field": "bio", "source": "rule", "message": f"자기소개의 '{m.group(0)}'과 입력한 경력 {exp}년이 맞지 않아요."})
    return flags


async def load(s: ReviewState, config) -> dict:
    await _progress("load", "가입 정보 불러오기")
    a = await tools.call("business", "get_account", {"account_id": s["account_id"]})
    return {"account": a}


async def schema(s: ReviewState, config) -> dict:
    await _progress("schema", "가입 요건(스키마) 확인")
    errs = schema_errors(s["account"])
    checks = [{"stage": "schema", "name": "가입 요건", "ok": not errs, "detail": "모든 필수 항목이 형식에 맞아요." if not errs else f"{len(errs)}개 항목 확인 필요"}]
    await _progress("schema", "가입 요건(스키마) 확인", "done" if not errs else "failed")
    return {"schema_errors": errs, "checks": checks}


async def normality(s: ReviewState, config) -> dict:
    if s["schema_errors"]:
        return {"flags": []}
    await _progress("normality", "입력값이 정상인지 점검")
    flags = rule_flags(s["account"])
    llm = config["configurable"]["llm"]
    try:
        judged = await llm.review_account(s["account"])
        flags += [{"field": c.field, "source": "model", "message": c.concern} for c in judged.concerns]
        model_overall = judged.overall
    except Exception as e:  # model trouble must not auto-approve: escalate instead
        flags.append({"field": "nickname", "source": "harness", "message": f"모델 점검을 끝내지 못했어요({type(e).__name__}). 사람이 확인해 주세요."})
        model_overall = "ambiguous"
    seen, uniq = set(), []
    for f in flags:
        key = (f["field"], f["message"])
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    checks = s["checks"] + [{"stage": "normality", "name": "입력값 점검", "ok": not uniq and model_overall == "clean",
                             "detail": "이상한 점이 없어요." if not uniq else f"{len(uniq)}건 확인 필요"}]
    await _progress("normality", "입력값이 정상인지 점검", "done")
    return {"flags": uniq, "checks": checks}


def decide(s: ReviewState, config) -> dict:
    if s["schema_errors"]:
        return {"route": "invalid"}
    return {"route": "clean" if not s["flags"] else "ambiguous"}


def route(s: ReviewState) -> str:
    return "approval" if s["route"] == "ambiguous" else "apply"


def _recommendation(flags: list[dict]) -> str:
    fields = {f["field"] for f in flags}
    if fields <= {"experience_years"}:
        return "approve"  # only outside the target range: usually a business call, not a bad input
    if "bio" in fields and any("지시" in f["message"] for f in flags):
        return "reject"
    return "ask"


def approval(s: ReviewState, config) -> dict:
    a = s["account"]
    decision = interrupt({
        "kind": "ACCOUNT_REVIEW",
        "tool": "business.decide_account",
        "args": {"account_id": a["id"]},
        "reason": "가입 요건은 맞지만 입력값에 확인할 점이 있어요. 승인하면 계정이 활성화되고, 반려하면 지원자에게 안내돼요.",
        "recommendation": _recommendation(s["flags"]),
        "flags": s["flags"],
        "checks": s["checks"],
    })
    return {"decision": decision if isinstance(decision, dict) else {"approved": bool(decision)}}


async def apply(s: ReviewState, config) -> dict:
    await _progress("apply", "결정 반영")
    review = {"checks": s.get("checks", []), "flags": s.get("flags", []), "schema_errors": s.get("schema_errors", [])}
    if s["route"] == "invalid":
        args = {"decision": "rejected", "basis": "auto_schema", "reason": "가입 요건 불충족",
                "review": {**review, "candidate_message": "가입 정보 중 " + ", ".join(e["message"] for e in s["schema_errors"])}}
    elif s["route"] == "clean":
        args = {"decision": "approved", "basis": "auto_clean", "reason": "요건 충족, 확인할 점 없음", "review": review}
    else:
        d = s["decision"]
        ok = bool(d.get("approved"))
        args = {"decision": "approved" if ok else "rejected", "basis": "admin_approved" if ok else "admin_rejected",
                "reason": d.get("comment") or ("관리자 승인" if ok else "관리자 반려"),
                "review": {**review, "admin": d.get("by"), "candidate_message": None if ok else "담당자 확인 결과 이번 평가에 참여할 수 없어요."}}
    res = await tools.call("business", "decide_account", {"account_id": s["account_id"], **args}, approved=s["route"] == "ambiguous")
    await _progress("apply", "결정 반영", "done")
    return {"result": {"status": res.get("status"), "basis": args["basis"]}}


def build_account_review_graph(checkpointer=None):
    g = StateGraph(ReviewState)
    for name, fn in (("load", load), ("schema", schema), ("normality", normality), ("decide", decide), ("apply", apply)):
        g.add_node(name, traced(fn))
    g.add_node("approval", approval)  # interrupt() runs in the node itself
    g.add_edge(START, "load")
    g.add_edge("load", "schema")
    g.add_edge("schema", "normality")
    g.add_edge("normality", "decide")
    g.add_conditional_edges("decide", route, {"approval": "approval", "apply": "apply"})
    g.add_edge("approval", "apply")
    g.add_edge("apply", END)
    return g.compile(checkpointer=checkpointer)
