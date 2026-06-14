"""
All API routes for the SunCDN project.
"""

import os
import random
import shutil
from urllib.parse import quote

from fastapi import UploadFile, HTTPException
from fastapi import status
from fastapi.responses import FileResponse

import config
from src.api_handler.app import app

__all__ = [
    "root",
    "home",
    "create_upload_file",
]  # explicitly define the routes that should be registered to the FastAPI app


@app.get("/")
async def home():
    """Home route for the API."""
    # Ensure the path points to where your index.html is stored
    # Path.join helps avoid issues between Windows/Linux environments
    # index.html is at root dir, and this file is in src/api_handler, so we go up two levels
    file_path = os.path.join(os.path.dirname(__file__), "..", "..", "index.html")

    return FileResponse(file_path)


@app.get("/root")
async def root():
    """To check if the server is running without much hassle."""

    return {"message": "Hello World"}


@app.post("/uploadfile/")
async def create_upload_file(file: UploadFile):
    download_path = "./mountpoint/downloads"
    # it is already ensured in purge_old_files.py that the download directory exists
    random_string = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))

    if not os.path.exists(os.path.join(download_path, random_string)):
        os.makedirs(os.path.join(download_path, random_string))

    # Prevent path traversal via uploaded filename
    # Use basename to strip any path components, then remove any remaining separators
    raw_filename = file.filename or ""
    safe_name = os.path.basename(raw_filename)
    safe_name = safe_name.replace("/", "").replace("\\", "")
    if not safe_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    file_location = os.path.join(download_path, random_string, safe_name)

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file.file.close()

    ip_or_domain = config.get("IP_OR_DOMAIN")
    cdn_path = config.get("CDN_PATH")

    return {
        "file_location": f"{ip_or_domain}{quote(cdn_path)}/{quote(random_string)}/{quote(safe_name)}"
    }
