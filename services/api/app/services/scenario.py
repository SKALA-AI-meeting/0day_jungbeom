"""시나리오: 미션 카탈로그 로드(버전 해시), 채용 건 조립, 세션 시작 시 이벤트·공개 예약 펼치기.

규칙은 docs/common/scenario-model.md가 정본이다. 카탈로그는 `scenarios/missions/<mission_id>/`
(mission.yaml·cards.yaml·persona.yaml·documents/·prompts/)이다. 조립 결과(positions.scenario)는
카드·문서·프롬프트 본문을 복사해 고정하므로, 이후 카탈로그가 바뀌어도 진행 중 채용 건과 실행 중
그래프는 영향을 받지 않는다.
"""

import importlib.util
import uuid
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MISSION = "debate"

# 같은 at_min에서의 실행 순서: 흐름 카드 → 요소 카드 → 붙는 카드(collab_disagree) → 결 메시지
_RANK_FLOW, _RANK_ELEMENT, _RANK_ATTACHED, _RANK_TEXTURE = range(4)

# 카드 정의에서 scenario로 복사하는 내용 필드(시점·구조 필드는 조립에서 따로 다룬다)
_CONTENT_FIELDS = (
    "name",
    "actor",
    "channel",
    "brief",
    "brief_note",
    "text",
    "sender_label",
    "recipient_label",
    "release_text",
    "system_text",
    "after_timeout_note",
    "colleague_greeting",
    "sends_document",
    "labels",
    "label_texts",
    "aux",
    "evidence_types",
    "metrics",
    "aux_facts",
    "finalize_metrics",
    "rubric",
    "fixed_opinions",
    "target_rule",
    "change_targets",
    "requires_docs",
    "facts_note",
    "situation",
    "debrief",
)
# mission.yaml에서 scenario로 그대로 복사하는 필드
_MISSION_FIELDS = (
    "name",
    "company",
    "candidate_role",
    "candidate_title",
    "parts",
    "default_division",
    "division_min",
    "division_min_messages",
    "debrief_texts",
    "final_template",
    "kickoff_assumption",
)


class InvalidElements(ValueError):
    """elements가 미션의 요소 id가 아니거나, 중복이거나, 1~5개가 아님(422 invalid_elements)."""


class InvalidMission(ValueError):
    """mission_id가 카탈로그에 없음(422 invalid_mission)."""


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_catalog(scenarios_dir: Path, mission_id: str = DEFAULT_MISSION) -> dict[str, Any]:
    """미션 폴더를 읽는다. {mission, cards, persona}."""
    root = scenarios_dir / "missions" / mission_id
    if not (root / "mission.yaml").is_file():
        raise InvalidMission(f"unknown mission: {mission_id}")
    return {
        "mission": _read_yaml(root / "mission.yaml"),
        "cards": _read_yaml(root / "cards.yaml"),
        "persona": _read_yaml(root / "persona.yaml"),
    }


def list_missions(scenarios_dir: Path) -> list[str]:
    """mission.yaml이 있는 미션 폴더 id들(관리자 카탈로그의 missions)."""
    root = scenarios_dir / "missions"
    return sorted(p.name for p in root.iterdir() if (p / "mission.yaml").is_file())


