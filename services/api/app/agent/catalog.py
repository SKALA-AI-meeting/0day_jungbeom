"""그래프·어시스턴트가 읽는 미션 카탈로그 뷰(positions.scenario 복사본 + 프롬프트 본문).

정본 구조는 docs/common/scenario-model.md 6장. 실행은 채용 건에 고정된 복사본을 읽는다:
- `scenario["seats"]`: 자리 → 페르소나 유형·이름(고정 p1·p2·p3).
- `scenario["prompts"]`: `prompts/` 상대 경로 → 본문(guard_patterns.yaml·fixed_phrases.yaml 포함).
- `scenario["catalog"]`: `{mission, personas, cards, keywords}` = 미션 폴더 YAML 4개를 읽은 dict.
`catalog` 키가 생기기 전에 만든 옛 채용 건은 같은 복사본의 조립 결과(personas·cards·keywords·
lead_option·fill_priority)로 4개를 재구성한다. 스케줄러·합의·시간 초과가 읽는 기준과 같게
하기 위해서다.
그래도 없는 부분만 미션 폴더(`<SCENARIOS_DIR>/missions/<mission_id>/`)에서 채우고(info 로그), 현재
catalog_version이 채용 건 기록과 다르면 경고한다. 파일 읽기는 (폴더, 기록 버전)마다 프로세스에서
한 번이라 같은 채용 건의 세션·토론·어시스턴트가 같은 내용을 받는다.
"""

import logging
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

PHASES = ("keyword", "problem", "solution", "proposal")
DEBATE_PHASES = ("keyword", "problem", "solution")
SEATS = ("p1", "p2", "p3")
PERSONA_TYPES = ("stubborn", "quiet", "critic", "agreeable", "divergent")
_FILES = {
    "mission": "mission.yaml",
    "personas": "personas.yaml",
    "cards": "cards.yaml",
    "keywords": "keywords.yaml",
}


def _has_batchim(word: str) -> tuple[bool, bool]:
    """(받침 있음, 받침이 ㄹ). 한글이 아니면 (False, False)."""
    for char in reversed(word.strip()):
        code = ord(char) - 0xAC00
        if 0 <= code < 11172:
            tail = code % 28
            return tail != 0, tail == 8
        if char.isalnum():
            return False, False
    return False, False


_JOSA = {
    "이": ("이", "가"),
    "가": ("이", "가"),
    "을": ("을", "를"),
    "를": ("을", "를"),
    "은": ("은", "는"),
    "는": ("은", "는"),
    "과": ("과", "와"),
    "와": ("과", "와"),
}


def attach(word: str, josa: str) -> str:
    """word + 알맞은 조사. 로/으로는 ㄹ 받침이면 '로'."""
    batchim, rieul = _has_batchim(word)
    if josa in ("로", "으로"):
        return word + ("으로" if batchim and not rieul else "로")
    pair = _JOSA.get(josa)
    if pair is None:
        return word + josa
    return word + (pair[0] if batchim else pair[1])


_VAR = re.compile(r"\{(\w+)\}(으로|로|이|가|을|를|은|는|과|와)?")


def render(template: str, **values: str) -> str:
    """고정 문장 치환. `{option}로`처럼 변수 바로 뒤 조사는 값의 끝 글자로 고른다."""

    def sub(match: re.Match[str]) -> str:
        value = values.get(match.group(1))
        if value is None:
            return match.group(0)
        josa = match.group(2)
        return attach(value, josa) if josa else value

    return _VAR.sub(sub, template)


_FILE_BASES: dict[tuple[Path, str | None], "Catalog"] = {}


def _rebuilt(scenario: dict[str, Any]) -> dict[str, Any]:
    """옛 채용 건: 조립 결과 키에서 Catalog가 읽는 4개를 되살린다(없는 키는 빠진다)."""
    parts: dict[str, Any] = {}
    if scenario.get("personas"):
        parts["personas"] = {"session": scenario["personas"]}
    if scenario.get("cards"):
        parts["cards"] = {"cards": scenario["cards"]}
    if scenario.get("keywords") and scenario.get("keyword_order"):
        parts["keywords"] = {
            "keywords": [
                {"key": key, **scenario["keywords"][key]} for key in scenario["keyword_order"]
            ]
        }
    if scenario.get("lead_option") and scenario.get("fill_priority"):
        parts["mission"] = {
            "lead_option": scenario["lead_option"],
            "consensus_fill": {"filler_priority": scenario["fill_priority"]},
        }
    return parts


def _default_scenarios_dir() -> Path:
    from app.config import get_settings

    return get_settings().scenarios_dir


