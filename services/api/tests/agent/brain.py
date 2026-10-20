"""FakeLLM 응답 함수. 입력(시스템 프롬프트·블록 이름)으로 호출 종류를 알아보고 테스트가 정한 값을
낸다.

| 호출 | 알아보는 법 | 응답 |
|---|---|---|
| 메시지 분류 | system이 classify.CLASSIFY_SYSTEM | `classify[본문]`(없으면 kind other) |
| 관찰 분류 | system이 observe_labels.md | `labels[카드 id]`의 레이블·aux, 근거는 허용 타입 활동
전부(관련 메시지 id는 비움) |
| 파트 문서 | `[쓸 파트]` 블록 | 파트 제목 + 반영할 지시의 핵심어 + 회사 문서 인용(300자 안팎) |
| 진행 기록 | `[진행 기록]` 블록 | 파트마다 "사례 후보 추리는 중" |
| 그 밖(페르소나 말) | — | 고정 문장 |

calls에 (종류, 입력 전체)를 남겨 테스트가 컨텍스트를 검사한다.
"""

import json
import re
from collections.abc import Callable
from typing import Any

from app.agent.llm import tool_call
from app.agent.session.classify import CLASSIFY_SYSTEM
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

SAY = "네, 확인했어요. 그렇게 진행할게요."
ACTIVITY = re.compile(r"^- (\w+) id=(\S+)", re.M)


def cls(kind: str = "other", **fields: Any) -> dict[str, Any]:
    """분류 응답 한 건(필드는 classify.CLASSIFY_SYSTEM 형식)."""
    return {"kind": kind, "decision": "other", "instructions": [], **fields}


def instr(part_no: int | None, text: str, *keywords: str) -> dict[str, Any]:
    return {"part_no": part_no, "text": text, "keywords": list(keywords)}


class Brain:
    def __init__(
        self,
        classify: dict[str, dict[str, Any]] | None = None,
        labels: dict[str, dict[str, Any] | Callable[[str], dict[str, Any]]] | None = None,
        say: str = SAY,
        tools: dict[str, tuple[str, dict[str, Any]]] | None = None,
        echo_search: bool = False,
    ) -> None:
        self.classify = classify or {}
        self.labels = labels or {}
        self.say = say
        self.tools = tools or {}  # {질문 일부: (도구, 인자)}. respond에서 도구를 한 번 고른다
        self.echo_search = echo_search  # 답에 [문서 검색 결과] 첫 줄을 "제목 보니까 …"로 인용
        self.calls: list[tuple[str, str]] = []
        self.omit = {}  # {파트 번호: n}. 그 파트의 다음 문서 n개는 핵심어를 빼고 쓴다(재생성 확인)

    def __call__(self, messages: list[BaseMessage]) -> str | AIMessage:
        system = str(messages[0].content)
        human = "\n".join(str(m.content) for m in messages[1:])
        if system == CLASSIFY_SYSTEM:
            self.calls.append(("classify", human))
            content = human[human.index("[메시지]") :].split("\n", 1)[1]
            content = re.sub(r"^\(문서 답글: [^)]*\)\n", "", content)
            return json.dumps(self.classify.get(content.strip(), cls()), ensure_ascii=False)
        if system.startswith("# 관찰 레이블 분류 지시문"):
            self.calls.append(("observe", human))
            return self._observe(human)
        if "[쓸 파트]" in human:
            self.calls.append(("draft", human))
            return self._draft(human)
        if "[진행 기록]" in human:
            self.calls.append(("progress", human))
            parts = re.findall(r"(\d)번", human.split("파트:")[-1])
            return json.dumps({"progress": {p: "사례 후보 추리는 중" for p in parts}})
        self.calls.append(("say", human))
        if not isinstance(messages[-1], ToolMessage):
            for key, (name, args) in self.tools.items():
                if key in human.rsplit("[최근 대화]", 1)[-1]:
                    return tool_call(name, **args)
        if self.echo_search:
            block = re.split(r"\n\n\[", human.split("[문서 검색 결과]", 1)[-1], maxsplit=1)[0]
            found = re.findall(r"^- \[([^\]]+)\] (.*?)(?=^- \[|\Z)", block, re.S | re.M)
            if found:
                title = found[0][0]
                chunks = " ".join(" ".join(c.split()) for t, c in found if t == title)
                return f"{title} 보니까 {chunks[:400]}"
        return self.say

    def _observe(self, human: str) -> str:
        card_id = re.search(r"카드 id: (\w+)", human).group(1)
        spec = self.labels.get(card_id) or {}
        if callable(spec):
            spec = spec(human)
        allowed = re.search(r"근거 타입: (.*)", human).group(1).split(", ")
        evidence = [
            {"type": kind, "id": item}
            for kind, item in ACTIVITY.findall(human)
            if kind in allowed and kind in spec.get("types", allowed)
        ]
        aux = {"related_message_ids": [], **spec.get("aux", {})}
        return json.dumps({"label": spec.get("label"), "evidence": evidence, "aux": aux})

    def _draft(self, human: str) -> str:
        head = re.search(r"\[쓸 파트\]\n(\d)번 (\S+)", human)
        keywords = re.findall(r"\[핵심어: ([^\]]+)\]", human)
        words = [k.strip() for group in keywords for k in group.split(",")]
        part = int(head.group(1))
        if self.omit.get(part):
            self.omit[part] -= 1
            words = []
        body = " ".join(f"{w}을(를) 기준으로 정리했다." for w in words)
        return (
            f"{head.group(1)}번 {head.group(2)} 초안. 지표 현황에 따르면 첫 참여 후 재방문 비율이 "
            f"낮다. "
            f"{body} 사용자 관점에서 첫 모임 경험을 이어 주는 방향으로 쓴다."
        )
