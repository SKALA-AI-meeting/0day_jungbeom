"""Guardrails: approval for change tools that publish evaluation data, PII masking of tool results, output guard.

Tool policy (also in docs/architecture/harness.md):
  approval required : business.save_report        (the report is shown to the company -> a person approves it)
                      business.decide_account     unless basis is auto_clean (approve) or auto_schema (reject):
                                                  only clear-cut cases are decided without a person
  automatic writes  : business.init_session, business.append_turn, business.save_detection
                      (conversation log bookkeeping; the business rules are enforced again by Spring Boot)
                      business.save_analytics (derived admin snapshot, recomputable; Spring keeps only the newest state_rev)
  read-only         : every rag.*, every analytics.*, detector.describe_rubric / get_session_detections,
                      business.get_session_state / list_conditions / get_account / list_artifacts / get_artifact / list_annotations
  event redaction   : tools.REDACTED_ARGS (observations, dialogue, report, …) never appear in TOOL_START args
"""
from __future__ import annotations

import re

APPROVAL_REQUIRED = {"business.save_report", "business.decide_account"}
AUTO_BASIS = {"auto_clean": "approved", "auto_schema": "rejected"}


class ApprovalRequired(PermissionError):
    pass


def needs_approval(tool: str, args: dict | None = None) -> bool:
    if tool == "business.decide_account":
        a = args or {}
        return AUTO_BASIS.get(a.get("basis")) != a.get("decision")
    return tool in APPROVAL_REQUIRED


def require_approval(tool: str, approved: bool, args: dict | None = None) -> None:
    if needs_approval(tool, args) and not approved:
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