@cache
def _version_module(scenarios_dir: Path):
    spec = importlib.util.spec_from_file_location("scenarios_version", scenarios_dir / "version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def catalog_version(scenarios_dir: Path, mission_id: str = DEFAULT_MISSION) -> str:
    """scenarios/version.py의 catalog_version()을 그대로 쓴다(rag-mcp와 같은 함수)."""
    return _version_module(scenarios_dir.resolve()).catalog_version(mission_id, scenarios_dir)


def validate_elements(catalog: dict[str, Any], elements: list[str]) -> None:
    known = [e["id"] for e in catalog["cards"]["elements"]]
    if not 1 <= len(elements) <= len(known):
        raise InvalidElements(f"elements must have 1 to {len(known)} items")
    if len(set(elements)) != len(elements):
        raise InvalidElements("duplicate elements")
    unknown = [e for e in elements if e not in known]
    if unknown:
        raise InvalidElements(f"unknown elements: {unknown}")


def _minutes(value: float) -> float:
    # 카탈로그 비율이 소수 넷째 자리(0.0833)라 L/12가 9.996이 된다. 0.01분 단위로 맞춘다.
    return round(value, 2)


def _clock(at_min: float) -> str:
    total = int(round(at_min))
    return f"{total // 60:02d}:{total % 60:02d}"


def middle_times(session_minutes: int, n: int, timing: dict[str, Any]) -> list[float]:
    """중간 카드 n개의 시점. L·start + i·(L·span)/n (n==1이면 L·start)."""
    start = session_minutes * timing["middle"]["start_fraction"]
    span = session_minutes * timing["middle"]["span_fraction"]
    return [_minutes(start + i * span / n) for i in range(n)]


def _content(card_def: dict[str, Any]) -> dict[str, Any]:
    return {k: card_def[k] for k in _CONTENT_FIELDS if k in card_def}


def assemble(
    catalog: dict[str, Any],
    elements: list[str],
    session_minutes: int,
    documents: dict[str, str],
    prompts: dict[str, str],
) -> dict[str, Any]:
    """positions.scenario를 만든다. documents는 doc_id→본문, prompts는 상대 경로→본문."""
    validate_elements(catalog, elements)
    mission, cards_def = catalog["mission"], catalog["cards"]
    timing = cards_def["timing"]
    L = session_minutes
    selected = set(elements)
    element_defs = cards_def["elements"]
    element_of = {card["id"]: e["id"] for e in element_defs for card in e["cards"]}
    card_defs = {card["id"]: card for e in element_defs for card in e["cards"]}
    chosen = {cid: c for cid, c in card_defs.items() if element_of[cid] in selected}

    cards: list[tuple[float, int, dict[str, Any]]] = []

    def element_card(card_def: dict[str, Any], at: float) -> dict[str, Any]:
        card = {"card_id": card_def["id"], "element": element_of[card_def["id"]], "at_min": at}
        card.update(_content(card_def))
        return card

    # 고정 흐름 카드. 승격 대상(flow_card)이 선택됐으면 같은 시각에 요소 카드 하나만 둔다.
    promoted = {c["flow_card"]: c for c in chosen.values() if c.get("flow_card")}
    flow_at: dict[str, float] = {}
    for flow in cards_def["flow_cards"]:
        at = _minutes(timing["fixed"][flow["id"]] * L)
        flow_at[flow["id"]] = at
        if flow["id"] in promoted:
            card = element_card(promoted[flow["id"]], at)
            rank = _RANK_ELEMENT
        else:
            card = {"card_id": flow["id"], "at_min": at, "flow": True}
            card.update(_content(flow))
            rank = _RANK_FLOW
        if card.get("card_id") == "planning_division":
            card["window_start_min"] = 0
        if flow.get("or_on_submit"):
            card["or_on_submit"] = True
        cards.append((at, rank, card))

    # 중간 카드: middle_order 중 선택된 것만 L/4 + i·(L/2)/N
    middle = [cid for cid in timing["middle_order"] if cid in chosen]
    delayed: dict[str, float] = {}
    for cid, at in zip(middle, middle_times(L, len(middle), timing), strict=True):
        card = element_card(chosen[cid], at)
        effects = chosen[cid].get("effects") or {}
        if "release_document" in effects:
            release_at = _minutes(at + effects["delay_fraction"] * L)
            delayed[effects["release_document"]] = release_at
            card["effects"] = {
                "release_document": effects["release_document"],
                "release_at_min": release_at,
            }
        cards.append((at, _RANK_ELEMENT, card))

    # 붙는 카드(collab_disagree): 붙는 흐름 카드와 같은 시각의 별도 행
    for card_def in chosen.values():
        if card_def.get("attach_to"):
            at = flow_at[card_def["attach_to"]]
            card = element_card(card_def, at)
            card["attach_to"] = card_def["attach_to"]
            cards.append((at, _RANK_ATTACHED, card))

    # texture: 지정 요소가 미선택일 때만(midpoint_draft는 계획성 미선택일 때 L/2)
    for texture in cards_def.get("texture", []):
        if texture.get("only_when_unselected") in selected:
            continue
        at = _minutes(texture["at_fraction"] * L)
        card = {"card_id": texture["id"], "at_min": at, "texture": True}
        card.update(_content(texture))
        cards.append((at, _RANK_TEXTURE, card))

    cards.sort(key=lambda item: (item[0], item[1]))
    ordered = [card for _, _, card in cards]
    delay_card = next((c for c in ordered if c["card_id"] == "responsibility_delay"), None)

    return {
        "mission_id": mission["id"],
        "session_minutes": L,
        "elements": [e["id"] for e in element_defs if e["id"] in selected],
        "element_meta": [
            {k: e[k] for k in ("id", "name", "meaning", "how_we_see", "if_unselected")}
            for e in element_defs
            if e["id"] in selected
        ],
        "cards": ordered,
        **{k: mission[k] for k in _MISSION_FIELDS if k in mission},
        "vars": {
            # 킥오프의 {interview_expected_time}: 지연 카드 시각, 미선택이면 시작 시 공유
            "interview_expected_time": (
                _clock(delay_card["at_min"]) if delay_card else "시작 시 공유됨"
            ),
            "release_time": (
                _clock(delay_card["effects"]["release_at_min"]) if delay_card else None
            ),
            "final_length": mission["final_template"]["length"],
        },
        "releases_at_start": [d["id"] for d in mission["documents"] if d["id"] not in delayed],
        "documents": [
            {"doc_id": d["id"], "title": d["title"], "content": documents[d["id"]]}
            for d in mission["documents"]
        ],
        "persona": catalog["persona"],
        "prompts": prompts,
        "rubric_rules": cards_def["rubric_rules"],
        "common_labels": cards_def["common_labels"],
        "common_aux": cards_def.get("common_aux", []),
    }


def read_documents(scenarios_dir: Path, catalog: dict[str, Any]) -> dict[str, str]:
    root = scenarios_dir / "missions" / catalog["mission"]["id"] / "documents"
    return {
        d["id"]: (root / d["file"]).read_text(encoding="utf-8")
        for d in catalog["mission"]["documents"]
    }


def read_prompts(scenarios_dir: Path, mission_id: str) -> dict[str, str]:
    root = scenarios_dir / "missions" / mission_id / "prompts"
    if not root.is_dir():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def build_scenario(
    scenarios_dir: Path,
    elements: list[str],
    session_minutes: int = 120,
    mission_id: str = DEFAULT_MISSION,
) -> tuple[dict[str, Any], str]:
    """채용 건 생성 시 한 번 호출한다. (scenario, catalog_version)."""
    catalog = load_catalog(scenarios_dir, mission_id)
    scenario = assemble(
        catalog,
        elements,
        session_minutes,
        read_documents(scenarios_dir, catalog),
        read_prompts(scenarios_dir, mission_id),
    )
    return scenario, catalog_version(scenarios_dir, mission_id)


def expand(
    scenario: dict[str, Any], session_id: uuid.UUID, started_at: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """세션 시작 시 session_events 행과 document_releases 행을 만든다(collab_disagree도 별도 행)."""

    def at(minutes: float) -> datetime:
        return started_at + timedelta(minutes=minutes)

    events = [
        {
            "session_id": session_id,
            "card_id": card["card_id"],
            "element": card.get("element"),
            "due_at": at(card["at_min"]),
            "texture": bool(card.get("texture")),
            "or_on_submit": bool(card.get("or_on_submit")),
        }
        for card in scenario["cards"]
    ]
    releases = [
        {"session_id": session_id, "doc_id": doc_id, "release_at": started_at}
        for doc_id in scenario["releases_at_start"]
    ]
    for card in scenario["cards"]:
        effect = card.get("effects") or {}
        if "release_document" in effect:
            releases.append(
                {
                    "session_id": session_id,
                    "doc_id": effect["release_document"],
                    "release_at": at(effect["release_at_min"]),
                }
            )
    return events, releases
