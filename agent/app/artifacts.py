"""Shared work items ("같이 확인할 과제"): the design doc, result table and code the team looks at together.

The agent owns the catalog (seeded into Spring at START via business.init_session); the candidate marks them up in the
browser (Spring stores the annotations); personas read both through the session state and the open_shared_artifact tool.

Interface used across the agent (keep the signatures stable — see docs/architecture/api-contract.md):
    catalog(scn, scenario_id) -> list[Artifact]          # what START seeds (with checkpoints; strip them before seeding)
    context_block(session, *, new_ids=None) -> str       # compact table + new markups for persona/director prompts
    render_for_model(artifact) -> str                    # line-numbered body + its annotations (tool output)
    ARTIFACT_TOOL                                        # LLM tool schema the personas can call
Artifact = {id, kind: design|result|code, title, owner: lead|peer|team, status, summary, lang, body}
Annotation = {id, artifact_id, anchor: {line_start, line_end, quote}, kind: question|risk|suggest|ok, text, msg_idx, created_at}

Planted checkpoints: every catalog artifact carries `checkpoints: [{line, issue}]`, 1–2 deliberate problems (a bug, a
number that disagrees with another artifact, an ambiguous scope line, a missing review step) a careful teammate would
mark. They never leave the agent: START seeds without_checkpoints(catalog(...)), and only the admin view compares them
with the candidate's annotations (artifact_checks).

Every scenario gets the same three kinds, owned consistently with the personas (lead = 한서윤 팀장, peer = 이도현):
design (Markdown spec), result (Markdown metric table + one LaTeX formula), code (15–40 lines in the job's language).
Dilemma scenarios fill one template per job with the industry's company, service, metric and review gate; the variant
follows the axis criteria.pick_axis gives today (a job/industry whose axis changes falls back to a variant its data has).
"""
from __future__ import annotations

import copy
import re

from .criteria import INDUSTRIES, JOBS

KIND_LABEL = {"design": "설계·기획", "result": "결과", "code": "코드"}
MARK_LABEL = {"question": "질문", "risk": "우려", "suggest": "제안", "ok": "확인함"}
OWNER_LABEL = {"lead": "팀장", "peer": "동료", "team": "팀 공동"}
FIELDS = ("id", "kind", "title", "owner", "status", "summary", "lang", "body")  # what Spring stores (no checkpoints)
MAX_LEN = {"id": 16, "title": 80, "status": 20, "summary": 160, "body": 6000}

ARTIFACT_TOOL = {
    "type": "function",
    "function": {
        "name": "open_shared_artifact",
        "description": "팀이 같이 보는 과제(기획 문서·결과 표·코드)를 줄 번호와 지원자가 남긴 마크업과 함께 연다. 과제의 특정 내용이나 마크업을 두고 말하기 전에 쓴다.",
        "parameters": {"type": "object", "properties": {"artifact_id": {"type": "string", "description": "과제 id (예: a1)"}}, "required": ["artifact_id"]},
    },
}


# ----------------------------------------------------------------------------------------------------------- builder

_TOKEN = re.compile(r"«(\w+)»")


def _sub(text: str, kw: dict) -> str:
    return _TOKEN.sub(lambda m: str(kw[m.group(1)]), text)


class _Body:
    """One row per line; a (line, issue) tuple plants a checkpoint on exactly the line it writes."""

    def __init__(self, kw: dict) -> None:
        self.kw, self.lines, self.checks = kw, [], []

    def __call__(self, *rows) -> "_Body":
        for r in rows:
            line, issue = r if isinstance(r, tuple) else (r, None)
            text = _sub(line, self.kw)
            if "\n" in text:
                raise ValueError(f"multi-line row: {text[:40]}")
            self.lines.append(text)
            if issue:
                self.checks.append({"line": len(self.lines), "issue": _sub(issue, self.kw)})
        return self


def _art(kind: str, title: str, owner: str, status: str, summary: str, body: _Body, lang: str | None = None) -> dict:
    return {"id": "", "kind": kind, "title": _sub(title, body.kw), "owner": owner, "status": status,
            "summary": _sub(summary, body.kw), "lang": lang, "body": "\n".join(body.lines), "checkpoints": list(body.checks)}


def _n(x: int) -> str:
    return f"{x:,}"


def _p(num: int, den: int) -> str:
    return f"{100 * num / den:.1f}%"


def _r(x: float) -> str:
    return f"{100 * x:.1f}%"


def _pp(a: str, b: str) -> float:
    """Percentage-point gap between two displayed rates ("34.0%" - "30.4%"), as a reader would compute it."""
    return round(float(b.rstrip("%")) - float(a.rstrip("%")), 1)


def _tex(name: str, num: str, den: str) -> str:
    return "$$\\text{" + name + "}=\\frac{\\text{" + num + "}}{\\text{" + den + "}}\\times 100$$"


# Industry nouns shared by every job: counts behind the metric and a plausible daily volume / baseline rate.
DOMAIN = {
    "fintech": {"num_count": "정산 완료 건수", "den_count": "정산 요청 건수", "metric_key": "settlement_completion_rate", "vol": 4120, "base": 0.962},
    "health": {"num_count": "수신 확인 건수", "den_count": "알림 발송 건수", "metric_key": "reminder_receipt_rate", "vol": 8640, "base": 0.914},
    "commerce": {"num_count": "결제 완료 수", "den_count": "결제 시작 수", "metric_key": "checkout_conversion_rate", "vol": 3180, "base": 0.312},
    "saas": {"num_count": "성공한 실행 수", "den_count": "전체 실행 수", "metric_key": "automation_success_rate", "vol": 15400, "base": 0.987},
    "mobility": {"num_count": "대여 성공 수", "den_count": "대여 시도 수", "metric_key": "rental_success_rate", "vol": 6250, "base": 0.941},
}


def _variant(axis: str, data: dict, options: list[tuple[str, str, object]]):
    """options: (axis, key the industry data must have, builder). Prefer the scenario's axis, else what the data supports."""
    for ax, key, fn in options:
        if ax == axis and key in data:
            return fn
    return next(fn for _, key, fn in options if key in data)


# ------------------------------------------------------------------------------------------------------ PM (기획·PM)

PM = {
    "fintech": {
        "feature": "정산 예정일 미리보기", "flag": "settlement_preview", "squad": "settlement-squad",
        "pain": "정산 요청 뒤 '언제 들어오나요' 문의가 월 1,200건으로 CS 문의 1위예요",
        "scope0": "정산 요청 화면에 입금 예정일·수수료 미리보기", "scope1": "예정일이 바뀌면 앱 알림 1회",
        "pii_scope": "미리보기에 정산 계좌(은행명·끝 4자리) 함께 표시", "out": "정산 주기·수수료 정책 변경",
        "vague": "필요하면 대표자 휴대폰 문자 안내도 추가",
        "vague_issue": "'필요하면'만 있고 누가 언제 정하는지 없어요. 대표자 휴대폰 번호를 쓰면 개인정보 검토 범위도 달라져요.",
        "accept": "미리보기 수수료와 실제 차감액 차이 0원(원 단위 절사)",
        "review0": "수수료 계산 로직", "review1": "화면·알림 문구",
        "review_issue": "범위에 정산 계좌 표시가 있고 트래킹 명세(a3)에도 account_last4가 남는데, 검토 요청 항목에 계좌 정보가 빠져 있어요.",
        "beta": "베타 가맹점 40곳", "audience": 'merchant_group == "beta_40"',
        "ev1": "preview_viewed", "props1": "merchant_id, expected_date, fee_amount, account_last4",
        "prop_issue": "트래킹 속성에 account_last4(계좌 끝자리)가 들어가요. 검토 요청 항목(a1)에 없는 개인정보예요.",
        "ev2": "preview_date_changed", "props2": "merchant_id, old_date, new_date",
        "ask": ("예정일 문의", 41, 29), "extra": ("미리보기 확인율", "72.4%", "78.0%"),
    },
    "health": {
        "feature": "복약 시간 맞춤 알림", "flag": "dose_time_reminder", "squad": "care-squad",
        "pain": "복약 알림을 꺼 버린 환자의 61%가 '시간이 안 맞는다'고 답했어요",
        "scope0": "처방 정보로 복약 시간 자동 제안(아침·점심·저녁·취침 전)", "scope1": "환자가 시간을 바꾸면 다음 알림부터 반영",
        "pii_scope": "잠금화면 알림에 약품명·용량 표시", "out": "처방 내용 변경, 병원 EMR 연동",
        "vague": "필요하면 보호자에게도 같은 알림 발송",
        "vague_issue": "'필요하면'만 있고 누가 정하는지 없어요. 보호자 발송은 건강 정보를 제3자에게 보내는 일이라 검토 범위가 달라져요.",
        "accept": "바꾼 복약 시간이 바로 다음 알림부터 반영",
        "review0": "처방 정보 조회 범위", "review1": "알림 문구",
        "review_issue": "범위에 잠금화면 약품명 표시가 있고 트래킹 명세(a3)에도 drug_name이 남는데, 검토 요청 항목에 빠져 있어요.",
        "beta": "베타 환자 300명", "audience": 'patient_group == "beta_300"',
        "ev1": "reminder_shown", "props1": "patient_id, slot, drug_name, shown_at",
        "prop_issue": "트래킹 속성에 drug_name(약품명)이 남아요. 건강 정보라 검토 요청 항목(a1)에 들어가야 해요.",
        "ev2": "reminder_time_changed", "props2": "patient_id, slot, old_time, new_time",
        "ask": ("알림 끄기", 52, 37), "extra": ("추천 시간 수락률", "64.0%", "69.5%"),
    },
    "commerce": {
        "feature": "첫 주문 무료배송 쿠폰", "flag": "first_order_free_delivery", "squad": "growth-squad",
        "pain": "결제 화면까지 온 신규 고객 10명 중 7명이 배송비를 보고 나가요",
        "scope0": "신규 고객 첫 주문 배송비 0원 쿠폰 자동 발급", "scope1": "결제 화면에 쿠폰 적용 금액 표시",
        "out": "기존 고객 쿠폰, 최소 주문 금액 변경", "rule": "쿠폰은 고객 1명당 1회만 발급",
        "unit_ok": "고객(user_id) 단위 50:50", "unit_bad": "session_id",
        "unit_issue": "실험 단위가 session_id라 같은 고객이 두 군에 모두 들어갈 수 있어요. 기획안은 고객 단위예요.",
        "guard_key": "max_coupons_per_user", "guard_bad": "2",
        "guard_issue": "고객당 쿠폰 발급 한도가 2로 돼 있어요. 기획안 운영 규칙은 1인 1회예요.",
        "second": ("2주 내 재구매율", "18.1%", "21.7%", "+3.6%p"), "lift": 0.036,
        "peer_work": "쿠폰 발급·중복 차단 API",
        "ev1": "coupon_issued", "props1": "user_id, coupon_id, issued_at",
        "ev2": "checkout_paid", "props2": "user_id, order_id, coupon_id, paid_amount",
    },
    "saas": {
        "feature": "결재 승인 자동화 템플릿", "flag": "approval_templates", "squad": "automation-squad",
        "pain": "고객사 관리자가 결재 자동화를 직접 만들다 막히는 경우가 많아요. 실행 실패의 절반이 설정 오류예요",
        "scope0": "결재·경비·휴가 승인 템플릿 3종", "scope1": "설치 단계에서 필수 결재자 누락 경고",
        "out": "외부 전자결재 연동, 고객사 맞춤 템플릿", "rule": "템플릿 설치는 워크스페이스 관리자만",
        "unit_ok": "고객사(workspace_id) 단위 50:50", "unit_bad": "user_id",
        "unit_issue": "실험 단위가 user_id라 한 고객사 안에서 두 군이 섞여요. 기획안은 고객사 단위예요.",
        "guard_key": "install_role", "guard_bad": "member",
        "guard_issue": "설치 권한이 member로 열려 있어요. 기획안 운영 규칙은 관리자만 설치예요.",
        "second": ("설정 오류 실패 비율", "0.7%", "0.3%", "−0.4%p"), "lift": 0.006,
        "peer_work": "템플릿 설치·검증 API",
        "ev1": "template_installed", "props1": "workspace_id, template_id, installed_by",
        "ev2": "run_finished", "props2": "workspace_id, template_id, status, duration_ms",
    },
    "mobility": {
        "feature": "QR 실패 시 기기 번호 대여", "flag": "manual_unlock", "squad": "rental-squad",
        "pain": "대여 실패의 38%가 QR 인식 실패예요. 야간과 비 오는 날에 몰려요",
        "scope0": "QR 인식이 3초 넘게 안 되면 기기 번호 6자리 입력 안내", "scope1": "입력한 기기와 이용자 위치가 50m 넘게 떨어지면 재확인",
        "out": "NFC 대여, 기기 QR 스티커 교체", "rule": "번호 입력은 대여 1건당 3번까지",
        "unit_ok": "이용자(user_id) 단위 50:50", "unit_bad": "attempt_id",
        "unit_issue": "실험 단위가 attempt_id라 같은 이용자가 시도마다 다른 군에 들어가요. 기획안은 이용자 단위예요.",
        "guard_key": "max_manual_tries", "guard_bad": "5",
        "guard_issue": "번호 입력 허용 횟수가 5번이에요. 기획안 운영 규칙은 3번까지예요.",
        "second": ("QR 실패 후 이탈률", "41.0%", "23.5%", "−17.5%p"), "lift": 0.021,
        "peer_work": "기기 번호 대여·위치 확인 API",
        "ev1": "manual_unlock_prompted", "props1": "user_id, device_id, qr_fail_ms",
        "ev2": "rental_started", "props2": "user_id, device_id, method",
    },
}


