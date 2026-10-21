import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["MOCK_LLM"] = "1"
os.environ["DETECTOR_DB"] = os.path.join(_tmp, "detector.db")
os.environ["DETECTOR_RULES_ONLY"] = "1"  # deterministic: no external model in tests
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["RAG_LOCAL_INDEX"] = os.path.join(_tmp, "rag_index.json")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("VECTOR_DB_URL", None)
os.environ.pop("RABBIT_URL", None)
os.environ["INTERNAL_KEY"] = "test-key"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def wired():
    """In-process MCP servers + fake Spring internal API + in-memory event sink."""
    import httpx

    from app import runner
    from app.harness import tools
    from app.harness.events import MemorySink
    from mcp_servers.business import server as business
    from mcp_servers.detector.server import mcp as detector_mcp
    from mcp_servers.rag.server import mcp as rag_mcp
    from rag_pipeline import index
    from tests.fake_backend import FakeBackend

    index.build()
    backend = FakeBackend()
    business.use_transport(httpx.MockTransport(backend.handle))
    tools.use_in_process("business", business.mcp)
    tools.use_in_process("rag", rag_mcp)
    tools.use_in_process("detector", detector_mcp)
    sink = MemorySink()
    runner.set_sink(sink)
    return {"backend": backend, "sink": sink}
