"""
This file contains the FastAPI app.
It also runs the sub-processes in the background.
"""

from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api_handler.side_processes.base import purge_old_files
import config

logger = logging.getLogger("uvicorn.error")

background_tasks: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Creates sub-processes to run in the background when the server starts,
    and cancels them cleanly on shutdown."""
    task = asyncio.create_task(purge_old_files())
    background_tasks.add(task)
    task.add_done_callback(background_tasks.discard)

    yield

    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)


app = FastAPI(docs_url="/docs", redoc_url=None, lifespan=lifespan)

origins = config.get("ALLOWED_DOMAINS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