def _pm_review(c: dict) -> list[dict]:
    """V2: the launch is Friday, the review gate slipped to next Tuesday."""
    vol, base = c["vol"], c["base"]
    target = round(base + 0.009, 3)
    w1d, w2d = round(vol * 0.64), round(vol * 0.68)
    w1n, w2n = round(w1d * (base + 0.004)), round(w2d * (base + 0.006))
    ask, a0, a1 = c["ask"]
    kw = {**c, "last": _r(base), "target_s": _r(target), "w1d": _n(w1d), "w2d": _n(w2d), "w1n": _n(w1n), "w2n": _n(w2n),
          "w1r": _p(w1n, w1d), "w2r": _p(w2n, w2d), "w2_shown": _r(w2n / w2d + 0.012), "ask0": ask, "a0": a0, "a1": a1,
          "drop": _p(a0 - a1, a0), "ex0": c["extra"][0], "ex1": c["extra"][1], "ex2": c["extra"][2], "alert": round(base - 0.02, 3),
          "formula": _tex(c["metric"], c["num_count"], c["den_count"])}
    design = _Body(kw)(
        "# «feature» 기획안",
        "> «company» · «service» · 작성: 기획(지원자) · 검토: 한서윤 팀장 · 기능 명세: 이도현",
        "",
        "## 1. 배경",
        "- «pain».",
        "- «metric»: 지난달 «last» → 이번 분기 목표 «target_s»",
        "",
        "## 2. 범위",
        "- 포함: «scope0»",
        "- 포함: «scope1»",
        "- 포함: «pii_scope»",
        "- 제외: «out»",
        ("- 미정: «vague»", "«vague_issue»"),
        "",
        "## 3. 수용 기준",
        "1. «accept»",
        "2. «metric» «target_s» 이상 (출시 2주 후)",
        "3. «ask0» 30% 감소",
        "",
        "## 4. 일정",
        "| 단계 | 담당 | 시점 |",
        "|---|---|---|",
        "| 기획 확정 | 기획 | 월 |",
        "| «peer_artifact» | 이도현 | 화 |",
        "| 개발·QA | 이도현 | 수–목 |",
        "| 출시·고객 안내 | 팀 | 금 |",
        "| «gate» | 검토팀 | 다음 주 화 (일정 밀림) |",
        "",
        "## 5. «gate» 요청 항목",
        "- «review0»",
        ("- «review1»", "«review_issue»"),
    )
    result = _Body(kw)(
        "# 베타 테스트 결과 — «feature»",
        "> «beta» · 2주 · 정리: 한서윤 팀장",
        "",
        "| 지표 | 1주 차 | 2주 차 | 목표 |",
        "|---|---:|---:|---:|",
        "| «den_count» | «w1d» | «w2d» | – |",
        "| «num_count» | «w1n» | «w2n» | – |",
        ("| «metric» | «w1r» | «w2_shown» | «target_s» |",
         "2주 차는 «w2n»/«w2d» = «w2r»라 목표(«target_s») 미달인데 «w2_shown»로 적혀 있어요. 아래 '목표를 넘겼다'는 판단도 이 숫자에 기대고 있어요."),
        "| «ask0»(건) | «a0» | «a1» | 30% 감소 |",
        "| «ex0» | «ex1» | «ex2» | – |",
        "",
        "«formula»",
        "",
        "- 2주 차에 «metric» 목표를 넘겨서 금요일 출시에는 문제가 없다고 봐요.",
        "- «ask0»는 «drop» 줄어 목표(30%)에 거의 닿았어요.",
    )
    code = _Body(kw)(
        "# «feature» — 기능 플래그·트래킹 명세 («peer_artifact» 부록)",
        "# 작성: 이도현 · 상태: 리뷰 요청",
        "flag: «flag»",
        "owner: «squad»",
        "default: off",
        "rollout:",
        "  - stage: beta",
        "    audience: '«audience»'",
        "    percent: 100",
        "  - stage: launch",
        '    when: "금 10:00"',
        "    percent: 100",
        ("    requires: [qa_signoff, cs_notice_sent]",
         "출시 조건(requires)에 «gate» 통과가 없어요. 기획안 일정상 검토는 다음 주 화요일인데 금요일 출시가 그대로 열려요."),
        "kill_switch: «flag»_off",
        "alerts:",
        "  - metric: «metric_key»",
        "    window: 1h",
        "    below: «alert»",
        "tracking:",
        "  - event: «ev1»",
        ("    props: [«props1»]", "«prop_issue»"),
        "  - event: «ev2»",
        "    props: [«props2»]",
    )
    return [
        _art("design", "«artifact» — «feature»", "team", "검토 대기", "금요일 출시 예정인 «feature» 범위·수용 기준·일정. «gate»는 다음 주 화요일로 밀렸어요.", design),
        _art("result", "베타 테스트 결과 — «feature»", "lead", "공유됨", "«beta» 2주 베타의 «metric»·문의 지표 (팀장 정리).", result),
        _art("code", "«peer_artifact» 부록 — 플래그·트래킹", "peer", "리뷰 요청", "«feature» 출시 플래그, 알림 기준, 트래킹 이벤트 명세 (이도현).", code, "yaml"),
    ]


def _pm_done(c: dict) -> list[dict]:
    """V1: the feature shipped well; tomorrow someone presents it and leads the follow-up."""
    vol, base = c["vol"], c["base"]
    cd, td = round(vol * 10.5), round(vol * 10.6)
    ctrl = base - 0.008
    cn, tn = round(cd * ctrl), round(td * (ctrl + c["lift"]))
    cr, tr = _p(cn, cd), _p(tn, td)
    diff = _pp(cr, tr)
    s_label, s0, s1, s2 = c["second"]
    kw = {**c, "base_s": _r(base), "cd": _n(cd), "td": _n(td), "cn": _n(cn), "tn": _n(tn), "cr": cr, "tr": tr,
          "diff_ok": f"{diff:+.1f}%p", "diff_shown": f"{diff + 0.5:+.1f}%p", "s_label": s_label, "s0": s0, "s1": s1, "s2": s2,
          "formula": _tex(c["metric"], c["num_count"], c["den_count"])}
    design = _Body(kw)(
        "# «feature» 기획안 (출시 완료)",
        "> «company» · «service» · 작성: 기획(지원자) · 검토: 한서윤 팀장 · 기능 명세·구현: 이도현",
        "",
        "## 1. 배경",
        "- «pain».",
        ("- 현재 «metric» «base_s» (지난 4주 평균)",
         "기획안의 현재 «metric»(«base_s»)이 실험 대조군(a2, «cr»)과 달라요. 기준 기간이 다른지 맞춰 봐야 해요."),
        "",
        "## 2. 범위",
        "- 포함: «scope0»",
        "- 포함: «scope1»",
        "- 제외: «out»",
        "- 운영 규칙: «rule»",
        "",
        "## 3. 실험·적용 기준",
        "1. «unit_ok», 최소 14일",
        ("2. «metric»이 의미 있게 오르면 전체 적용", "'의미 있게'만 있고 몇 %p 이상, 어떤 유의 수준이면 적용하는지 기준이 없어요."),
        "3. 보조 지표: «s_label»",
        "",
        "## 4. 역할",
        "- 문제 정의·아이디어: 기획(지원자)",
        "- «peer_work»·실험 운영: 이도현 (마지막 2주 실무 대부분)",
        "- 실험 설계 검토·전체 적용 결정: 한서윤 팀장",
        "",
        "## 5. 일정",
        "| 단계 | 담당 | 시점 |",
        "|---|---|---|",
        "| 기획 확정 | 기획 | 6주 전 |",
        "| 개발·QA | 이도현 | 5–4주 전 |",
        "| A/B 실험·운영 | 이도현 | 3주 전–지난주 |",
        "| 전체 적용 | 팀 | 지난주 금 |",
    )
    result = _Body(kw)(
        "# A/B 실험 결과 — «feature»",
        "> 3주 · «unit_ok» · 정리: 한서윤 팀장",
        "",
        "| 지표 | 대조군 | 실험군 | 차이 |",
        "|---|---:|---:|---:|",
        "| «den_count» | «cd» | «td» | – |",
        "| «num_count» | «cn» | «tn» | – |",
        ("| «metric» | «cr» | «tr» | «diff_shown» |", "차이가 «diff_shown»로 적혀 있는데 «tr» − «cr» = «diff_ok»예요. 내일 발표 자료에 그대로 들어갈 숫자예요."),
        "| «s_label» | «s0» | «s1» | «s2» |",
        "",
        "«formula»",
        "",
        "- «metric»이 «diff_shown» 올라 지난주 금요일 전체 적용했어요.",
        "- 내일 전사 회의 발표 자료에 이 표를 그대로 써요.",
    )
    code = _Body(kw)(
        "# «feature» — 실험·플래그 명세 («peer_artifact» 부록)",
        "# 작성: 이도현 · 상태: 전체 적용 완료(지난주 금)",
        "flag: «flag»",
        "owner: «squad»",
        "experiment:",
        "  metric: «metric_key»",
        "  split: {control: 50, treatment: 50}",
        ("  unit: «unit_bad»", "«unit_issue»"),
        "  min_days: 14",
        "  ran_days: 21",
        "rollout:",
        "  - stage: experiment",
        "    percent: 100",
        "  - stage: full",
        "    percent: 100",
        "    approved_by: 한서윤",
        "guard:",
        ("  «guard_key»: «guard_bad»", "«guard_issue»"),
        "tracking:",
        "  - event: «ev1»",
        "    props: [«props1»]",
        "  - event: «ev2»",
        "    props: [«props2»]",
    )
    return [
        _art("design", "«artifact» — «feature»", "team", "출시 완료", "지난주 전체 적용한 «feature»의 배경·범위·실험 기준과 역할 분담.", design),
        _art("result", "A/B 실험 결과 — «feature»", "lead", "공유됨", "3주 A/B 실험의 «metric»·보조 지표 비교 (팀장 정리, 내일 발표 자료).", result),
        _art("code", "«peer_artifact» 부록 — 실험·플래그", "peer", "적용 완료", "«feature» 실험 설정, 운영 가드, 트래킹 이벤트 명세 (이도현).", code, "yaml"),
    ]


def _pm(c: dict, axis: str) -> list[dict]:
    return _variant(axis, c, [("V2", "pii_scope", _pm_review), ("V1", "unit_ok", _pm_done)])(c)


# ------------------------------------------------------------------------------------------------------ 개발 (dev)

