"""`python -m assessment_mcp` → 0.0.0.0:9103."""

import uvicorn

from assessment_mcp.server import PORT, create_app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=PORT)
