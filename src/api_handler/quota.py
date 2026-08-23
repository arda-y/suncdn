"""
Per-IP upload quota tracking (tiered: hourly + daily + weekly caps).

Uses a small SQLite database (via SQLAlchemy) to record every successful
upload's size, timestamp and source IP, then sums bytes over trailing
windows to decide whether a new upload should be allowed.
"""

import logging
import time
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Float, select, func
from sqlalchemy.orm import declarative_base, sessionmaker

import config

logger = logging.getLogger("uvicorn.error")

DB_PATH = Path("./mountpoint/quota.db").resolve()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", future=True)
Session = sessionmaker(bind=engine, future=True)
Base = declarative_base()

HOUR_SECONDS = 3600
DAY_SECONDS = 86400
WEEK_SECONDS = 7 * DAY_SECONDS


class UploadRecord(Base):
    """One row per successful upload: how many bytes, from which IP, when."""

    __tablename__ = "upload_records"

    id = Column(Integer, primary_key=True)
    ip = Column(String, nullable=False, index=True)
    bytes = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False, index=True)


Base.metadata.create_all(engine)


def _bytes_used_since(ip: str, since_ts: float) -> int:
    with Session() as session:
        total = session.execute(
            select(func.coalesce(func.sum(UploadRecord.bytes), 0)).where(
                UploadRecord.ip == ip, UploadRecord.timestamp >= since_ts
            )
        ).scalar_one()
    return int(total)


def check_quota(ip: str, incoming_bytes: int) -> tuple[bool, str]:
    """
    Returns (allowed, reason). reason is a human readable message when not allowed.

    Limits are read from config on every call (mirrors config.get's hot-reload style).
    """
    now = time.time()

    hourly_limit = config.get("HOURLY_UPLOAD_LIMIT_MB", 2048) * 1024 * 1024
    daily_limit = config.get("DAILY_UPLOAD_LIMIT_MB", 5120) * 1024 * 1024
    weekly_limit = config.get("WEEKLY_UPLOAD_LIMIT_MB", 10240) * 1024 * 1024

    used_this_hour = _bytes_used_since(ip, now - HOUR_SECONDS)
    if used_this_hour + incoming_bytes > hourly_limit:
        return False, "Hourly upload limit exceeded"

    used_today = _bytes_used_since(ip, now - DAY_SECONDS)
    if used_today + incoming_bytes > daily_limit:
        return False, "Daily upload limit exceeded"

    used_this_week = _bytes_used_since(ip, now - WEEK_SECONDS)
    if used_this_week + incoming_bytes > weekly_limit:
        return False, "Weekly upload limit exceeded"

    return True, ""


def record_upload(ip: str, size_bytes: int) -> None:
    with Session() as session:
        session.add(UploadRecord(ip=ip, bytes=size_bytes, timestamp=time.time()))
        session.commit()


ANONYMIZED_IP = "0.0.0.0"


def prune_old_records(older_than_seconds: float = WEEK_SECONDS) -> None:
    """
    Scrub the IP on rows past the widest quota window, but keep the row.

    Rows this old are already excluded from every quota check (hourly/daily/
    weekly windows all look back at most WEEK_SECONDS), so blanking the ip
    here has no effect on quota enforcement - it only satisfies "we don't
    keep your IP forever" while preserving upload history (bytes, timestamp)
    so past job volume is still visible later.
    """
    cutoff = time.time() - older_than_seconds
    with Session() as session:
        session.query(UploadRecord).filter(
            UploadRecord.timestamp < cutoff,
            UploadRecord.ip != ANONYMIZED_IP,
        ).update({UploadRecord.ip: ANONYMIZED_IP}, synchronize_session=False)
        session.commit()