DEV = {
    "fintech": {"feature": "정산 콜백 처리 개편", "upstream": "은행 펌뱅킹", "ok_new_label": "부분 정산", "lang": "kotlin",
                "pkg": "com.paylog.settlement.callback", "E": "Settlement", "var": "bank", "Client": "BankClient",
                "st": ("REQUESTED", "PROCESSING", "COMPLETED", "COMPLETED_PARTIAL", "FAILED"), "event": "settlement_completed"},
    "health": {"feature": "복약 알림 수신 처리 개편", "upstream": "푸시 게이트웨이", "ok_new_label": "방해 금지 시간 무음 수신", "lang": "python",
               "pkg": "carenote.reminder.receipt", "E": "Reminder", "var": "gateway", "Client": "PushGateway",
               "st": ("QUEUED", "SENT", "DELIVERED", "DELIVERED_QUIET", "FAILED"), "event": "reminder_delivered"},
    "commerce": {"feature": "결제 승인 연동 개편", "upstream": "PG사 승인", "ok_new_label": "포인트 전액 결제", "lang": "kotlin",
                 "pkg": "com.jangbo.checkout.payment", "E": "Checkout", "var": "pg", "Client": "PgClient",
                 "st": ("CREATED", "PENDING", "PAID", "PAID_BY_POINT", "FAILED"), "event": "checkout_paid"},
    "saas": {"feature": "워크플로 실행 결과 처리 개편", "upstream": "커넥터 실행기", "ok_new_label": "재시도 후 성공", "lang": "python",
             "pkg": "workflo.engine.runs", "E": "WorkflowRun", "var": "executor", "Client": "ConnectorExecutor",
             "st": ("QUEUED", "RUNNING", "SUCCEEDED", "SUCCEEDED_AFTER_RETRY", "FAILED"), "event": "run_succeeded"},
    "mobility": {"feature": "대여 잠금 해제 API 개편", "upstream": "킥보드 IoT 게이트웨이", "ok_new_label": "재시도 후 잠금 해제", "lang": "kotlin",
                 "pkg": "com.tagoga.rental.unlock", "E": "Rental", "var": "iot", "Client": "IotGateway",
                 "st": ("REQUESTED", "UNLOCKING", "UNLOCKED", "UNLOCKED_ON_RETRY", "FAILED"), "event": "rental_started"},
}

_KOTLIN_HANDLER = [
    "// «peer_artifact»: «feature» — 어제 17:00 배포분 · 담당: 이도현",
    "package «pkg»",
    "",
    "enum class «E»Status { «s0», «s1», «s2», «s3», «s4» }",
    "",
    "data class «E»Callback(val id: String, val code: String)",
    "",
    "class «E»CallbackHandler(",
    "    private val events: EventPublisher,",
    "    private val «var»: «Client»,",
    "    private val manualQueue: ManualQueue,",
    ") {",
    "    private val maxRetries = 3",
    "",
    "    fun handle(cb: «E»Callback) {",
    "        val status = toStatus(cb.code)",
    ("        if (status == «E»Status.«s2») {", "«miss_issue»"),
    '            events.publish("«event»", cb.id)',
    "        }",
    "        if (status == «E»Status.«s1» && !confirm(cb.id)) {",
    "            manualQueue.push(cb.id)",
    "        }",
    "    }",
    "",
    "    private fun confirm(id: String): Boolean {",
    ("        for (attempt in 1 until maxRetries) {", "반복 범위 때문에 확인 요청이 2번만 가요(`1 until maxRetries`). 배포 계획(a1)은 최대 3회예요."),
    "            if («var».confirm(id)) return true",
    "            Thread.sleep(200L * attempt)",
    "        }",
    "        return false",
    "    }",
    "",
    "    private fun toStatus(code: String) = when (code) {",
    '        "00" -> «E»Status.«s2»',
    '        "01" -> «E»Status.«s3»',
    '        "10" -> «E»Status.«s1»',
    "        else -> «E»Status.«s4»",
    "    }",
    "}",
]

_PY_HANDLER = [
    "# «peer_artifact»: «feature» — 어제 17:00 배포분 · 담당: 이도현 («pkg»)",
    "import time",
    "from enum import Enum",
    "",
    "",
    "class «E»Status(str, Enum):",
    '    «s0» = "«s0»"',
    '    «s1» = "«s1»"',
    '    «s2» = "«s2»"',
    '    «s3» = "«s3»"',
    '    «s4» = "«s4»"',
    "",
    "",
    "class «E»ResultHandler:",
    "    max_retries = 3",
    "",
    "    def __init__(self, events, «var», manual_queue):  # «var»: «Client»",
    "        self.events, self.«var», self.manual_queue = events, «var», manual_queue",
    "",
    "    def handle(self, result: dict) -> None:",
    '        status = self.to_status(result["code"])',
    ("        if status == «E»Status.«s2»:", "«miss_issue»"),
    '            self.events.publish("«event»", result["id"])',
    '        if status == «E»Status.«s1» and not self.confirm(result["id"]):',
    '            self.manual_queue.push(result["id"])',
    "",
    "    def confirm(self, item_id: str) -> bool:",
    ("        for attempt in range(1, self.max_retries):", "반복 범위 때문에 확인 요청이 2번만 가요(`range(1, self.max_retries)`). 배포 계획(a1)은 최대 3회예요."),
    "            if self.«var».confirm(item_id):",
    "                return True",
    "            time.sleep(0.2 * attempt)",
    "        return False",
    "",
    "    @staticmethod",
    "    def to_status(code: str) -> «E»Status:",
    '        mapping = {"00": «E»Status.«s2», "01": «E»Status.«s3», "10": «E»Status.«s1»}',
    "        return mapping.get(code, «E»Status.«s4»)",
]


def _dev(c: dict, axis: str) -> list[dict]:
    """V3: the metric fell after yesterday's deploy; cause unknown, maybe a collection error."""
    vol, base = c["vol"], c["base"]
    avg_n = round(vol * base)
    rows = [("3일 전", round(vol * 0.996), base + 0.001, ""), ("2일 전", round(vol * 1.017), base, ""),
            ("어제", round(vol * 1.03), base - 0.051, "17:00 배포")]
    t_den = round(vol * 0.32)
    t_num = round(t_den * (base - 0.133))
    d1_den, d1_num = rows[-1][1], round(rows[-1][1] * rows[-1][2])
    kw = {**c, **{f"s{i}": s for i, s in enumerate(c["st"])}, "avg_d": _n(vol), "avg_n": _n(avg_n), "base_s": _p(avg_n, vol),
          "t_den": _n(t_den), "t_num": _n(t_num), "t_r": _p(t_num, t_den), "new_count": _n(round(d1_den * base) - d1_num - 3),
          "formula": _tex(c["metric"], c["num_count"], c["den_count"])}
    kw["miss_issue"] = _sub("«ok_new_label» 상태(«s3»)일 때 완료 이벤트를 보내지 않아서 «metric» 분자에서 빠져요. 배포 계획(a1) 수용 기준 1과 달라요.", kw)
    design = _Body(kw)(
        "# «feature» — 배포 계획",
        "> «company» · «service» · 배포: 어제 17:00 · 정리: 한서윤 팀장",
        "> 구현: 지원자(«artifact»), 이도현(«peer_artifact»)",
        "",
        "## 변경 사항",
        "- «upstream» 응답 코드를 새 상태 체계로 매핑 (`«s3»`: «ok_new_label» 추가)",
        "- 확인 요청 재시도: 최대 3회, 간격 200ms씩 증가",
        "- 완료 이벤트 이름은 그대로: `«event»`",
        "",
        "## 수용 기준",
        "1. «ok_new_label» 건도 완료로 집계한다",
        "2. 재시도 3회 안에 확인되지 않으면 수동 확인 대기열로 보낸다",
        "3. 배포 후 «metric»이 배포 전 7일 평균(«base_s»)과 같은 수준이다",
        "",
        "## 모니터링·롤백",
        "- 배포 후 24시간 동안 «metric»을 1시간 단위로 본다",
        ("- 지표가 많이 떨어지면 롤백을 검토한다", "'많이'가 몇 %p인지, 몇 시간 지속되면 판단하는지 없어요. 지금처럼 원인이 불확실할 때 누가 언제 결정할지 정해지지 않아요."),
        "- 롤백 판단: 한서윤 팀장 · 실행: 이도현",
        "",
        "## 공유",
        "- 장애로 판단되면 운영·CS 채널에 공지 (공지 문안: 지원자)",
    )
    result = _Body(kw)(
        "# «metric» 배포 전후 (일 단위)",
        "> 출처: 운영 대시보드 · 배포: 어제 17:00 · 오늘은 09:00까지 집계 · 정리: 지원자",
        "",
        "| 일자 | «den_count» | «num_count» | «metric» | 비고 |",
        "|---|---:|---:|---:|---|",
        "| 배포 전 7일 일평균 | «avg_d» | «avg_n» | «base_s» | 기준 |",
        *[f"| {label} | {_n(d)} | {_n(round(d * r))} | {_p(round(d * r), d)} | {note} |" for label, d, r, note in rows],
        ("| 오늘(09시까지) | «t_den» | «t_num» | «t_r» | 집계 중 |",
         "오늘은 09시까지 부분 집계라 처리 중인 건이 남아 있어요. 하루 단위 행과 같은 기준으로 비교하면 하락폭이 커 보여요."),
        "",
        "«formula»",
        "",
        "- 어제 17시 이후 «ok_new_label» 상태로 끝난 건: «new_count»건",
        "- 원인은 아직 확인 전이에요. 실제 실패인지 수집 오류인지 몰라요.",
    )
    code = _Body(kw)(*(_KOTLIN_HANDLER if c["lang"] == "kotlin" else _PY_HANDLER))
    return [
        _art("design", "«feature» — 배포 계획", "lead", "배포됨", "어제 17:00 배포한 «feature»의 변경 사항·수용 기준·롤백 기준 (팀장 정리).", design),
        _art("result", "«metric» 배포 전후 비교", "team", "확인 중", "배포 전 7일 평균과 어제·오늘의 «metric» (운영 대시보드).", result),
        _art("code", "«peer_artifact» — «feature»", "peer", "배포됨", "«upstream» 응답 처리와 확인 재시도 (이도현, 어제 배포).", code, c["lang"]),
    ]


# ------------------------------------------------------------------------------------------------------ 디자인 (design)

DESIGN = {
    "fintech": {"steps": ("사업자 정보 입력", "정산 계좌 연결", "알림 설정"), "perm_label": "알림 권한", "perm_key": "notifications", "starts": 2140},
    "health": {"steps": ("복용 약 등록", "복약 시간 설정", "보호자 연결(선택)"), "perm_label": "알림 권한", "perm_key": "notifications", "starts": 3860},
    "commerce": {"steps": ("배송지 설정", "관심 카테고리 선택", "첫 주문 혜택 확인"), "perm_label": "위치 권한", "perm_key": "location", "starts": 6920},
    "saas": {"steps": ("워크스페이스 만들기", "팀원 초대", "첫 자동화 템플릿 선택"), "perm_label": "브라우저 알림 권한", "perm_key": "notifications", "starts": 1180},
    "mobility": {"steps": ("본인·운전면허 인증", "결제 수단 등록", "안전 수칙 확인"), "perm_label": "위치 권한", "perm_key": "location", "starts": 4820},
}