@dataclass
class Catalog:
    mission: dict[str, Any]
    personas: dict[str, Any]
    cards: dict[str, Any]
    keywords: dict[str, Any]
    prompts: dict[str, str]
    seats: list[dict[str, Any]] = field(default_factory=list)

    # ---- 만들기 -------------------------------------------------------------------------
    @classmethod
    def from_dir(cls, mission_dir: Path) -> "Catalog":
        parts = {k: _read_yaml(mission_dir / f) for k, f in _FILES.items()}
        prompts_dir = mission_dir / "prompts"
        prompts = {
            p.relative_to(prompts_dir).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(prompts_dir.rglob("*"))
            if p.is_file()
        }
        catalog = cls(prompts=prompts, **parts)
        catalog.seats = catalog._default_seats()
        return catalog

    @classmethod
    def from_scenario(
        cls, scenario: dict[str, Any], scenarios_dir: Path | None = None
    ) -> "Catalog":
        raw = dict(scenario.get("catalog") or {}) or _rebuilt(scenario)
        prompts = dict(scenario.get("prompts") or {})
        missing = [k for k in _FILES if not raw.get(k)]
        if missing or not prompts:
            base = cls._file_base(scenario, scenarios_dir or _default_scenarios_dir())
            log.info("scenario copy lacks %s; filled from mission files", missing or ["prompts"])
            for key in missing:
                raw[key] = getattr(base, key)
            if not prompts:
                prompts = base.prompts
        catalog = cls(prompts=prompts, **{k: raw[k] for k in _FILES})
        catalog.seats = list(scenario.get("seats") or catalog._default_seats())
        return catalog

    @classmethod
    def _file_base(cls, scenario: dict[str, Any], scenarios_dir: Path) -> "Catalog":
        from app.services.scenario import catalog_version

        mission_id = scenario.get("mission_id", "debate")
        recorded = scenario.get("catalog_version")
        key = (scenarios_dir.resolve() / mission_id, recorded)
        if key not in _FILE_BASES:
            current = catalog_version(scenarios_dir, mission_id)
            if recorded != current:
                log.warning(
                    "position catalog_version %s differs from current %s; missing parts come "
                    "from the current %s files",
                    recorded,
                    current,
                    mission_id,
                )
            _FILE_BASES[key] = cls.from_dir(scenarios_dir / "missions" / mission_id)
        return _FILE_BASES[key]

    def _default_seats(self) -> list[dict[str, Any]]:
        return [
            {"seat": p["seat"], "persona_type": p["id"], "name": p["name"]}
            for p in self.personas.get("session", [])
        ]

    # ---- 자리·페르소나 ---------------------------------------------------------------------
    def type_of(self, seat: str) -> str:
        return next(s["persona_type"] for s in self.seats if s["seat"] == seat)

    def seat_of(self, persona_type: str) -> str | None:
        return next((s["seat"] for s in self.seats if s["persona_type"] == persona_type), None)

    def name_of(self, seat: str) -> str:
        return next((s["name"] for s in self.seats if s["seat"] == seat), seat)

    def persona(self, seat: str) -> dict[str, Any]:
        ptype = self.type_of(seat)
        return next(p for p in self.personas["session"] if p["id"] == ptype)

    def persona_prompt(self, seat: str) -> str:
        return self.prompts.get(f"persona_{self.type_of(seat)}.md", "")

    def safe_phrase(self, seat: str) -> str:
        return self.prompts.get(f"safe_{self.type_of(seat)}.md", "").strip() or "네, 들어 볼게요."

    def seats_by_priority(self, types: list[str]) -> list[str]:
        """유형 우선순위 목록을 세션 자리 순서로(없는 유형은 건너뜀)."""
        return [seat for t in types if (seat := self.seat_of(t))]

    # ---- 키워드·안 ------------------------------------------------------------------------
    def keyword_list(self) -> list[dict[str, Any]]:
        return list(self.keywords.get("keywords", []))

    def keyword_key_for(self, value: str | None) -> str | None:
        """확정 키워드 값(라벨 '물' 또는 키 'water')을 키로."""
        if not value:
            return None
        for kw in self.keyword_list():
            if value.strip() in (kw["key"], kw["label"]):
                return kw["key"]
        return None

    def catalog_options(self, phase: str, keyword_key: str | None) -> list[dict[str, str]]:
        """그 단계의 시나리오 안 전체 [{scenario_option_key, label}]."""
        if phase == "keyword":
            return [
                {"scenario_option_key": k["key"], "label": k["label"]} for k in self.keyword_list()
            ]
        kw = next((k for k in self.keyword_list() if k["key"] == keyword_key), None)
        if kw is None or phase not in ("problem", "solution"):
            return []
        items = kw["problems"] if phase == "problem" else kw["solutions"]
        return [{"scenario_option_key": i["key"], "label": i["label"]} for i in items]

    def label_of(self, key: str) -> str | None:
        for kw in self.keyword_list():
            if kw["key"] == key:
                return kw["label"]
            for item in kw["problems"] + kw["solutions"]:
                if item["key"] == key:
                    return item["label"]
        return None

    # ---- 카드 -----------------------------------------------------------------------------
    def card(self, card_id: str) -> dict[str, Any] | None:
        return next((c for c in self.cards.get("cards", []) if c["card_id"] == card_id), None)

    def cards_in(self, phase: str) -> list[dict[str, Any]]:
        return [c for c in self.cards.get("cards", []) if c["stage_id"] == phase]

    # ---- 프롬프트·고정 문장 ------------------------------------------------------------------
    @cached_property
    def fixed(self) -> dict[str, Any]:
        return yaml.safe_load(self.prompts.get("fixed_phrases.yaml", "")) or {}

    @cached_property
    def stance_fallback(self) -> dict[str, Any]:
        return yaml.safe_load(self.prompts.get("stance_fallback.yaml", "")) or {}

    @cached_property
    def guard_spec(self) -> dict[str, Any]:
        return yaml.safe_load(self.prompts.get("guard_patterns.yaml", "")) or {}

    @property
    def notices(self) -> dict[str, str]:
        return dict(self.fixed.get("notices") or {})


def _read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
