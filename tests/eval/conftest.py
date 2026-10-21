"""eval 픽스처 공용: live 실행 결과를 `tests/e2e/records/eval-live-<일시>.md` 한 파일에 모은다."""

from datetime import datetime
from pathlib import Path

import pytest

RECORDS = Path(__file__).resolve().parents[1] / "e2e" / "records"


@pytest.fixture(scope="session")
def live_report():
    sections: list[str] = []
    yield sections
    if sections:
        RECORDS.mkdir(parents=True, exist_ok=True)
        path = RECORDS / f"eval-live-{datetime.now():%Y%m%d-%H%M}.md"
        path.write_text("# eval live 결과\n\n" + "\n\n".join(sections) + "\n", "utf-8")