def _design(c: dict, axis: str) -> list[dict]:
    """V4: the peer's implementation is due today and the candidate reviews it against the spec."""
    n0 = c["starts"]
    n1 = round(n0 * 0.81)
    n2 = round(n1 * 0.86)
    n3e = n2 + 44  # planted: more people enter step 3 than finished step 2
    n3 = round(n3e * 0.878)
    overall = n3 / n0
    kw = {**c, **{f"s{i}": s for i, s in enumerate(c["steps"])}, "n0": _n(n0), "n1": _n(n1), "n2": _n(n2), "n3e": _n(n3e),
          "n3": _n(n3), "r1": _p(n1, n0), "r2": _p(n2, n1), "r3": _p(n3, n3e), "overall": _r(overall), "stale": _r(overall - 0.029),
          "after": _r(c["base"] + 0.01), "formula": _tex("온보딩 완료율", "3단계 완료", "1단계 진입")}
    design = _Body(kw)(
        "# «artifact» 명세 (v3)",
        "> «company» · «service» · 시안: 디자인(지원자) · 구현: 이도현 · 리뷰 마감: 오늘 18:00",
        "",
        "## 흐름 (3단계)",
        "1. «s0»",
        "2. «s1»",
        "3. «s2»",
        "- 진행 표시: 상단 '1/3' 텍스트 + 진행 바, 마지막 단계에서 100%",
        "",
        "## 컴포넌트 기준",
        "- 기본 버튼: 높이 48px, 좌우 여백 20px, 모서리 12px",
        "- 터치 영역: 최소 44×44px",
        "- 본문 16px, 보조 문구 14px, 글자 대비 4.5:1 이상",
        ("- «perm_label» 요청: 적절한 시점에 노출",
         "'적절한 시점'이 언제인지 없어서 구현(a3)은 첫 화면에 들어오자마자 요청해요. 어느 단계에서, 왜 필요한지 보여 주고 요청할지 정해야 해요."),
        "",
        "## 수용 기준",
        ("1. 온보딩 완료율 70% 이상 (현재 «stale»)", "현재 완료율(«stale»)이 퍼널 결과(a2)의 전체 완료율(«overall»)과 달라요. 어느 기간 기준인지 맞춰야 해요."),
        "2. 모든 문구는 해요체, 버튼 문구는 동사로 끝낸다",
        "3. 스크린리더가 단계 이름과 버튼 이름을 읽을 수 있다",
        "",
        "## 리뷰 체크리스트",
        "- [ ] 버튼·터치 영역 규격",
        "- [ ] 진행 표시",
        "- [ ] 문구·접근성 라벨",
    )
    result = _Body(kw)(
        "# 온보딩 퍼널 (지난 2주)",
        "> 출처: 제품 분석 도구 · 정리: 한서윤 팀장 · 현재 운영 중인 v2 화면 기준",
        "",
        "| 단계 | 진입 | 완료 | 단계 완료율 |",
        "|---|---:|---:|---:|",
        "| 1. «s0» | «n0» | «n1» | «r1» |",
        "| 2. «s1» | «n1» | «n2» | «r2» |",
        ("| 3. «s2» | «n3e» | «n3» | «r3» |", "2단계 완료(«n2»)보다 3단계 진입(«n3e»)이 많아요. 재진입이 중복으로 세졌는지 확인해야 하고, 전체 완료율도 같이 흔들려요."),
        "| 전체 | «n0» | «n3» | «overall» |",
        "",
        "«formula»",
        "",
        "- 온보딩을 마친 사용자의 첫 주 «metric»: «after»",
        "- v3 시안은 오늘 구현 리뷰를 거쳐 다음 주 배포 예정이에요.",
    )
    code = _Body(kw)(
        "// «peer_artifact» — 오늘 마감 · 담당: 이도현 · 리뷰: 지원자",
        'import { useEffect, useState } from "react";',
        'import { requestPermission } from "../native/permissions";',
        "",
        'const STEPS = ["«s0»", "«s1»", "«s2»"] as const;',
        "",
        "export const styles = {",
        ('  primaryButton: { height: 40, padding: "0 20px", borderRadius: 12, fontSize: 16 },',
         "기본 버튼 높이가 40px이에요. 시안 명세(a1)는 48px이고 터치 영역도 최소 44px이에요."),
        '  caption: { fontSize: 14, color: "#5F6368" },',
        '  skip: { minHeight: 44, fontSize: 14, color: "#5F6368", background: "none", border: 0 },',
        "};",
        "",
        "export function Onboarding({ onDone }: { onDone: () => void }) {",
        "  const [step, setStep] = useState(0);",
        "",
        "  useEffect(() => {",
        '    requestPermission("«perm_key»");',
        "  }, []);",
        "",
        ("  const progress = Math.round((step / STEPS.length) * 100);", "step이 0부터라 진행률이 0% → 33% → 67%로 끝나요. 명세(a1)는 마지막 단계에서 100%예요."),
        "  const next = () => (step < STEPS.length - 1 ? setStep(step + 1) : onDone());",
        "",
        "  return (",
        '    <section aria-label="온보딩">',
        "      <p style={styles.caption}>{step + 1}/{STEPS.length}</p>",
        '      <progress value={progress} max={100} aria-label="진행률" />',
        "      <h1>{STEPS[step]}</h1>",
        "      <button style={styles.primaryButton} onClick={next}>다음</button>",
        '      <button type="button" style={styles.skip} onClick={onDone}>건너뛰기</button>',
        "    </section>",
        "  );",
        "}",
    )
    return [
        _art("design", "«artifact» 명세 (v3)", "team", "확정", "3단계 온보딩 흐름, 컴포넌트 기준, 수용 기준, 리뷰 체크리스트.", design),
        _art("result", "온보딩 퍼널 — 지난 2주", "lead", "공유됨", "현재 v2 온보딩의 단계별 진입·완료와 전체 완료율 (팀장 정리).", result),
        _art("code", "«peer_artifact» (오늘 마감)", "peer", "리뷰 요청", "온보딩 3단계 화면 컴포넌트와 스타일 (이도현, 오늘 마감).", code, "typescript"),
    ]


# --------------------------------------------------------------------------------------------------- 영업·CS (sales)

SALES = {
    "fintech": {"client": "한빛상인회", "client_desc": "전통시장 상인회 · 가맹점 120곳 · 카드 매출 정산을 주 1회 수기로 확인",
                "need": "정산 지연 문의 창구 일원화, 단체 요금", "offer0": "단체 요금제 (수수료 0.1%p 인하, 12개월)",
                "offer1": "상인회 전담 CS 채널 (이도현 담당)", "offer2": "가맹점별 월간 정산 리포트", "vague": "도입 교육은 필요하면 지원",
                "pilot": "파일럿 가맹점 20곳", "group_label": "가맹점",
                "sql": {"gtable": "merchants", "name_col": "merchant_name", "gfk": "merchant_id", "partner_col": "partner_group",
                        "partner": "HANBIT", "table": "settlement_requests", "time_col": "requested_at", "ok": "COMPLETED"}},
    "health": {"client": "바른내과의원 네트워크", "client_desc": "내과 의원 18곳 · 고혈압·당뇨 환자 약 2,400명",
               "need": "재진 사이 복약 관리, 의원별 수신 현황 리포트", "offer0": "의원 단위 복약 알림 현황 대시보드",
               "offer1": "환자 안내문·가입 코드 제공", "offer2": "의원별 월간 수신율 리포트", "vague": "의원 직원 교육은 필요하면 지원",
               "pilot": "파일럿 의원 5곳", "group_label": "의원",
               "sql": {"gtable": "clinics", "name_col": "clinic_name", "gfk": "clinic_id", "partner_col": "network",
                       "partner": "BAREUN", "table": "dose_reminders", "time_col": "scheduled_at", "ok": "DELIVERED"}},
    "mobility": {"client": "한결대학교", "client_desc": "캠퍼스 3곳 · 재학생 1.8만 명 · 셔틀버스 대체 이동 수요",
                 "need": "강의 시간대 대여 실패 감소, 캠퍼스 전용 주차 구역", "offer0": "캠퍼스 전용 킥보드 80대·주차 구역 12곳",
                 "offer1": "학생증 인증 할인 20%", "offer2": "월간 이용·안전 리포트", "vague": "안전 교육은 필요하면 지원",
                 "pilot": "파일럿 캠퍼스 1곳", "group_label": "주차 구역",
                 "sql": {"gtable": "zones", "name_col": "zone_name", "gfk": "zone_id", "partner_col": "partner",
                         "partner": "HANGYEOL_UNIV", "table": "rental_attempts", "time_col": "attempted_at", "ok": "UNLOCKED"}},
    "commerce": {"client": "그린팜 산지직송 협동조합", "client_desc": "농가 46곳 · 제철 채소·과일 산지 직송",
                 "need": "신규 판로, 신선도 클레임 처리", "offer0": "입점 수수료 첫 3개월 50% 감면", "offer1": "공동 기획전 월 2회",
                 "scale": 1.5, "lift": 0.028, "second": ("신선도 클레임(건)", "31", "18", "−13건"),
                 "won": {"parent": "checkout_sessions", "time_col": "started_at", "child": "cart_items", "child_fk": "checkout_id",
                         "child_filter": "c.supplier_code = 'GREENFARM'", "ok": "PAID", "target_desc": "그린팜 상품이 장바구니에 담긴 결제",
                         "fan_issue": "장바구니에 그린팜 상품이 여러 개면 같은 결제가 여러 번 세져요(JOIN 중복). EXISTS나 COUNT(DISTINCT x.id)로 세야 해요."}},
    "saas": {"client": "대명물류", "client_desc": "직원 340명 · 배차·경비 결재를 메신저로 처리",
             "need": "결재 누락·지연 감소, 감사 대응 기록", "offer0": "결재·배차 자동화 템플릿 6종", "offer1": "도입 4주 전담 지원 (CS 이도현)",
             "scale": 0.9, "lift": 0.005, "second": ("결재 누락(건)", "46", "9", "−37건"),
             "won": {"parent": "workflow_runs", "time_col": "started_at", "child": "run_steps", "child_fk": "run_id",
                     "child_filter": "c.connector IN ('ERP', 'TMS') AND x.workspace_id = 'ws_daemyung'", "ok": "SUCCEEDED",
                     "target_desc": "대명물류 워크스페이스의 ERP·배차(TMS) 연동 실행",
                     "fan_issue": "실행 하나에 연동 단계가 여러 개면 같은 실행이 여러 번 세져요(JOIN 중복). EXISTS나 COUNT(DISTINCT x.id)로 세야 해요."}},
}


def _sales_anomaly(c: dict) -> list[dict]:
    """V3: preparing the proposal, the candidate sees the metric fall after yesterday's deploy."""
    vol, base = c["vol"], c["base"]
    avg_n = round(vol * base)
    rows = [("2일 전", round(vol * 1.012), base + 0.001, 35), ("어제", round(vol * 1.026), base - 0.048, 57)]
    t_den = round(vol * 0.38)
    t_num = round(t_den * (base - 0.121))
    kw = {**c, **c["sql"], "avg_d": _n(vol), "avg_n": _n(avg_n), "base_s": _p(avg_n, vol), "t_den": _n(t_den), "t_num": _n(t_num),
          "t_r": _p(t_num, t_den), "formula": _tex(c["metric"], c["num_count"], c["den_count"])}
    design = _Body(kw)(
        "# «artifact»: «client» (구성안 v2)",
        "> «company» · «service» · 제안 발표: 목 14:00 · 작성: 영업(지원자) · 검토: 한서윤 팀장 · 응대 계획: 이도현",
        "",
        "## 1. 고객 현황",
        "- «client_desc»",
        "- 요구: «need»",
        "",
        "## 2. 제안 범위",
        "- 포함: «offer0»",
        "- 포함: «offer1»",
        "- 포함: «offer2»",
        ("- 협의: «vague»", "'필요하면'만 있어서 교육 횟수·대상·비용이 없어요. 고객사는 무상·무제한으로 읽을 수 있어요."),
        "",
        "## 3. 근거 지표",
        ("- «metric» «base_s» (지난 4주 평균, 전체 고객 기준)",
         "근거 지표가 지난 4주 평균만 적혀 있어요. 어제 배포 이후 «metric»이 떨어진 상태(a2)라 발표 전에 기간과 수치를 다시 확인해야 해요."),
        "- 문의 첫 응답 평균 1시간 40분 (CS 운영 기준)",
        "",
        "## 4. 일정",
        "| 단계 | 담당 | 시점 |",
        "|---|---|---|",
        "| 구성안 확정 | 영업 | 수 |",
        "| 제안 발표 | 영업·팀장 | 목 14:00 |",
        "| «pilot» | 영업·CS | 다음 주 |",
    )
    result = _Body(kw)(
        "# «metric» 일별 현황 — 제안서 근거 자료",
        "> 출처: 운영 대시보드(전체 고객) · 어제 17:00 앱 배포 · 오늘은 10:00까지 · 정리: 지원자",
        "",
        "| 일자 | «den_count» | «num_count» | «metric» | 고객 문의 |",
        "|---|---:|---:|---:|---:|",
        "| 지난 4주 일평균 | «avg_d» | «avg_n» | «base_s» | 38 |",
        *[f"| {label} | {_n(d)} | {_n(round(d * r))} | {_p(round(d * r), d)} | {q} |" for label, d, r, q in rows],
        "| 오늘(10시까지) | «t_den» | «t_num» | «t_r» | 22 |",
        "",
        "«formula»",
        "",
        ("- 어제 고객 문의 57건으로 평소(38건)의 2배예요.", "57건은 평소 38건의 1.5배예요. 고객사 발표 자료에 들어가면 과장된 숫자가 돼요."),
        "- 하락이 실제 실패인지 집계 문제인지는 아직 몰라요. 이도현님이 문의 내용을 확인하고 있어요.",
    )
    code = _Body(kw)(
        "-- «peer_artifact» 첨부: «client» «group_label»별 «metric»·문의 현황",
        "-- 작성: 이도현 · 기간: 최근 7일(오늘 제외) · 대상: «client» 소속 «group_label» 전체",
        "SELECT",
        "  g.«name_col»,",
        "  COUNT(x.id) AS total_cnt,",
        "  COUNT(x.id) FILTER (WHERE x.status = '«ok»') AS ok_cnt,",
        ("  COUNT(x.id) FILTER (WHERE x.status = '«ok»') / COUNT(x.id) AS ok_rate,",
         "정수끼리 나눠서 ok_rate가 0 아니면 1로만 나와요. 100.0 *을 곱하거나 numeric으로 바꿔야 해요."),
        "  (SELECT COUNT(*) FROM cs_tickets t",
        "    WHERE t.«gfk» = g.id",
        "      AND t.created_at >= CURRENT_DATE - 7",
        "      AND t.created_at < CURRENT_DATE) AS inquiries",
        "FROM «gtable» g",
        "JOIN «table» x ON x.«gfk» = g.id",
        "WHERE g.«partner_col» = '«partner»'",
        "  AND x.«time_col» >= CURRENT_DATE - 7",
        "  AND x.«time_col» < CURRENT_DATE",
        "GROUP BY g.id, g.«name_col»",
        ("HAVING COUNT(x.id) >= 20", "머리말은 '«group_label» 전체'인데 7일 20건 미만인 곳을 조용히 빼요. 문의가 몰린 작은 곳이 표에서 사라질 수 있어요."),
        "ORDER BY ok_rate ASC;",
    )
    return [
        _art("design", "«artifact» — «client»", "team", "작성 중", "목요일 발표할 «client» 제안 범위·근거 지표·일정 (구성안 v2).", design),
        _art("result", "«metric» 일별 현황 (제안 근거)", "team", "확인 중", "제안서에 인용할 «metric»과 고객 문의의 최근 추이.", result),
        _art("code", "«peer_artifact» 첨부 쿼리", "peer", "초안", "«client» «group_label»별 «metric»·문의 집계 쿼리 (이도현).", code, "sql"),
    ]


