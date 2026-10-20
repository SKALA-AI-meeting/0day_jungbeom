"""`python -m rag_mcp` → 0.0.0.0:9102."""

import uvicorn

from rag_mcp.server import PORT, create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=PORT)
