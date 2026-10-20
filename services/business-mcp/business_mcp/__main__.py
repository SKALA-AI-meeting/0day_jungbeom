"""`python -m business_mcp` → 0.0.0.0:9101."""

import uvicorn

from business_mcp.server import PORT, create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=PORT)
