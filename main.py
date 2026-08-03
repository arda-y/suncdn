"""
Entry point for the project.
"""

# pylint: disable=wildcard-import, unused-wildcard-import
#
# this is a false positive from pylint's side
# you can just import the routes and not use them as long as they are registered in the FastAPI app

import sys

import uvicorn

import config

# rebasing the imports for future changes, bear with me for a while
from src.api_handler.routes import *

if __name__ == "__main__":
    port = config.get("PORT")
    if port is None:
        sys.exit("PORT is not set in config.yaml - refusing to start.")

    root_path = config.get("ROOT_PATH", "/sun")
    log_level = config.get("LOG_LEVEL", "info")

    uvicorn.run(
        "src.api_handler.app:app",  # FastAPI app instance, routes are registered to this app
        host="0.0.0.0",  # listen on all interfaces - fine since this is bound inside the container
        port=port,  # check config.yaml for the port
        reload=False,  # auto-reload on code changes; useful in dev, keep False in production
        log_level=log_level,  # "info" or "debug" recommended for dev, "warning"/"error" for prod
        loop="asyncio",  # event loop implementation used by uvicorn/asyncio
        lifespan="on",  # enables FastAPI's startup/shutdown (lifespan) hooks - required for app.py's purge task to run
        root_path=root_path,  # root path for the API, useful behind a reverse proxy
    )
