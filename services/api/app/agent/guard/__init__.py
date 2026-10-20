"""guard: 모든 생성 텍스트에 금지 패턴 치환과 600자 제한을 적용한다(harness.md Guardrails).

패턴 정본은 `scenarios/prompts/guard_patterns.yaml`(prompts 트랙). 실행 시에는 채용 건에 고정된
scenario 복사본(`scenario["prompts"]["guard_patterns.yaml"]`)을 읽는다. 규칙:
- 문장 단위(sentence_split)로 본다. 문장이 그룹 패턴에 걸리면 그 그룹의 안내문(notices)으로 바꾼다.
  그룹에 unless가 있고 문장이 unless에도 걸리면 그 그룹은 건너뛴다(업무 지표 문장 보존).
  단 strict_patterns(사람에 대한 점수 표현)는 unless보다 먼저 검사해 걸리면 치환한다.
- 같은 안내문이 한 메시지에 두 번 이상 나오면 첫 번째만 남긴다.
- 그 뒤 max_chars로 자른다.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

GUARD_FILE = "guard_patterns.yaml"


@dataclass(frozen=True)
class Group:
    id: str
    notice: str
    patterns: tuple[re.Pattern[str], ...]
    unless: tuple[re.Pattern[str], ...]
    strict: tuple[re.Pattern[str], ...] = ()  # unless보다 먼저 검사(사람에 대한 점수 표현)

    def hits(self, sentence: str) -> bool:
        if any(p.search(sentence) for p in self.strict):
            return True
        if not any(p.search(sentence) for p in self.patterns):
            return False
        return not any(p.search(sentence) for p in self.unless)


@dataclass(frozen=True)
class GuardResult:
    text: str
    hits: tuple[str, ...]  # 걸린 그룹 id(문장 순서)
    truncated: bool


def _compile(patterns: list[str] | None) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns or ())


class Guard:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.notices: dict[str, str] = dict(spec["notices"])
        self.groups = tuple(
            Group(
                id=g["id"],
                notice=self.notices[g["replacement"]],
                patterns=_compile(g["patterns"]),
                unless=_compile(g.get("unless")),
                strict=_compile(g.get("strict_patterns")),
            )
            for g in spec["groups"]
        )
        self.max_chars = int(spec["max_chars"])
        # 구분자를 결과에 남기려고 캡처 그룹으로 감싼다(re.split이 구분자도 돌려준다)
        self._split = re.compile(f"({spec['sentence_split']})")
        titles = (spec.get("citation") or {}).get("titles") or {}
        self.titles: dict[str, str] = {doc_id: t["title"] for doc_id, t in titles.items()}
        self._aliases = {
            doc_id: tuple(t.get("aliases") or [t["title"]]) for doc_id, t in titles.items()
        }

    @classmethod
    def from_yaml(cls, text: str) -> "Guard":
        return cls(yaml.safe_load(text))

    def groups_hit(self, sentence: str) -> list[str]:
        """문장이 걸리는 그룹 id 전부(단위 테스트·진단용)."""
        return [g.id for g in self.groups if g.hits(sentence)]

    def _first_group(self, sentence: str) -> Group | None:
        return next((g for g in self.groups if g.hits(sentence)), None)

    def apply(self, text: str) -> GuardResult:
        pieces = self._split.split(text.strip())
        out: list[str] = []
        hits: list[str] = []
        # 짝수 인덱스가 문장, 홀수 인덱스가 구분자
        for index, piece in enumerate(pieces):
            if index % 2 or not piece:
                out.append(piece or "")
                continue
            group = self._first_group(piece)
            if group is None:
                out.append(piece)
                continue
            hits.append(group.id)
            out.append(group.notice)
        result = _dedupe("".join(out), self.notices.values())
        truncated = len(result) > self.max_chars
        if truncated:
            result = result[: self.max_chars].rstrip()
        return GuardResult(result, tuple(hits), truncated)

    def cited_docs(self, text: str) -> list[str]:
        """본문에 제목·별칭이 나온 회사 문서 id(인용 검사·meta 기록용)."""
        return [d for d, aliases in self._aliases.items() if any(a in text for a in aliases)]


def _dedupe(text: str, notices) -> str:
    """같은 안내문은 처음 한 번만 남긴다. 지운 자리의 빈 줄·공백을 정리한다."""
    for notice in notices:
        first = text.find(notice)
        if first < 0:
            continue
        end = first + len(notice)
        if notice in text[end:]:
            text = text[:end] + text[end:].replace(notice, "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


@lru_cache(maxsize=16)
def _cached(text: str) -> Guard:
    return Guard.from_yaml(text)


def guard_for(scenario: dict[str, Any]) -> Guard:
    """채용 건에 고정된 패턴(scenario 복사본)으로 만든 Guard. 같은 본문은 다시 컴파일하지 않는다."""
    return _cached(scenario["prompts"][GUARD_FILE])
