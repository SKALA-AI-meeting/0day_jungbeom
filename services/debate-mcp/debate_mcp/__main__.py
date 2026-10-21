"""`python -m debate_mcp` → 0.0.0.0:9101."""

import uvicorn

from debate_mcp.server import PORT, create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=PORT)
