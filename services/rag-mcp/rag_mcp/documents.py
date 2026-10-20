"""미션 회사 문서(`scenarios/missions/<id>/documents/*.md`) 읽기, 400자 청크, 카탈로그 버전."""

import importlib.util
from dataclasses import dataclass
from pathlib import Path

CHUNK_CHARS = 400


@dataclass(frozen=True)
class Document:
    doc_id: str  # 파일 이름(확장자 제외)
    title: str  # 첫 제목 줄
    content: str


def _title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return fallback


DEFAULT_MISSION = "planning"


def load_documents(scenarios_dir: Path, mission_id: str = DEFAULT_MISSION) -> list[Document]:
    """doc_id는 파일 이름(mission.yaml documents의 file과 같은 이름)."""
    docs = []
    for path in sorted((scenarios_dir / "missions" / mission_id / "documents").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        docs.append(Document(path.stem, _title(content, path.stem), content))
    return docs


def chunk(content: str, size: int = CHUNK_CHARS) -> list[str]:
    text = content.strip()
    return [text[i : i + size] for i in range(0, len(text), size)]


def catalog_version(scenarios_dir: Path, mission_id: str = DEFAULT_MISSION) -> str:
    """`scenarios/version.py`의 함수를 파일 경로로 import한다.

    api와 같은 함수이고 미션 폴더 전체의 해시다.
    """
    spec = importlib.util.spec_from_file_location("scenarios_version", scenarios_dir / "version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.catalog_version(mission_id, scenarios_dir)
