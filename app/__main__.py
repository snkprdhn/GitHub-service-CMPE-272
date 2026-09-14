"""Run the service with settings loaded from the environment or .env."""

# Author: Sonit — local application startup.

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