def _sales_won(c: dict) -> list[dict]:
    """V1: the deal closed; tomorrow someone presents it and leads the follow-up."""
    vol, base = c["vol"], c["base"]
    bd, ad = round(vol * c["scale"] * 4), round(vol * c["scale"] * 4 * 1.07)
    bn, an = round(bd * base), round(ad * (base + c["lift"]))
    s_label, s0, s1, s2 = c["second"]
    kw = {**c, **c["won"], "bd": _n(bd), "ad": _n(ad), "bn": _n(bn), "an": _n(an), "br": _p(bn, bd), "ar": _p(an, ad),
          "diff": f"{_pp(_p(bn, bd), _p(an, ad)):+.1f}%p", "after_wrong": _r(an / ad + 0.006),
          "s_label": s_label, "s0": s0, "s1": s1, "s2": s2, "formula": _tex(c["metric"], c["num_count"], c["den_count"])}
    design = _Body(kw)(
        "# «artifact»: «client» (수주 완료)",
        "> «company» · «service» · 계약: 지난주 금 · 작성: 영업(지원자) · 발표: 내일 전사 회의",
        "",
        "## 1. 고객 현황",
        "- «client_desc»",
        "- 요구: «need»",
        "",
        "## 2. 제안 내용",
        "- «offer0»",
        "- «offer1»",
        ("- 성공 기준: 파일럿 4주 동안 «metric» 개선", "얼마나 오르면 성공인지 기준이 없어요. 후속 계약 조건을 정할 때 다툼이 생길 수 있어요."),
        "",
        "## 3. 파일럿 성과 요약",
        ("- «metric» «br» → «after_wrong»", "제안서의 파일럿 후 «metric»(«after_wrong»)이 성과 표(a2)의 «ar»와 달라요."),
        "- 문의 첫 응답 1시간 이내 유지",
        "",
        "## 4. 기여",
        "- 고객 발굴·제안 아이디어·첫 미팅: 영업(지원자)",
        "- 파일럿 운영·«peer_artifact»·주간 리포트 (마지막 2주): 이도현",
        "- 계약 조건 협상 동행: 한서윤 팀장",
    )
    result = _Body(kw)(
        "# «client» 파일럿 성과 (4주)",
        "> 정리: 한서윤 팀장 · 집계: 이도현 쿼리(a3) · 비교: 도입 전 4주",
        "",
        "| 지표 | 도입 전 4주 | 파일럿 4주 | 변화 |",
        "|---|---:|---:|---:|",
        "| «den_count» | «bd» | «ad» | – |",
        "| «num_count» | «bn» | «an» | – |",
        "| «metric» | «br» | «ar» | «diff» |",
        ("| 문의 첫 응답(분) | 72 | 48 | −40% |", "72분에서 48분이면 33% 단축인데 40%로 적혀 있어요."),
        "| «s_label» | «s0» | «s1» | «s2» |",
        "",
        "«formula»",
        "",
        "- 내일 전사 회의 발표에는 «metric» 변화와 응답 시간 단축을 핵심 성과로 넣어요.",
    )
    code = _Body(kw)(
        "-- «peer_artifact» 첨부: «client» 파일럿 성과 집계 (주간 리포트·발표 자료용)",
        "-- 작성: 이도현 · 파일럿 4주 vs 도입 전 4주 · 대상: «target_desc»",
        "WITH base AS (",
        "  SELECT x.id,",
        "         x.status,",
        "         CASE WHEN x.«time_col» >= CURRENT_DATE - 28 THEN '파일럿' ELSE '도입 전' END AS period",
        "  FROM «parent» x",
        ("  JOIN «child» c ON c.«child_fk» = x.id", "«fan_issue»"),
        "  WHERE «child_filter»",
        "    AND x.«time_col» >= CURRENT_DATE - 56",
        "    AND x.«time_col» < CURRENT_DATE",
        ")",
        "SELECT period,",
        "       COUNT(*) AS total_cnt,",
        "       COUNT(*) FILTER (WHERE status = '«ok»') AS ok_cnt,",
        "       ROUND(100.0 * COUNT(*) FILTER (WHERE status = '«ok»') / COUNT(*), 1) AS rate_pct",
        "FROM base",
        "GROUP BY period",
        "ORDER BY period DESC;",
    )
    return [
        _art("design", "«artifact» — «client» (수주)", "team", "수주 완료", "지난주 계약한 «client» 제안 내용·파일럿 성과·기여 정리.", design),
        _art("result", "«client» 파일럿 성과 (4주)", "lead", "공유됨", "도입 전 4주 대비 파일럿 4주 성과 (팀장 정리, 내일 발표 자료).", result),
        _art("code", "«peer_artifact» 첨부 — 성과 집계 쿼리", "peer", "공유됨", "파일럿 전후 «metric» 집계 쿼리 (이도현).", code, "sql"),
    ]


def _sales(c: dict, axis: str) -> list[dict]:
    return _variant(axis, c, [("V3", "sql", _sales_anomaly), ("V1", "won", _sales_won)])(c)


# --------------------------------------------------------------------------------------------- 데이터·운영 (data)

DATA = {
    "fintech": {"partial_def": "완료에 부분 정산 포함 여부: 추후 결정", "dims": "업종(음식점·소매·서비스), 지역(시·도), 가맹점 규모",
                "sources": "settlement_requests, merchants", "mart": "mart.weekly_settlement", "audience": "경영진·운영팀 전원",
                "review0": "집계 단위 (가맹점 단위 이상)", "review1": "열람 권한 범위", "src": "settlement_requests", "gtable": "merchants",
                "fk": "merchant_id", "time_col": "requested_at", "done_col": "completed_at", "ok": "COMPLETED",
                "dim0": "g.category", "dim1": "g.region", "pii_col": "g.owner_phone", "pii_label": "가맹점 대표자 휴대폰 번호",
                "aux": ("평균 정산 소요(시간)", 26.4, 0.3, "3600", "avg_hours")},
    "health": {"partial_def": "수신에 무음 수신 포함 여부: 추후 결정", "dims": "질환군(고혈압·당뇨·고지혈증), 연령대, 의원",
               "sources": "dose_reminders, patients", "mart": "mart.weekly_reminder", "audience": "경영진·의료지원팀 전원",
               "review0": "집계 단위 (질환군·연령대)", "review1": "열람 권한 범위", "src": "dose_reminders", "gtable": "patients",
               "fk": "patient_id", "time_col": "scheduled_at", "done_col": "delivered_at", "ok": "DELIVERED",
               "dim0": "g.disease_group", "dim1": "g.age_band", "pii_col": "g.birth_date", "pii_label": "환자 생년월일",
               "aux": ("평균 수신 지연(분)", 4.8, 0.1, "60", "avg_minutes")},
    "saas": {"partial_def": "성공에 재시도 후 성공 포함 여부: 추후 결정", "dims": "요금제, 고객사 업종, 템플릿 종류",
             "sources": "workflow_runs, workspaces", "mart": "mart.weekly_runs", "audience": "경영진·고객성공팀 전원",
             "review0": "고객사별 데이터 분리 (테넌트 단위)", "review1": "열람 권한 범위", "src": "workflow_runs", "gtable": "workspaces",
             "fk": "workspace_id", "time_col": "started_at", "done_col": "finished_at", "ok": "SUCCEEDED",
             "dim0": "g.plan", "dim1": "g.industry", "pii_col": "g.admin_phone", "pii_label": "고객사 관리자 연락처",
             "aux": ("평균 실행 시간(초)", 12.6, 0.2, "1", "avg_seconds")},
    "mobility": {"partial_def": "성공에 재시도 후 잠금 해제 포함 여부: 추후 결정", "dims": "권역(대학가·역세권·주거지), 시간대, 기기 모델",
                 "sources": "rental_attempts, devices", "mart": "mart.weekly_rental", "audience": "경영진·현장운영팀 전원",
                 "review0": "기기 상태·고장 지표 정의", "review1": "열람 권한 범위", "src": "rental_attempts", "gtable": "devices",
                 "fk": "device_id", "time_col": "attempted_at", "done_col": "unlocked_at", "ok": "UNLOCKED",
                 "dim0": "g.zone", "dim1": "g.model", "pii_col": "x.user_geohash8", "pii_label": "이용자 위치(지오해시 8자리, 약 20m)",
                 "aux": ("평균 잠금 해제(초)", 3.4, 0.1, "1", "avg_seconds")},
    "commerce": {"event": "checkout_started", "deploy": "결제 화면 개편 (쿠폰 선택 단계 분리)",
                 "dims": "배송 권역(강남·송파·분당), 앱·웹, 신규·기존 고객", "mart": "mart.daily_checkout"},
}


