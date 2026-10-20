"""시나리오: 카탈로그 로드(버전 해시), 채용 건 조립, 세션 시작 시 이벤트·공개 예약 펼치기.

규칙은 docs/common/scenario-model.md가 정본이다.
조립 결과(positions.scenario)는 카드·문서·프롬프트 본문을
복사해 고정하므로, 이후 카탈로그가 바뀌어도 진행 중 채용 건과 실행 중 그래프는 영향을 받지 않는다.
"""

import importlib.util
import uuid
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import yaml

# 같은 at_min에서의 실행 순서: 흐름 카드 → 요소 카드 → 붙는 카드(respect) → 결 메시지
_RANK_FLOW, _RANK_ELEMENT, _RANK_ATTACHED, _RANK_TEXTURE = range(4)

# 요소 카드에서 scenario로 복사하는 필드.
# order·attach_to·effects·unselected는 조립에 쓰고 따로 다룬다.
_ELEMENT_FIELDS = (
    "name",
    "actor",
    "channel",
    "brief",
    "brief_note",
    "text",
    "labels",
    "label_texts",
    "metrics",
    "rubric",
    "aux_facts",
    "requires_docs",
    "situation",
    "debrief",
)
_SHARED_FIELDS = (
    "company",
    "persona",
    "parts",
    "candidate_role",
    "default_division",
    "division_min",
    "rubric_rules",
    "common_labels",
)


class InvalidElements(ValueError):
    """elements가 카탈로그 id가 아니거나, 중복이거나, 1~4개가 아님(400 invalid_elements)."""


