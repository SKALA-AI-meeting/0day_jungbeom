"""계약 비교 도구. 정본은 저장소 루트 tests/contract_shape.py(api·report-worker 공용)다."""

import importlib.util

from app.config import REPO_ROOT

_spec = importlib.util.spec_from_file_location(
    "contract_shape", REPO_ROOT / "tests" / "contract_shape.py"
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

CANDIDATE_OPTIONAL = _module.CANDIDATE_OPTIONAL
assert_contract = _module.assert_contract
assert_shape = _module.assert_shape
load_contract = _module.load_contract
