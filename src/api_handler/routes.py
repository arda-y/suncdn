"""
All API routes for the SunCDN project.
"""

import logging
import os
import uuid
from pathlib import Path
from urllib.parse import quote

import aiofiles
from fastapi import UploadFile, HTTPException, status
from fastapi.responses import FileResponse

import config
from src.api_handler.app import app

__all__ = [
    "root",
    "home",
    "create_upload_file",
]  # explicitly define the routes that should be registered to the FastAPI app

logger = logging.getLogger("uvicorn.error")

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_ROOT = Path("./mountpoint/downloads").resolve()


@app.get("/")
async def home():
    """Home route for the API."""
    file_path = BASE_DIR / ".." / ".." / "index.html"
    return FileResponse(file_path)


@app.get("/root")
async def root():
    """To check if the server is running without much hassle."""
    return {"message": "Hello World"}


@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile):
    raw_filename = file.filename or ""
    safe_name = os.path.basename(raw_filename).strip()

    if not safe_name or safe_name in (".", ".."):
        logger.warning("Rejected upload with invalid filename: %r", raw_filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename"
        )

    upload_id = uuid.uuid4().hex
    upload_dir = DOWNLOAD_ROOT / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_location = upload_dir / safe_name

    if (
        upload_dir not in file_location.resolve().parents
        and file_location.resolve() != upload_dir
    ):
        logger.warning("Rejected path traversal attempt: %r", raw_filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename"
        )

    try:
        async with aiofiles.open(file_location, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                await buffer.write(chunk)
    except OSError:
        logger.exception("Failed to write uploaded file to %s", file_location)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed"
        )
    finally:
        await file.close()

    logger.info("Uploaded file %s -> %s", safe_name, upload_id)

    ip_or_domain = config.get("IP_OR_DOMAIN")
    cdn_path = config.get("CDN_PATH")

    return {
        "file_location": f"{ip_or_domain}{quote(cdn_path)}/{quote(upload_id)}/{quote(safe_name)}"
    }