def _data_review(c: dict) -> list[dict]:
    """V2: the dashboard opens Friday, the review gate slipped to next Tuesday."""
    vol, base = c["vol"], c["base"]
    aux_label, aux0, aux_step, aux_div, aux_col = c["aux"]
    weeks = [("4주 전", 0.98, -0.001), ("3주 전", 1.0, 0.001), ("2주 전", 1.01, -0.002), ("지난주", 1.03, 0.002)]
    rows = []
    for i, (label, f, dr) in enumerate(weeks):
        d = round(vol * 7 * f)
        n = round(d * (base + dr))
        rows.append((label, d, n, f"{aux0 - aux_step * i:.1f}"))
    cd = round(vol * 3 * 1.02)
    cn = round(cd * (base + 0.004))
    w2 = rows[2]
    kw = {**c, "aux_label": aux_label, "aux_div": "" if aux_div == "1" else f" / {aux_div}", "aux_col": aux_col, "cd": _n(cd), "cn": _n(cn), "cr": _p(cn, cd),
          "c_aux": f"{aux0 - aux_step * 4:.1f}", "w2d": _n(w2[1]), "w2n": _n(w2[2]), "w2r": _p(w2[2], w2[1]),
          "w2_shown": _r(w2[2] / w2[1] - 0.012), "formula": _tex(c["metric"], c["num_count"], c["den_count"])}
    table = [f"| {label} | {_n(d)} | {_n(n)} | {_p(n, d)} | {aux} |" for label, d, n, aux in rows]
    table[2] = (f"| 2주 전 | «w2d» | «w2n» | «w2_shown» | {rows[2][3]} |", "2주 전은 «w2n»/«w2d» = «w2r»인데 «w2_shown»로 적혀 있어요.")
    design = _Body(kw)(
        "# «artifact» 정의서 (v0.9)",
        "> «company» · «service» · 공개: 금 10:00 경영 회의 · 작성: 데이터 분석(지원자) · 파이프라인: 이도현",
        "",
        "## 1. 핵심 지표",
        "- «metric» = «num_count» ÷ «den_count» (발생일 기준, KST)",
        ("- «partial_def»", "분자 정의가 '추후 결정'으로 남아 있어요. 금요일 공개 전에 정하지 않으면 주차별 수치를 다시 뽑아야 해요."),
        "- 보조 지표: «aux_label», 고객 문의 건수",
        "",
        "## 2. 차원",
        "- «dims»",
        "",
        "## 3. 데이터 출처·접근",
        "- 원천: «sources» (운영 DB 복제본)",
        "- 마트: «mart» (이도현 파이프라인, 매일 06:00 적재)",
        "- 열람: «audience»",
        "",
        "## 4. «gate» 요청 항목",
        "- «review0»",
        ("- «review1»", "마트 적재 쿼리(a3)에 «pii_label» 컬럼이 그대로 들어가는데 검토 요청 항목에 없어요."),
        "",
        "## 5. 일정",
        "| 단계 | 담당 | 시점 |",
        "|---|---|---|",
        "| 지표 정의 확정 | 분석 | 화 |",
        "| 파이프라인 적재 | 이도현 | 수 |",
        "| 대시보드 공개 | 분석 | 금 10:00 |",
        "| «gate» | 검토팀 | 다음 주 화 (일정 밀림) |",
    )
    result = _Body(kw)(
        "# «metric» 주간 추이 (대시보드 초안)",
        "> 출처: «mart» · 주 시작: 월요일 · 정리: 지원자",
        "",
        "| 주차 | «den_count» | «num_count» | «metric» | «aux_label» |",
        "|---|---:|---:|---:|---:|",
        *table,
        "| 이번 주(월–수) | «cd» | «cn» | «cr» | «c_aux» |",
        "",
        "«formula»",
        "",
        ("- 이번 주 «metric»이 가장 높아 개선 추세로 보여요.",
         "이번 주는 월–수 3일치 부분 집계라 처리 중인 건이 남아 있어요. 7일치 주와 같은 기준으로 '가장 높다'고 보기 어려워요."),
    )
    code = _Body(kw)(
        "-- «peer_artifact»: «mart» 적재 (매일 06:00) · 작성: 이도현",
        "-- 원천: «sources» (운영 DB 복제본)",
        "-- 주 기준: 월요일 00시(KST) · 기간: 이번 주 포함 최근 5주",
        "DELETE FROM «mart» WHERE week_start >= date_trunc('week', now()) - INTERVAL '4 weeks';",
        "INSERT INTO «mart»",
        "SELECT",
        ("  date_trunc('week', x.«time_col») AS week_start,",
         "머리말은 KST 월요일 기준인데 시간대 변환 없이 date_trunc를 써서 UTC 기준 주로 잘려요. 월요일 0–9시 건이 전 주로 들어가요."),
        "  «dim0»,",
        "  «dim1»,",
        ("  «pii_col»,", "«pii_label» 컬럼을 마트에 그대로 적재해요. 주간 집계에 필요 없는 개인정보이고 «gate» 요청 항목(a1)에도 없어요."),
        "  COUNT(*) AS total_cnt,",
        "  COUNT(*) FILTER (WHERE x.status = '«ok»') AS ok_cnt,",
        "  ROUND(AVG(EXTRACT(EPOCH FROM x.«done_col» - x.«time_col»)«aux_div»), 1) AS «aux_col»",
        "FROM «src» x",
        "JOIN «gtable» g ON g.id = x.«fk»",
        "WHERE x.«time_col» >= date_trunc('week', now()) - INTERVAL '4 weeks'",
        "GROUP BY 1, 2, 3, 4;",
    )
    return [
        _art("design", "«artifact» 정의서 (v0.9)", "team", "검토 대기", "금요일 공개할 «metric» 대시보드의 지표 정의·차원·접근·«gate» 요청 항목.", design),
        _art("result", "«metric» 주간 추이 (초안)", "team", "초안", "최근 5주 «metric»과 «aux_label» (대시보드 초안).", result),
        _art("code", "«peer_artifact» — 마트 적재 쿼리", "peer", "리뷰 요청", "«mart» 주간 적재 SQL (이도현, 매일 06:00).", code, "sql"),
    ]


def _data_anomaly(c: dict) -> list[dict]:
    """V3: the dashboard shows the metric falling since yesterday's deploy; it may be a collection error."""
    vol, base = c["vol"], c["base"]
    rows = [("3일 전", round(vol * 0.997), round(vol * 0.997 * (base + 0.001)), ""),
            ("2일 전", round(vol * 1.008), round(vol * 1.008 * base), ""),
            ("어제", round(vol * 1.387), round(vol * 1.01 * base), "17:00 앱 배포")]
    t_den, t_num = round(vol * 0.531), round(vol * 0.36 * base)
    usual = (rows[0][1] + rows[1][1]) / 2
    kw = {**c, "t_den": _n(t_den), "t_num": _n(t_num), "t_r": _p(t_num, t_den), "jump": f"{100 * (rows[2][1] / usual - 1):.0f}%",
          "d1n": _n(rows[2][2]), "d2n": _n(rows[1][2]), "formula": _tex(c["metric"], c["num_count"], c["den_count"])}
    design = _Body(kw)(
        "# «artifact» 정의서 (v1.2)",
        "> «company» · «service» · 매일 09:00 갱신 · 작성: 데이터 분석(지원자) · 파이프라인: 이도현",
        "",
        "## 1. 핵심 지표",
        "- «metric» = «num_count» ÷ «den_count» (일 단위, KST)",
        ("- 결제 시작: 결제 화면 진입 이벤트 `«event»` 기준",
         "'화면 진입' 기준이라 같은 결제에서 화면을 다시 열 때마다 세는지, 결제 건당 한 번인지 정해져 있지 않아요."),
        "- 결제 완료: 주문 DB `orders.status = 'PAID'`",
        "- 보조 지표: 장바구니 이탈률, 평균 결제 금액",
        "",
        "## 2. 차원",
        "- «dims»",
        "",
        "## 3. 최근 변경",
        "- 어제 17:00 앱 배포: «deploy»",
        "- 이벤트 명세 변경 여부: 확인 전",
        "",
        "## 4. 이상 징후 공유 기준",
        ("- 전환율이 전날보다 크게 떨어지면 공유한다", "'크게'가 몇 %p인지, 확인 전에도 알리는지, 누가 어느 채널에 알리는지가 없어요."),
        "- 공유 채널: #data-alerts",
    )
    result = _Body(kw)(
        "# «metric» 일별 (대시보드 스냅숏)",
        "> 출처: «mart» · 어제 17:00 앱 배포 · 오늘은 10:00까지 · 정리: 지원자",
        "",
        "| 일자 | «den_count» | «num_count» | «metric» | 비고 |",
        "|---|---:|---:|---:|---|",
        *[f"| {label} | {_n(d)} | {_n(n)} | {_p(n, d)} | {note} |" for label, d, n, note in rows],
        "| 오늘(10시까지) | «t_den» | «t_num» | «t_r» | 집계 중 |",
        "",
        "«formula»",
        "",
        "- 어제 «den_count»가 평소보다 «jump» 많았어요. 배포 이후 시간대에 몰려 있어요.",
        ("- 결제 완료가 줄어 매출 영향이 커 보여요.",
         "결제 완료 수(어제 «d1n»)는 평소(«d2n») 수준이에요. 결제 시작만 늘어난 거라 매출 영향보다 집계 문제를 먼저 의심해야 해요."),
    )
    code = _Body(kw)(
        "-- «peer_artifact»: «mart» 적재 (매시 정각) · 작성: 이도현",
        "-- 결제 시작 = 앱 이벤트 «event» · 결제 완료 = 주문 DB status 'PAID'",
        "WITH started AS (",
        "  SELECT (e.event_time AT TIME ZONE 'Asia/Seoul')::date AS d,",
        ("         COUNT(*) AS started",
         "결제 시작을 이벤트 건수로 세요. 개편된 화면에서 쿠폰 단계를 오갈 때마다 이벤트가 다시 찍히면 결제 시작이 부풀어요. checkout_id로 중복을 빼야 해요."),
        "  FROM app_events e",
        "  WHERE e.name = '«event»'",
        "    AND e.event_time >= CURRENT_DATE - 7",
        "  GROUP BY 1",
        "), paid AS (",
        "  SELECT (o.paid_at AT TIME ZONE 'Asia/Seoul')::date AS d,",
        "         COUNT(*) AS paid",
        "  FROM orders o",
        "  WHERE o.status = 'PAID'",
        "    AND o.paid_at >= CURRENT_DATE - 7",
        "  GROUP BY 1",
        ")",
        "INSERT INTO «mart» (d, started, paid, conversion_pct)",
        "SELECT s.d, s.started, p.paid, ROUND(100.0 * p.paid / s.started, 1)",
        "FROM started s",
        "JOIN paid p USING (d);",
    )
    return [
        _art("design", "«artifact» 정의서 (v1.2)", "team", "운영 중", "«metric» 대시보드의 지표 정의·차원·최근 변경·이상 징후 공유 기준.", design),
        _art("result", "«metric» 일별 스냅숏", "team", "확인 중", "어제 배포 전후 «metric» 일별 수치 (대시보드 스냅숏).", result),
        _art("code", "«peer_artifact» — 일별 적재 쿼리", "peer", "운영 중", "«mart» 매시 적재 SQL (이도현).", code, "sql"),
    ]


def _data(c: dict, axis: str) -> list[dict]:
    return _variant(axis, c, [("V2", "pii_col", _data_review), ("V3", "event", _data_anomaly)])(c)


JOB_BUILDERS = {"pm": (PM, _pm), "dev": (DEV, _dev), "design": (DESIGN, _design), "sales": (SALES, _sales), "data": (DATA, _data)}


def _dilemma(scn: dict) -> list[dict]:
    job, industry = scn["job"], scn["industry"]
    data, build = JOB_BUILDERS[job]
    ctx = {**JOBS[job], **INDUSTRIES[industry], **DOMAIN[industry], **data[industry]}
    return build(ctx, scn["axis"])


# -------------------------------------------------------------------------------------- 카테고리 시나리오 (모아런)

def _delay() -> list[dict]:
    design = _Body({})(
        "# 모임 리마인드 알림 기획 (작성 중 · 70%)",
        "> 모아런 · 금요일 베타 (대외 공지 완료) · 기획: 지원자 · 알림 서버: 이도현 · 승인: 한서윤 팀장",
        "",
        "## 목표",
        "- 첫 모임 참여자의 두 번째 모임 참여율(재참여율) 22% → 27%",
        "",
        "## 화면 흐름 (완료)",
        "1. 모임 상세 > '리마인드 받기' 토글 (기본 켜짐)",
        "2. 모임 하루 전 20:00, 시작 2시간 전에 알림",
        "3. 알림을 누르면 모임 상세로 이동, '참여 확정' 버튼 노출",
        "",
        "## 알림 문구 (초안)",
        '- 하루 전: "내일 {모임명} 같이 뛰어요! 물이랑 편한 운동화 챙겨 주세요"',
        '- 2시간 전: "{시작 시각}에 출발해요. 모임 장소를 한 번 더 확인해 주세요"',
        "",
        "## 발송 조건 (오늘 확정 필요)",
        "- 대상: 참여 확정자 (대기자 제외)",
        ("- 방해 금지 시간에는 보내지 않음",
         "방해 금지 시간이 몇 시부터 몇 시까지인지 없어요. 아침 7시 모임이면 2시간 전 알림(05:00)이 빠질 수 있어서 발송 조건 확정 전에 정해야 해요."),
        "- 푸시 실패 시: 미정",
        "",
        "## 범위",
        "- 포함: 앱 푸시, 앱 내 배너",
        "- 제외: 문자·카카오 알림톡",
        "",
        "## 일정",
        "| 항목 | 담당 | 상태 |",
        "|---|---|---|",
        "| 화면 흐름 | 기획 | 완료 |",
        "| 알림 문구·발송 조건 | 기획 | 진행 중 |",
        "| 알림 서버(API) | 이도현 | 진행 중 |",
        "| QA | 팀 | 목 |",
        "| 베타 | 팀 | 금 (공지됨) |",
    )
    result = _Body({"formula": _tex("진척률", "완료 항목", "계획 항목")})(
        "# 베타 준비 현황 (수요일 기준)",
        "> 정리: 한서윤 팀장 · 금요일 베타 공지 완료",
        "",
        "| 항목 | 계획 | 완료 | 진척률 |",
        "|---|---:|---:|---:|",
        "| 기획 (화면·문구·조건) | 10 | 7 | 70% |",
        ("| 알림 서버 API | 8 | 4 | 75% |", "알림 서버 API는 8개 중 4개 완료라 50%인데 75%로 적혀 있어요. 이 숫자 때문에 개발 지연이 가려져 보여요."),
        "| 앱 화면 | 6 | 5 | 83% |",
        "| QA 케이스 | 24 | 0 | 0% |",
        "| 전체 | 48 | 16 | 33% |",
        "",
        "«formula»",
        "",
        "- 지표 기준선: 재참여율 22% (지난달 첫 모임 참여자 1,850명 중 407명)",
        "- 목요일 QA 시작 전까지 남은 항목을 채우면 일정은 맞출 수 있어 보여요.",
    )
    code = _Body({})(
        "// 리마인드 알림 발송 시각 계산 — 알림 서버(작업 중) · 담당: 이도현",
        "package run.moa.reminder",
        "",
        "import java.time.Instant",
        "import java.time.LocalTime",
        "import java.time.ZoneId",
        "import java.time.ZonedDateTime",
        "",
        "data class Meetup(val id: Long, val startsAt: Instant)",
        "",
        "object ReminderSchedule {",
        "    private val QUIET_START = LocalTime.of(22, 0)",
        "    private val QUIET_END = LocalTime.of(8, 0)",
        "",
        "    fun sendTimes(meetup: Meetup): List<ZonedDateTime> {",
        ('        val start = meetup.startsAt.atZone(ZoneId.of("UTC"))',
         "모임 시각을 UTC로 바꿔서 계산해요. 한국 시간 기준 '하루 전 20:00'이 9시간 어긋나요."),
        "        val dayBefore = start.minusDays(1).withHour(20).withMinute(0)",
        "        val twoHoursBefore = start.minusHours(2)",
        "        return listOf(dayBefore, twoHoursBefore).filterNot { isQuiet(it.toLocalTime()) }",
        "    }",
        "",
        "    private fun isQuiet(t: LocalTime): Boolean =",
        ("        t.isAfter(QUIET_START) && t.isBefore(QUIET_END)",
         "자정을 넘는 구간이라 22시 이후이면서 8시 이전인 시각은 없어요. 방해 금지 시간에도 알림이 나가요."),
        "}",
    )
    return [
        _art("design", "모임 리마인드 알림 기획 (70%)", "team", "작성 중", "금요일 베타 기능의 화면 흐름·알림 문구·발송 조건. 발송 조건은 오늘 확정해야 해요.", design),
        _art("result", "베타 준비 현황", "lead", "공유됨", "금요일 베타까지 항목별 진척률과 재참여율 기준선 (팀장 정리).", result),
        _art("code", "알림 발송 시각 계산 (알림 서버)", "peer", "작업 중", "리마인드 알림 발송 시각과 방해 금지 시간 처리 (이도현, 작업 중).", code, "kotlin"),
    ]


