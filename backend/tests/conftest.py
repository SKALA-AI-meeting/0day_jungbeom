import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["MOCK_LLM"] = "1"
os.environ["DAYZERO_DB"] = os.path.join(_tmp, "test.db")
os.environ["DETECTOR_DB"] = os.path.join(_tmp, "detector.db")
os.environ["DETECTOR_MCP_URL"] = "inmemory"  # in-process detector-mcp
os.environ["DETECTOR_RULES_ONLY"] = "1"  # deterministic: no external model in tests
os.environ.pop("ADMIN_TOKEN", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
