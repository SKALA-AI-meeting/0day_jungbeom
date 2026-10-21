"""Guardrails: approval for change tools that publish evaluation data, PII masking of tool results, output guard.

Tool policy (also in docs/architecture/harness.md):
  approval required : business.save_report        (the report is shown to the company -> a person approves it)
  automatic writes  : business.init_session, business.append_turn, business.save_detection
                      (conversation log bookkeeping; the business rules are enforced again by Spring Boot)
  read-only         : every rag.* and detector.describe_rubric / get_session_detections
"""
from __future__ import annotations

import re

APPROVAL_REQUIRED = {"business.save_report"}


class ApprovalRequired(PermissionError):
    pass


def require_approval(tool: str, approved: bool) -> None:
    if tool in APPROVAL_REQUIRED and not approved:
        raise ApprovalRequired(f"{tool} needs human approval (interrupt) before it can run")


_PII = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[이메일]"),
    (re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"), "[전화번호]"),
    (re.compile(r"\b\d{6}-?[1-4]\d{6}\b"), "[주민번호]"),
]


def mask(obj):
    """Mask PII inside any JSON-like tool result."""
    if isinstance(obj, str):
        for pat, rep in _PII:
            obj = pat.sub(rep, obj)
        return obj
    if isinstance(obj, list):
        return [mask(x) for x in obj]
    if isinstance(obj, dict):
        return {k: mask(v) for k, v in obj.items()}
    return obj


# Personas must never talk about the assessment itself (PRD F-24).
_FORBIDDEN = re.compile(r"점수|합격|불합격|평가\s?(결과|기준|중)|관찰\s?(중|하고)|시뮬레이션|테스트\s?중|성향\s?(검사|분석)")


def violates_output_policy(text: str) -> bool:
    return bool(_FORBIDDEN.search(text or ""))
