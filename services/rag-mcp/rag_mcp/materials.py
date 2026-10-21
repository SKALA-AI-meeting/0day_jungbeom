"""미션 자료 읽기, 400자 청크, 카탈로그 버전.

자료는 `scenarios/missions/<id>/keywords.yaml`의 키워드별 `materials`다.

자료 목록·제목·키워드는 keywords.yaml이 정본이고 본문은 `materials/<file>`이다. 같은 목록을
`scripts/seed.py`가 `materials` 테이블(원문)에 시드하고 rag-mcp는 `material_chunks`(색인)에 쓴다.
"""

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import yaml

CHUNK_CHARS = 400
DEFAULT_MISSION = "debate"


@dataclass(frozen=True)
class Material:
    material_id: str
    keyword_key: str
    title: str
    content: str


def load_materials(scenarios_dir: Path, mission_id: str = DEFAULT_MISSION) -> list[Material]:
    root = scenarios_dir / "missions" / mission_id
    catalog = yaml.safe_load((root / "keywords.yaml").read_text(encoding="utf-8"))
    return [
        Material(
            item["material_id"],
            keyword["key"],
            item["title"],
            (root / "materials" / item["file"]).read_text(encoding="utf-8"),
        )
        for keyword in catalog["keywords"]
        for item in keyword.get("materials", [])
    ]


def chunk(content: str, size: int = CHUNK_CHARS) -> list[str]:
    text = content.strip()
    return [text[i : i + size] for i in range(0, len(text), size)]


def catalog_version(scenarios_dir: Path, mission_id: str = DEFAULT_MISSION) -> str:
    """`scenarios/version.py`의 함수를 파일 경로로 import한다(api·seed와 같은 함수)."""
    spec = importlib.util.spec_from_file_location("scenarios_version", scenarios_dir / "version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.catalog_version(mission_id, scenarios_dir)
