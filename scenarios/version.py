"""카탈로그 버전 해시. api(채용 건 고정)와 rag-mcp(색인 키)가 같은 함수를 쓴다.

표준 라이브러리만 쓴다. 두 서비스가 `scenarios/`를 읽기 전용으로 마운트하고 파일 경로로 import한다.
"""

import hashlib
from pathlib import Path


def _versioned_files(root: Path) -> list[Path]:
    files = [root / "catalog.yaml"]
    files += sorted((root / "documents").glob("*.md"))
    prompts = root / "prompts"
    if prompts.is_dir():
        files += sorted(p for p in prompts.rglob("*") if p.is_file())
    return files


def catalog_version(scenarios_dir: str | Path | None = None) -> str:
    """catalog.yaml, documents/*.md, prompts/* 전체 내용의 해시(16자리 hex).

    문서·프롬프트 본문만 바뀌어도 버전이 바뀐다. 파일 이름도 해시에 넣어 이동·이름 변경을 구분한다.
    """
    root = Path(scenarios_dir) if scenarios_dir else Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in _versioned_files(root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]
