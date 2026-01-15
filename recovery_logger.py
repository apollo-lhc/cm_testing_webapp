# recovery_logger.py
# OSRS Recovery System - Flask webapp recovery logging
from __future__ import annotations

import traceback
from typing import Optional

from flask import request, session as flask_session
from sqlalchemy.orm import sessionmaker
from werkzeug.datastructures import MultiDict, FileStorage


from models import db, AuditEvent
from utils import current_user

# ===== HELPERS =====

def _multidict_to_plain_dict(md: MultiDict) -> dict:
    """
    Convert a MultiDict (e.g. request.form) into a plain dict.
    If a key has multiple values, keep the list.
    """
    out = {}
    for key in md.keys():
        values = md.getlist(key)
        if len(values) == 1:
            out[key] = values[0]
        else:
            out[key] = values
    return out

def _redact_form_payload(payload: dict) -> dict:
    """
    Redact sensitive keys and truncate large values.
    """
    REDACT_KEYS = {
        "password",
        "passwd",
        "token",
        "csrf_token",
        "secret",
        "api_key",
    }

    MAX_LEN = 500  # prevent megabyte logs

    clean = {}
    for k, v in payload.items():
        lk = k.lower()

        if any(rk in lk for rk in REDACT_KEYS):
            clean[k] = "<redacted>"
            continue

        if isinstance(v, str):
            clean[k] = v[:MAX_LEN]
        elif isinstance(v, list):
            clean[k] = [str(x)[:MAX_LEN] for x in v]
        else:
            clean[k] = str(v)[:MAX_LEN]

    return clean

def _files_metadata(files) -> dict:
    """
    Extract safe metadata from request.files.
    NEVER reads file contents.
    """
    meta = {}

    for field, fs in files.items():
        if not isinstance(fs, FileStorage):
            continue

        meta[field] = {
            "filename": fs.filename,
            "content_type": fs.content_type,
            "mimetype": fs.mimetype,
            "content_length": fs.content_length,
        }

    return meta



# ===== RECOVERY LOGGING =====
def make_recovery_session(app) -> sessionmaker:
    """Create a dedicated session factory bound ONLY to the recovery DB."""
    engine = db.get_engine(app, bind="recovery")
    return sessionmaker(bind=engine)


def log_recovery_event(
    RecoverySession: sessionmaker,
    *,
    form_index: Optional[int] = None,
    expected_keys: Optional[list[str]] = None,
    entry_id: Optional[int] = None,
    cm_serial: Optional[str] = None,
    error: Optional[str] = None,
) -> Optional[str]:
    """
    Writes a recovery record to recovery.db and returns event_uuid (or None on failure).
    Never raises.
    """
    try:
        user = current_user()
        username = getattr(user, "username", None) if user else None
        user_id = flask_session.get("user_id")

        # request context
        path = request.path
        method = request.method
        query_args = request.args.to_dict(flat=True)

        remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr)
        user_agent = (request.user_agent.string if request.user_agent else None)

        # form payload
        raw_form = _multidict_to_plain_dict(request.form)
        form_payload = _redact_form_payload(raw_form)

        # file metadata (NOT file contents)
        files_payload = _files_metadata(request.files)

        # expected/missing/unexpected
        expected_keys = expected_keys or []
        got_keys = set(form_payload.keys())
        expected_set = set(expected_keys)

        missing_expected = sorted(list(expected_set - got_keys))
        unexpected_keys = sorted(list(got_keys - expected_set))

        # session snapshot
        session_snapshot = {}
        for k in list(flask_session.keys()):
            v = flask_session.get(k)
            if isinstance(v, (str, int, float, bool)) or v is None:
                session_snapshot[k] = v
            else:
                session_snapshot[k] = str(v)[:500]

        rec = AuditEvent(
            username=username,
            user_id=user_id,
            path=path,
            method=method,
            query_args=query_args,
            remote_addr=remote_addr,
            user_agent=user_agent,
            form_index=form_index,
            expected_keys=expected_keys,
            missing_expected=missing_expected,
            unexpected_keys=unexpected_keys,
            form_payload=form_payload,
            files_payload=files_payload,
            session_snapshot=session_snapshot,
            entry_id=entry_id,
            cm_serial=cm_serial,
            error=error,
        )

        rs = RecoverySession()
        rs.add(rec)
        rs.commit()
        event_uuid = rec.event_uuid
        rs.close()
        return event_uuid

    except Exception:
        # never break the main request
        return None


def init_recovery(app) -> None:
    """
    Capture ALL incoming /form POST payloads BEFORE route logic runs.
    Also attach traceback info if the request crashes.
    """
    RecoverySession = make_recovery_session(app)

    @app.before_request
    def _recovery_before_request():
        # Only log real form submissions
        if request.method != "POST":
            return
        if request.path != "/form":
            return

        try:
            user = current_user()
            username = getattr(user, "username", None) if user else None
            user_id = flask_session.get("user_id")

            raw_form = _multidict_to_plain_dict(request.form)

            action = raw_form.get("action")
            if action not in {None, "save", "next", "finish", "fail"}:
                return

            rec = AuditEvent(
                username=username,
                user_id=user_id,
                path=request.path,
                method=request.method,
                query_args=request.args.to_dict(flat=True),
                remote_addr=request.headers.get(
                    "X-Forwarded-For", request.remote_addr
                ),
                user_agent=request.user_agent.string if request.user_agent else None,

                raw_form_payload=raw_form,
                form_payload=_redact_form_payload(raw_form),
                files_payload=_files_metadata(request.files),

                session_snapshot={
                    k: (
                        flask_session.get(k)
                        if isinstance(flask_session.get(k), (str, int, float, bool))
                        else str(flask_session.get(k))[:500]
                    )
                    for k in flask_session.keys()
                },

                cm_serial=raw_form.get("CM_serial")
                or raw_form.get("cm_serial"),
            )

            rs = RecoverySession()
            rs.add(rec)
            rs.commit()
            rs.close()

            flask_session["_recovery_event_id"] = rec.id

        except Exception:
            pass

    @app.teardown_request
    def _recovery_teardown(exc):
        if exc is None:
            return
        if request.method != "POST" or request.path != "/form":
            return

        event_id = flask_session.pop("_recovery_event_id", None)
        if not event_id:
            return

        try:
            tb = "".join(
                traceback.format_exception(
                    type(exc), exc, exc.__traceback__
                )
            )
            rs = RecoverySession()
            ev = rs.query(AuditEvent).get(event_id)
            if ev:
                ev.error = tb
                rs.commit()
            rs.close()
        except Exception:
            pass
