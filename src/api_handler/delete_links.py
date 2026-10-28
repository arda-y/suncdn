"""
Delete ("termination") links for uploads. Each upload gets a random token; only its
SHA-256 hash is stored, in mountpoint/delete_tokens/<upload_id> - outside downloads/, so
nginx never serves it. Presenting the right token for an upload id removes the whole
upload folder. Wrong id and wrong token look identical to the caller (no id probing).
"""

import hashlib
import hmac
import logging
import re
import secrets
import shutil
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

DOWNLOAD_ROOT = Path("./mountpoint/downloads").resolve()
TOKEN_DIR = Path("./mountpoint/delete_tokens").resolve()

ID_RE = re.compile(r"^[a-z0-9]{8}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(upload_id: str) -> str:
    """Create and store a delete token for an upload; returns the plain token (shown once)."""
    token = secrets.token_urlsafe(24)
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    (TOKEN_DIR / upload_id).write_text(_hash(token), encoding="utf-8")
    return token


def token_matches(upload_id: str, token: str) -> bool:
    if not ID_RE.match(upload_id) or not TOKEN_RE.match(token):
        return False
    try:
        stored = (TOKEN_DIR / upload_id).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return hmac.compare_digest(stored, _hash(token))


def delete_upload(upload_id: str, token: str) -> bool:
    """Delete the upload if the token is right. False = nothing deleted."""
    if not token_matches(upload_id, token):
        return False
    shutil.rmtree(DOWNLOAD_ROOT / upload_id, ignore_errors=True)
    (TOKEN_DIR / upload_id).unlink(missing_ok=True)
    logger.info("Upload %s deleted via its delete link", upload_id)
    return True


def drop_orphan_tokens() -> None:
    """Remove token files whose upload folder is gone (expired or already deleted)."""
    if not TOKEN_DIR.is_dir():
        return
    for token_file in TOKEN_DIR.iterdir():
        if not (DOWNLOAD_ROOT / token_file.name).exists():
            token_file.unlink(missing_ok=True)