def _scope() -> list[dict]:
    design = _Body({})(
        "# 재참여율 개선 기획안 (작성 중 · 80%)",
        "> 모아런 · 오늘 오후 팀장 제출 · 문제 정의·기능 제안: 지원자 · 성공 지표·출시 일정: 이도현",
        "",
        "## 1. 문제 정의",
        ("- 대상: 첫 모임 참여자 (필요하면 휴면 사용자도 포함)",
         "대상이 첫 참여자인지 휴면 사용자인지 둘로 읽혀요. 대상에 따라 문제 정의와 성공 지표가 전부 달라져요."),
        "- 첫 모임 참여자 중 두 번째 모임에도 나오는 비율 22%",
        "- 이탈 이유 1위: 아는 사람이 없어 어색했다 (인터뷰 12명 중 7명)",
        "",
        "## 2. 기능 제안",
        "1. 첫 모임 후 24시간 안에 '같이 뛴 사람' 카드 보내기",
        "2. 다음 모임 추천에서 같이 뛴 사람이 있는 모임을 먼저 보여 주기",
        "3. 두 번째 모임 참여 시 배지",
        "",
        "## 3. 성공 지표 (이도현 작성 중)",
        ("- 재참여율 22% → 30% (출시 후 8주)", "목표 재참여율이 30%인데 이도현님 성공 지표 초안(a2)은 27%예요."),
        "- 보조: 카드 열람률, 추천 클릭률",
        "",
        "## 4. 출시 일정 (초안)",
        "| 단계 | 담당 | 시점 |",
        "|---|---|---|",
        "| 기획안 확정 | 기획 | 오늘 |",
        "| 개발 | 이도현 | 다음 주 |",
        "| 출시 | 팀 | 2주 뒤 |",
    )
    result = _Body({"formula": _tex("재참여율", "두 번째 모임 참여자", "첫 모임 참여자")})(
        "# 성공 지표 초안 — 재참여율 개선",
        "> 작성: 이도현 · 기획안 3장에 들어갈 표 · 대상: 첫 모임 참여자 기준",
        "",
        "| 지표 | 현재 | 목표 (8주) | 측정 |",
        "|---|---:|---:|---|",
        "| 재참여율 (첫 → 두 번째 모임) | 22% | 27% | 앱 로그, 주 단위 |",
        "| '같이 뛴 사람' 카드 열람률 | – | 60% | 카드 노출 대비 |",
        "| 추천 모임 클릭률 | 4.1% | 8% | 추천 노출 대비 |",
        ("| 휴면 사용자 (3개월+) | 9,600명 | – | 가입자 4.2만 명의 32% |", "9,600명은 가입자 4.2만 명의 약 23%인데 32%로 적혀 있어요."),
        "| 월 사용자 | 3만 명 | 3.3만 명 | MAU |",
        "",
        "«formula»",
        "",
        "- 대상이 바뀌면 이 표는 처음부터 다시 써야 해요.",
    )
    code = _Body({})(
        "-- 휴면 대상 추출 (초안) — '3개월 넘게 모임에 안 나온 사용자'",
        "-- 작성: 이도현 · 바뀐 대상 기준으로 지표를 다시 뽑기 위한 쿼리",
        "-- 결과는 성공 지표 표(a2)의 '휴면 사용자' 행에 씀",
        "SELECT",
        "  u.id,",
        "  u.nickname,",
        "  u.joined_at,",
        "  MAX(a.attended_at) AS last_attended,",
        "  COUNT(a.id) AS total_meetups",
        "FROM users u",
        ("JOIN attendances a ON a.user_id = u.id", "INNER JOIN이라 가입만 하고 한 번도 안 나온 사용자는 빠져요. 이들도 대상인지 정해야 해요."),
        "WHERE u.status = 'ACTIVE'",
        "  AND u.deleted_at IS NULL",
        "GROUP BY u.id, u.nickname, u.joined_at",
        ("HAVING MAX(a.attended_at) < CURRENT_DATE - INTERVAL '30 days'", "기준은 3개월인데 30일로 걸러요. 휴면 대상이 훨씬 많이 잡혀요."),
        "ORDER BY last_attended;",
    )
    return [
        _art("design", "재참여율 개선 기획안 (80%)", "team", "작성 중", "오늘 오후 제출할 기획안의 문제 정의·기능 제안·성공 지표·일정 (대상: 첫 모임 참여자).", design),
        _art("result", "성공 지표 초안 (이도현)", "peer", "초안", "기획안 3장에 들어갈 재참여율·보조 지표 표 (이도현 작성 중).", result),
        _art("code", "휴면 대상 추출 쿼리 (초안)", "peer", "초안", "'3개월 넘게 안 나온 사용자'를 뽑는 SQL 초안 (이도현).", code, "sql"),
    ]


def _conflict() -> list[dict]:
    design = _Body({})(
        "# 재참여 핵심 기능 비교안 — 오늘 하나로 정리",
        "> 모아런 · 작성: 기획(지원자) · 안 A: 한서윤 팀장 · 안 B: 이도현",
        "",
        "## 안 A. 다음 모임 자동 추천",
        "- 첫 모임 후 24시간 안에 가까운 일정·비슷한 페이스의 모임 3개 추천",
        ("- 구현: 1.5주 (추천 로직 + 알림, 이도현 추정)", "추천 구현을 1.5주로 적었는데 이도현님 프로토타입 메모(a3)는 3주(추천 2주 + 알림 1주)예요."),
        "- 근거: 소규모 실험에서 추천 노출군 두 번째 모임 참여 30% vs 20%",
        "",
        "## 안 B. 모임 후 참가자 간 간단 채팅",
        "- 모임이 끝나고 72시간 동안 참가자끼리 채팅방 유지",
        "- 구현: 4주 (채팅 서버, 신고·차단 포함)",
        "- 근거: 인터뷰 12명 중 7명이 '아는 사람이 없어 어색했다'",
        "",
        "## 결정 기준",
        ("- 이번 분기 재참여율에 더 도움이 되는 쪽", "'더 도움이 되는 쪽'만 있어서 무엇을 언제 비교할지(지표, 기간, 표본)가 정해져 있지 않아요."),
        "- 이번 분기 개발 여력: 4주 (이도현 1명)",
        "",
        "## 다음 단계",
        "- 오늘 결정, 내일 기능 명세 착수",
    )
    result = _Body({"formula": _tex("재참여율", "두 번째 모임 참여자", "첫 모임 참여자")})(
        "# 근거 자료 요약 — 재참여 기능",
        "> 정리: 한서윤 팀장 · 인터뷰: 이도현 진행 · 로그: 지난달",
        "",
        "| 근거 | 출처 | 수치 |",
        "|---|---|---:|",
        "| 이탈 이유 1위: 아는 사람이 없어 어색했다 | 인터뷰 12명 | 7명 (58%) |",
        ("| 이탈 이유 2위: 다음 모임을 찾기 번거로웠다 | 인터뷰 12명 | 4명 (25%) |", "12명 중 4명이면 33%인데 25%로 적혀 있어요."),
        ("| 추천 노출 시 두 번째 모임 참여율 | 소규모 실험 (군별 20명) | 30% vs 20% |",
         "군별 20명이면 30% vs 20%는 6명 vs 4명 차이예요. 이 표본으로 10%p 차이를 근거로 쓰기엔 불확실해요."),
        "| 첫 모임 후 7일 안에 앱 재방문 | 앱 로그 | 41% |",
        "| 재참여율 (첫 → 두 번째 모임) | 앱 로그 | 22% |",
        "",
        "«formula»",
        "",
        "- 추천 쪽이 10%p 높게 나와서 안 A가 지표에 더 직접 닿는다고 봐요.",
    )
    code = _Body({})(
        "# 다음 모임 자동 추천 — 스코어 프로토타입 · 작성: 이도현",
        "# 팀장님 요청으로 공수 추정용. 추정: 3주 (추천 2주 + 알림 연동 1주)",
        "from math import exp",
        "",
        'WEIGHTS = {"distance": 0.5, "time_match": 0.3, "familiar": 0.2}',
        "",
        "",
        "def score(meetup: dict, user: dict) -> float:",
        '    distance = exp(-meetup["distance_km"] / 3)  # 3km 넘으면 빠르게 줄어요',
        '    time_match = 1.0 if meetup["weekday"] in user["preferred_days"] else 0.0',
        '    met = len(set(meetup["member_ids"]) & set(user["met_ids"]))',
        "    familiar = min(met, 3) / 3  # 지난 모임에서 같이 뛴 사람",
        '    return (WEIGHTS["distance"] * distance',
        '            + WEIGHTS["time_match"] * time_match',
        '            + WEIGHTS["familiar"] * familiar)',
        "",
        "",
        "def recommend(meetups: list[dict], user: dict, k: int = 3) -> list[dict]:",
        "    upcoming = [m for m in meetups",
        '                if m["starts_in_hours"] > 0 and m["id"] not in user["joined_ids"]]',
        ("    ranked = sorted(upcoming, key=lambda m: score(m, user))", "오름차순 정렬이라 점수가 가장 낮은 모임 3개를 추천해요(reverse=True가 빠졌어요)."),
        "    return ranked[:k]",
    )
    return [
        _art("design", "재참여 핵심 기능 비교안", "team", "검토 중", "자동 추천(팀장 안)과 참가자 채팅(이도현 안)의 효과·공수·근거, 결정 기준.", design),
        _art("result", "근거 자료 요약", "lead", "공유됨", "인터뷰·소규모 실험·앱 로그에서 뽑은 두 안의 근거 (팀장 정리).", result),
        _art("code", "다음 모임 추천 스코어 (프로토타입)", "peer", "프로토타입", "공수 추정용 추천 스코어 프로토타입 (이도현).", code, "python"),
    ]


