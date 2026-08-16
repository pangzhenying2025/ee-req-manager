"""LAN collaboration primitives for EE-Req Manager.

The module deliberately contains no Streamlit calls so locking and presence can
be tested with independent sessions and reused by every editing surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from db import CollaborationSession, EditLock

ACTIVE_WINDOW_SECONDS = 35
LOCK_TTL_SECONDS = 300
STALE_SESSION_HOURS = 24


@dataclass(frozen=True)
class LockResult:
    acquired: bool
    owner_name: str
    owner_session_id: str
    expires_at: datetime


def utcnow() -> datetime:
    # SQLAlchemy stores these timestamps as naive UTC values in SQLite.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def touch_session(
    db,
    *,
    session_id: str,
    user_name: str,
    project_id: int,
    page_name: str = "",
    ip_address: str = "",
    now: datetime | None = None,
) -> CollaborationSession:
    """Create or refresh one browser presence record."""
    now = now or utcnow()
    row = db.get(CollaborationSession, session_id)
    if row is None:
        row = CollaborationSession(
            session_id=session_id,
            user_name=user_name,
            project_id=project_id,
            page_name=page_name,
            ip_address=ip_address,
            started_at=now,
            last_seen_at=now,
        )
        db.add(row)
    else:
        row.user_name = user_name
        row.project_id = project_id
        row.page_name = page_name
        row.ip_address = ip_address
        row.last_seen_at = now
    db.query(EditLock).filter(
        EditLock.session_id == session_id,
        EditLock.expires_at > now,
    ).update({EditLock.user_name: user_name}, synchronize_session=False)
    db.query(EditLock).filter(EditLock.expires_at <= now).delete(
        synchronize_session=False
    )
    db.query(CollaborationSession).filter(
        CollaborationSession.last_seen_at < now - timedelta(hours=STALE_SESSION_HOURS),
    ).delete(synchronize_session=False)
    db.commit()
    return row


def active_sessions(
    db, project_id: int, now: datetime | None = None
) -> list[CollaborationSession]:
    now = now or utcnow()
    cutoff = now - timedelta(seconds=ACTIVE_WINDOW_SECONDS)
    return db.query(CollaborationSession).filter(
        CollaborationSession.project_id == project_id,
        CollaborationSession.last_seen_at >= cutoff,
    ).order_by(CollaborationSession.user_name, CollaborationSession.session_id).all()


def acquire_lock(
    db,
    *,
    project_id: int,
    artifact_type: str,
    artifact_id: int,
    session_id: str,
    user_name: str,
    now: datetime | None = None,
    ttl_seconds: int = LOCK_TTL_SECONDS,
) -> LockResult:
    """Acquire an artifact edit lock, reclaiming it only after expiration."""
    now = now or utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)
    row = db.query(EditLock).filter_by(
        project_id=project_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
    ).first()
    if row is not None and row.expires_at > now and row.session_id != session_id:
        return LockResult(False, row.user_name, row.session_id, row.expires_at)
    if row is None:
        row = EditLock(
            project_id=project_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            session_id=session_id,
            user_name=user_name,
            acquired_at=now,
            expires_at=expires_at,
            updated_at=now,
        )
        db.add(row)
    else:
        row.session_id = session_id
        row.user_name = user_name
        row.acquired_at = now
        row.expires_at = expires_at
        row.updated_at = now
    try:
        db.commit()
        return LockResult(True, user_name, session_id, expires_at)
    except IntegrityError:
        db.rollback()
        winner = db.query(EditLock).filter_by(
            project_id=project_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
        ).first()
        if winner is None:
            raise
        return LockResult(False, winner.user_name, winner.session_id, winner.expires_at)


def current_lock(
    db,
    *,
    project_id: int,
    artifact_type: str,
    artifact_id: int,
    now: datetime | None = None,
) -> EditLock | None:
    now = now or utcnow()
    row = db.query(EditLock).filter_by(
        project_id=project_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
    ).first()
    if row is not None and row.expires_at <= now:
        db.delete(row)
        db.commit()
        return None
    return row


def owns_lock(
    db,
    *,
    project_id: int,
    artifact_type: str,
    artifact_id: int,
    session_id: str,
    refresh: bool = False,
    now: datetime | None = None,
) -> bool:
    now = now or utcnow()
    row = current_lock(
        db,
        project_id=project_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        now=now,
    )
    if row is None or row.session_id != session_id:
        return False
    if refresh:
        row.expires_at = now + timedelta(seconds=LOCK_TTL_SECONDS)
        row.updated_at = now
        db.commit()
    return True


def release_lock(
    db,
    *,
    project_id: int,
    artifact_type: str,
    artifact_id: int,
    session_id: str,
) -> bool:
    deleted = db.query(EditLock).filter_by(
        project_id=project_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        session_id=session_id,
    ).delete(synchronize_session=False)
    db.commit()
    return bool(deleted)