def load_catalog(scenarios_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((scenarios_dir / "catalog.yaml").read_text(encoding="utf-8"))


@cache
def _version_module(scenarios_dir: Path):
    spec = importlib.util.spec_from_file_location("scenarios_version", scenarios_dir / "version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def catalog_version(scenarios_dir: Path) -> str:
    """scenarios/version.py의 catalog_version()을 그대로 쓴다(rag-mcp와 같은 함수)."""
    return _version_module(scenarios_dir.resolve()).catalog_version(scenarios_dir)


def validate_elements(catalog: dict[str, Any], elements: list[str]) -> None:
    known = {card["id"] for card in catalog["element_cards"]}
    if not 1 <= len(elements) <= len(known):
        raise InvalidElements("elements must have 1 to 4 items")
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


def element_times(session_minutes: int, n: int) -> list[float]:
    """요소 카드(attach_to 없는 것) n개의 시점. n==1이면 L/4, 아니면 L/4 + i·(L/2)/n."""
    quarter = session_minutes / 4
    return [_minutes(quarter + i * (session_minutes / 2) / n) for i in range(n)]


def assemble(
    catalog: dict[str, Any],
    elements: list[str],
    session_minutes: int,
    documents: dict[str, str],
    prompts: dict[str, str],
) -> dict[str, Any]:
    """positions.scenario를 만든다. documents는 doc_id→본문, prompts는 상대 경로→본문."""
    validate_elements(catalog, elements)
    L = session_minutes
    by_id = {card["id"]: card for card in catalog["element_cards"]}
    selected = sorted((by_id[e] for e in elements), key=lambda c: c["order"])
    non_review = [c for c in selected if not c.get("attach_to")]

    cards: list[tuple[float, int, dict[str, Any]]] = []
    flow_at: dict[str, float] = {}
    for flow in catalog["flow_cards"]:
        at = _minutes(flow["at_fraction"] * L)
        flow_at[flow["id"]] = at
        card = {"card_id": flow["id"], "at_min": at, "flow": True}
        card.update({k: flow[k] for k in ("actor", "channel", "brief") if k in flow})
        cards.append((at, _RANK_FLOW, card))

    delayed: dict[str, float] = {}
    for card_def, at in zip(non_review, element_times(L, len(non_review)), strict=True):
        card = _element_card(card_def, at)
        effects = card_def.get("effects") or {}
        if "release_document" in effects:
            release_at = _minutes(at + effects["delay_fraction"] * L)
            delayed[effects["release_document"]] = release_at
            card["effects"] = {
                "release_document": effects["release_document"],
                "at_min": release_at,
            }
        cards.append((at, _RANK_ELEMENT, card))

    for card_def in selected:
        if card_def.get("attach_to"):
            at = flow_at[card_def["attach_to"]]
            card = _element_card(card_def, at)
            card["attach_to"] = card_def["attach_to"]
            cards.append((at, _RANK_ATTACHED, card))

    for texture in catalog.get("texture", []):
        at = _minutes(texture["at_fraction"] * L)
        card = {"card_id": texture["id"], "at_min": at, "texture": True}
        card.update({k: texture[k] for k in ("actor", "channel", "brief") if k in texture})
        cards.append((at, _RANK_TEXTURE, card))

    # 미선택 요소의 처리(unselected): respect 미선택이면 리뷰 카드에 위반 없음 표시
    selected_ids = {c["id"] for c in selected}
    for card_def in catalog["element_cards"]:
        if card_def["id"] in selected_ids:
            continue
        if (card_def.get("unselected") or {}).get("review_without_violation"):
            for _, _, card in cards:
                if card["card_id"] == card_def.get("attach_to"):
                    card["review_without_violation"] = True

    cards.sort(key=lambda item: (item[0], item[1]))
    responsibility = next((c for _, _, c in cards if c["card_id"] == "responsibility"), None)

    return {
        "session_minutes": L,
        "elements": [c["id"] for c in selected],
        "cards": [card for _, _, card in cards],
        "releases_at_start": [d["id"] for d in catalog["documents"] if d["id"] not in delayed],
        "documents": [
            {"doc_id": d["id"], "title": d["title"], "content": documents[d["id"]]}
            for d in catalog["documents"]
        ],
        "prompts": prompts,
        "texture": catalog.get("texture", []),
        "vars": {
            # 킥오프 브리프의 {interview_expected_time}: 책임감 카드 시각, 미선택이면 시작 시 공유
            "interview_expected_time": (
                _clock(responsibility["at_min"]) if responsibility else "시작 시 공유됨"
            ),
        },
        **{k: catalog[k] for k in _SHARED_FIELDS if k in catalog},
    }


def _element_card(card_def: dict[str, Any], at: float) -> dict[str, Any]:
    card = {"card_id": card_def["id"], "at_min": at, "element": card_def["id"]}
    card.update({k: card_def[k] for k in _ELEMENT_FIELDS if k in card_def})
    return card


def read_documents(scenarios_dir: Path, catalog: dict[str, Any]) -> dict[str, str]:
    root = scenarios_dir / "documents"
    return {d["id"]: (root / d["file"]).read_text(encoding="utf-8") for d in catalog["documents"]}


def read_prompts(scenarios_dir: Path) -> dict[str, str]:
    root = scenarios_dir / "prompts"
    if not root.is_dir():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def build_scenario(
    scenarios_dir: Path, elements: list[str], session_minutes: int = 120
) -> tuple[dict[str, Any], str]:
    """채용 건 생성 시 한 번 호출한다. (scenario, catalog_version)."""
    catalog = load_catalog(scenarios_dir)
    scenario = assemble(
        catalog,
        elements,
        session_minutes,
        read_documents(scenarios_dir, catalog),
        read_prompts(scenarios_dir),
    )
    return scenario, catalog_version(scenarios_dir)


def expand(
    scenario: dict[str, Any], session_id: uuid.UUID, started_at: datetime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """세션 시작 시 session_events 행과 document_releases 행을 만든다(respect도 별도 행)."""

    def at(minutes: float) -> datetime:
        return started_at + timedelta(minutes=minutes)

    events = [
        {
            "session_id": session_id,
            "card_id": card["card_id"],
            "element": card.get("element"),
            "due_at": at(card["at_min"]),
            "texture": bool(card.get("texture")),
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
                    "release_at": at(effect["at_min"]),
                }
            )
    return events, releases