def _workload() -> list[dict]:
    design = _Body({})(
        "# 사용자 인터뷰 요약 — 내일 10:00 팀 리뷰용 (60%)",
        "> 모아런 · 인터뷰 12명 (첫 모임 후 이탈 8명, 재참여 4명) · 정리: 기획(지원자)",
        "",
        "## 정리 기준",
        "- 한 사람이 이유를 여러 개 말하면 모두 센다",
        "- 인용은 발견마다 2개, 참여자 번호(P1–P12)로 표기",
        "",
        "## 핵심 발견",
        ("1. 아는 사람이 없어 어색했다 — 이탈자 8명 중 7명 (78%)", "이탈자 8명 중 7명이면 88%인데 78%로 적혀 있어요."),
        "2. 모임 시간이 퇴근 시간과 겹친다 — 4명",
        "3. 페이스가 안 맞아 뒤처졌다 — 3명",
        "",
        "## 인용 (작성 중)",
        '- "다들 서로 아는 것 같아서 끼기 어려웠어요" (P3, 이탈)',
        '- "끝나고 바로 흩어져서 다음에 또 갈 이유가 없었어요" (P7, 이탈)',
        "",
        "## 남은 일",
        "- [x] 녹취 12명 정리",
        "- [ ] 발견별 인용 2개씩 채우기",
        "- [ ] 이탈·재참여 비교 표",
        "- [ ] 제안 3가지 (리뷰 때 논의)",
    )
    result = _Body({"formula": _tex("재참여율", "두 번째 참여자", "첫 참여자")})(
        "# 비슷한 서비스 사례 정리 (작성 중) — 이도현",
        "> 내일 팀 리뷰용 · 비교 기준이 아직 헷갈려요",
        "",
        "| 서비스 | 첫 참여 후 재참여 장치 | 재참여율 | 출처 |",
        "|---|---|---:|---|",
        "| 러닝 크루 앱 A | 크루 단톡방 자동 초대 | 35% | 운영사 블로그 (2년 전) |",
        "| 등산 모임 앱 B | 다음 일정 자동 추천 | 28% | IR 자료 |",
        "| 독서 모임 C | 기존 회원 멘토 매칭 | 41% | 인터뷰 기사 |",
        ("| 운동 클래스 D | 첫 방문 할인 쿠폰 | 52% | 자체 추정 (결제 재방문) |",
         "D의 52%는 결제 재방문 기준 자체 추정이라 다른 서비스의 재참여율과 정의가 달라요. 같은 표에서 나란히 비교하면 안 돼요."),
        "| 모아런 (우리) | 리마인드 알림 (준비 중) | 22% | 앱 로그 |",
        "",
        "«formula»",
        "",
        ("- 비교 기준: 재참여율 숫자로 볼지, 장치 유형으로 묶을지 미정", "비교 기준이 정해지지 않아 이 표가 숫자 비교용인지 장치 유형 정리용인지 불분명해요."),
    )
    code = _Body({})(
        "# 인터뷰 메모 태그 집계 — 요약·사례 정리 공용 · 작성: 이도현",
        "import csv",
        "from collections import Counter",
        "",
        "TAGS = {",
        '    "어색함": ["어색", "아는 사람"],',
        '    "시간": ["시간", "퇴근"],',
        '    "페이스": ["페이스", "뒤처"],',
        "}",
        "",
        "",
        "def load(path: str) -> list[dict]:",
        '    with open(path, encoding="utf-8") as f:',
        "        return list(csv.DictReader(f))",
        "",
        "",
        "def count_tags(rows: list[dict]) -> Counter:",
        "    counts = Counter()",
        "    for r in rows:",
        "        for tag, words in TAGS.items():",
        '            if any(w in r["memo"] for w in words):',
        "                counts[tag] += 1",
        ("                break", "break 때문에 한 사람이 이유를 여러 개 말해도 첫 태그 하나만 세요. 요약(a1) 기준은 '모두 센다'예요."),
        "    return counts",
        "",
        "",
        "def churned(rows: list[dict]) -> list[dict]:",
        '    return [r for r in rows if r["second_meetup"] == "N"]',
        "",
        "",
        'if __name__ == "__main__":',
        '    rows = load("interviews.csv")',
        ("    print(len(rows), count_tags(churned(rows[1:])))", "DictReader가 이미 머리글을 건너뛰는데 rows[1:]로 첫 참여자(P1)를 한 명 더 빼요."),
    )
    return [
        _art("design", "사용자 인터뷰 요약 (60%)", "team", "작성 중", "내일 팀 리뷰용 인터뷰 12명 요약: 정리 기준·핵심 발견·남은 일.", design),
        _art("result", "비슷한 서비스 사례 정리 (이도현)", "peer", "작성 중", "재참여 장치와 재참여율 사례 비교표. 비교 기준이 아직 정해지지 않았어요.", result),
        _art("code", "인터뷰 태그 집계 스크립트", "peer", "작성 중", "인터뷰 메모에서 이탈 이유 태그를 세는 스크립트 (이도현).", code, "python"),
    ]


CATEGORY = {"delay": _delay, "scope": _scope, "conflict": _conflict, "workload": _workload}


# ------------------------------------------------------------------------------------------------------ public API

def problems(a: dict) -> list[str]:
    """Contract checks for one artifact (catalog self-check and tests). Empty list = valid."""
    out = [f"{k} missing" for k in FIELDS if k not in a]
    if a.get("kind") not in KIND_LABEL:
        out.append(f"kind {a.get('kind')!r}")
    if a.get("owner") not in OWNER_LABEL:
        out.append(f"owner {a.get('owner')!r}")
    for k, n in MAX_LEN.items():
        if not a.get(k) or len(a[k]) > n:
            out.append(f"{k} empty or longer than {n}")
    if (a.get("kind") == "code") != bool(a.get("lang")):
        out.append("lang is for code only")
    lines = (a.get("body") or "").split("\n")
    for cp in a.get("checkpoints", []):
        if not (1 <= cp.get("line", 0) <= len(lines)) or not lines[cp["line"] - 1].strip() or not cp.get("issue"):
            out.append(f"checkpoint {cp}")
    return out


_CACHE: dict[str, list[dict]] = {}


def _build(scn: dict, scenario_id: str) -> list[dict]:
    if scn.get("kind") == "dilemma":
        arts = _dilemma(scn)
    elif scenario_id in CATEGORY:
        arts = CATEGORY[scenario_id]()
    else:
        return []
    for i, a in enumerate(arts, 1):
        a["id"] = f"a{i}"
        bad = problems(a)
        if bad or not 1 <= len(a["checkpoints"]) <= 2:
            raise ValueError(f"artifact {scenario_id}/{a['id']}: {bad or 'needs 1-2 checkpoints'}")
    return arts


def catalog(scn: dict, scenario_id: str) -> list[dict]:
    """Artifacts for a scenario. Deterministic for a scenario id (same session -> same items).

    Each item carries its planted `checkpoints`; use without_checkpoints() for anything that leaves the agent."""
    if scenario_id not in _CACHE:
        _CACHE[scenario_id] = _build(scn, scenario_id)
    return copy.deepcopy(_CACHE[scenario_id])


def without_checkpoints(arts: list[dict]) -> list[dict]:
    """The Artifact shape Spring stores (contract fields only): planted checkpoints never leave the agent."""
    return [{k: a.get(k) for k in FIELDS} for a in arts]


def _scenario(scenario_id: str, scn: dict | None) -> dict | None:
    if scn is not None:
        return scn
    from .scenarios import get_scenario

    try:
        return get_scenario(scenario_id)
    except KeyError:
        return None


def checkpoints(scenario_id: str, scn: dict | None = None) -> dict[str, list[dict]]:
    """Planted checkpoints by artifact id for a scenario ({} when the scenario has no catalog)."""
    s = _scenario(scenario_id, scn)
    return {a["id"]: a["checkpoints"] for a in catalog(s, scenario_id)} if s else {}


def _quote_lines(body: str, quote: str) -> list[tuple[int, int]]:
    """(first, last) line of every occurrence of quote in body."""
    spans, start = [], body.find(quote)
    while start >= 0:
        first = body.count("\n", 0, start) + 1
        spans.append((first, first + quote.count("\n")))
        start = body.find(quote, start + 1)
    return spans


def _covers(note: dict, line: int, body: str) -> bool:
    an = note.get("anchor") or {}
    ls = an.get("line_start")
    if ls:
        le = an.get("line_end") or ls
        if ls - 1 <= line <= le + 1:
            return True
    q = an.get("quote") or ""
    return bool(q.strip()) and any(a <= line <= b for a, b in _quote_lines(body, q))


def artifact_checks(scenario_id: str, artifacts: list[dict], annotations: list[dict], scn: dict | None = None) -> list[dict]:
    """Admin view: was each planted checkpoint marked by the candidate?

    spotted = an annotation whose line range covers the checkpoint line (±1), or whose quote sits on that line.
    A markup of kind 'ok' (확인함) on the line is listed in annotation_ids but does not count as spotting it.
    Checkpoints follow the stored body: if a line moved, it is found again by its text; if it is gone, it is skipped."""
    s = _scenario(scenario_id, scn)
    if not s:
        return []
    stored = {a["id"]: a for a in artifacts or []}
    out = []
    for art in catalog(s, scenario_id):
        if art["id"] not in stored:
            continue
        planted = art["body"].split("\n")
        body = stored[art["id"]].get("body") or ""
        lines = body.split("\n")
        notes = [n for n in annotations or [] if n.get("artifact_id") == art["id"]]
        for cp in art["checkpoints"]:
            text = planted[cp["line"] - 1]
            line = cp["line"] if cp["line"] <= len(lines) and lines[cp["line"] - 1] == text else (lines.index(text) + 1 if text in lines else None)
            if line is None:
                continue
            hits = [n for n in notes if _covers(n, line, body)]
            out.append({"artifact_id": art["id"], "line": line, "issue": cp["issue"],
                        "spotted": any(n.get("kind") != "ok" for n in hits), "annotation_ids": [n["id"] for n in hits]})
    return out


def _anchor(a: dict) -> str:
    an = a.get("anchor") or {}
    if an.get("line_start"):
        ls, le = an["line_start"], an.get("line_end") or an["line_start"]
        return f"L{ls}" if ls == le else f"L{ls}-{le}"
    q = (an.get("quote") or "").strip()
    return f"“{q[:40]}{'…' if len(q) > 40 else ''}”" if q else ""


def context_block(session: dict, *, new_ids: set | None = None) -> str:
    """Prompt block: the shared items and the candidate's markups (new ones first). Empty string when there are none."""
    arts = session.get("artifacts") or []
    if not arts:
        return ""
    notes = session.get("annotations") or []
    count: dict[str, int] = {}
    for n in notes:
        count[n["artifact_id"]] = count.get(n["artifact_id"], 0) + 1
    lines = ["[같이 보는 과제]"]
    for a in arts:
        owner = OWNER_LABEL.get(a.get("owner") or "team", a.get("owner"))
        lines.append(f"- {a['id']} [{KIND_LABEL.get(a['kind'], a['kind'])}] {a['title']} (담당: {owner}, 상태: {a.get('status', '')})"
                     f" — {a.get('summary', '')}" + (f" · 마크업 {count[a['id']]}개" if count.get(a["id"]) else ""))
    if notes:
        titles = {a["id"]: a["title"] for a in arts}
        fresh = [n for n in notes if new_ids is None or str(n["id"]) in {str(i) for i in new_ids}]
        if fresh:
            lines.append("[지원자가 새로 남긴 마크업]" if new_ids is not None else "[지원자가 남긴 마크업]")
            for n in fresh[-6:]:
                lines.append(f"- #{n['id']} {titles.get(n['artifact_id'], n['artifact_id'])} {_anchor(n)} ({MARK_LABEL.get(n['kind'], n['kind'])}): {n['text']}")
    return "\n".join(lines)


def render_for_model(artifact: dict) -> str:
    """Tool output: numbered lines so a persona can point at L12, plus the markups on this artifact."""
    body = artifact.get("body") or ""
    numbered = "\n".join(f"{i:>3}| {line}" for i, line in enumerate(body.split("\n"), 1))
    owner = OWNER_LABEL.get(artifact.get("owner") or "team", artifact.get("owner"))
    lang = f", {artifact['lang']}" if artifact.get("lang") else ""
    out = [f"{artifact['id']} [{KIND_LABEL.get(artifact['kind'], artifact['kind'])}{lang}] {artifact['title']} (담당: {owner}, 상태: {artifact.get('status', '')})", numbered]
    notes = artifact.get("annotations") or []
    if notes:
        out.append("마크업:")
        out += [f"- #{n['id']} {_anchor(n)} ({MARK_LABEL.get(n['kind'], n['kind'])}): {n['text']}" for n in notes]
    return "\n".join(out)
