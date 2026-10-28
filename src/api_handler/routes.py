"""
All API routes for the SunCDN project.
"""

import logging
import os
import secrets
from pathlib import Path
from urllib.parse import quote

import aiofiles
from fastapi import Request, UploadFile, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import config
from src.api_handler.app import app
from src.api_handler.client_ip import get_client_ip
from src.api_handler import delete_links, quota

__all__ = [
    "root",
    "home",
    "faq",
    "create_upload_file",
    "delete_page",
    "delete_upload_file",
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


@app.get("/faq")
async def faq():
    """FAQ page: retention, upload limits, and data collection policy."""
    file_path = BASE_DIR / ".." / ".." / "faq.html"
    return FileResponse(file_path)


@app.post("/uploadfile/")
async def create_upload_file(request: Request, file: UploadFile):
    raw_filename = file.filename or ""
    safe_name = os.path.basename(raw_filename).strip()

    if not safe_name or safe_name in (".", ".."):
        logger.warning("Rejected upload with invalid filename: %r", raw_filename)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename"
        )

    client_ip = get_client_ip(request)
    max_file_size = config.get("MAX_FILE_SIZE", 200) * 1024 * 1024

    # Reject early using Content-Length when available, before touching disk.
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None

        if declared_size is not None:
            if declared_size > max_file_size:
                logger.warning(
                    "Rejected upload from %s: declared size %d exceeds MAX_FILE_SIZE",
                    client_ip,
                    declared_size,
                )
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File exceeds maximum allowed size",
                )

            allowed, reason = quota.check_quota(client_ip, declared_size)
            if not allowed:
                logger.warning(
                    "Rejected upload from %s: %s", client_ip, reason
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=reason
                )

    upload_id = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(8))
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

    written_bytes = 0
    try:
        async with aiofiles.open(file_location, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                written_bytes += len(chunk)
                # Backstop in case Content-Length was absent/wrong: abort once
                # the actual bytes written exceed the max size.
                if written_bytes > max_file_size:
                    logger.warning(
                        "Aborting upload from %s: exceeded MAX_FILE_SIZE mid-stream",
                        client_ip,
                    )
                    await buffer.close()
                    file_location.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File exceeds maximum allowed size",
                    )
                await buffer.write(chunk)
    except OSError:
        logger.exception("Failed to write uploaded file to %s", file_location)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed"
        )
    finally:
        await file.close()

    # Content-Length was missing, so quota wasn't checked up front - check now
    # against the actual size, after the fact (best effort; file already on disk).
    if content_length is None:
        allowed, reason = quota.check_quota(client_ip, written_bytes)
        if not allowed:
            logger.warning(
                "Rejected upload from %s after write: %s", client_ip, reason
            )
            file_location.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=reason
            )

    quota.record_upload(client_ip, written_bytes)

    logger.info("Uploaded file %s -> %s (%d bytes)", safe_name, upload_id, written_bytes)

    ip_or_domain = config.get("IP_OR_DOMAIN")
    cdn_path = config.get("CDN_PATH")

    delete_token = delete_links.issue_token(upload_id)
    delete_base = config.get("DELETE_BASE_URL", "https://arda0.net/sun")

    return {
        "file_location": f"{ip_or_domain}{quote(cdn_path)}/{quote(upload_id)}/{quote(safe_name)}",
        "delete_location": f"{delete_base}/delete/{upload_id}/{delete_token}",
    }


_DELETE_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Delete file</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;
min-height:100vh;align-items:center;justify-content:center;margin:0;padding:16px}
.box{max-width:420px;text-align:center}
button{background:#dc2626;color:#fff;border:0;border-radius:8px;padding:12px 24px;
font-size:16px;font-weight:700;cursor:pointer}
button:disabled{opacity:.5}
</style></head><body><div class="box">
<h1>Delete this file?</h1>
<p>This removes the uploaded file from the CDN right now. It cannot be undone.</p>
<button id="b">Delete file</button>
<p id="m"></p></div>
<script>
document.getElementById('b').addEventListener('click', async (e) => {
  e.target.disabled = true;
  const r = await fetch(location.pathname, {method: 'DELETE'});
  document.getElementById('m').textContent =
    r.ok ? 'Deleted.' : 'Link is not valid (already deleted or expired).';
  if (r.ok) e.target.remove(); else e.target.disabled = false;
});
</script></body></html>"""

_NO_LEAK = {"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


@app.get("/delete/{upload_id}/{token}", response_class=HTMLResponse)
async def delete_page(upload_id: str, token: str):
    """Confirm page only - a GET never deletes (link previews/prefetchers must be harmless)."""
    if not delete_links.token_matches(upload_id, token):
        raise HTTPException(status_code=404, detail="Not found")
    return HTMLResponse(_DELETE_PAGE, headers=_NO_LEAK)


@app.delete("/delete/{upload_id}/{token}")
async def delete_upload_file(upload_id: str, token: str):
    """Deletes the upload. Wrong id and wrong token both give the same 404."""
    if not delete_links.delete_upload(upload_id, token):
        raise HTTPException(status_code=404, detail="Not found")
    return JSONResponse({"ok": True}, headers=_NO_LEAK)
