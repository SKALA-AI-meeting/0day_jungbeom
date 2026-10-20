import os
import tempfile

os.environ["MOCK_LLM"] = "1"
os.environ["DAYZERO_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.pop("ADMIN_TOKEN", None)
