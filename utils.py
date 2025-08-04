"""
Utility functions for the Apollo CM Test Entry app.

Provides core helpers for:
- Validating individual fields and entire forms (`validate_field`, `validate_form`)
- Tracking incomplete form steps (`determine_step_from_data`)
- Managing locks on entries (`acquire_lock`, `release_lock`)
- Handling file uploads with unique names (`process_file_fields`)
- Retrieving the current user (`current_user`)
- Verifying admin access and logging suspicious attempts (`authenticate_admin`)

Also defines:
- `fishy_users`: Tracks users who attempt unauthorized admin access.

Dependencies: Flask `session`, SQLAlchemy `User` and `TestEntry` models, `FORMS_NON_DICT`, `LOCK_TIMEOUT`.
"""


import os
import re
from datetime import datetime
from flask import session
from werkzeug.utils import secure_filename

from models import db, User, TestEntry
from form_config import FORMS_NON_DICT
from constants import LOCK_TIMEOUT, EASTERN_TZ


fishy_users = {}

def validate_field(field, value, data=None):
    """Validate a single field value based on its type and requirements."""
    if field.validate:
        valid, msg = field.validate(value)
        if not valid:
            print(f"Validation failed for {field.name}: {msg} (value={value})")
            return False, msg

    if field.type_field == "integer":
        if value is None or value == "":
            return False, "This field is required."
        try:
            int(value)
        except ValueError:
            return False, "Must be an integer."
    elif field.type_field == "float":
        if value is None or value == "":
            return False, "This field is required."
        try:
            float(value)
        except ValueError:
            return False, "Must be a number."
    elif field.type_field == "boolean":
        if value not in ("yes", "no"):
            return False, "Please select yes or no."
    elif field.type_field == "file":
        existing = data.get(field.name) if data else None
        if not value and not existing:
            return False, "File is required."
    return True, ""

def validate_form(fields, req, data=None):
    """Validate all fields in the form. Returns (is_valid, errors_dict)."""
    errors = {}
    for field in fields:
        if field.type_field == "file":
            file = req.files.get(field.name)
            value = file.filename if file and file.filename else None
        else:
            value = req.form.get(field.name)
        valid, msg = validate_field(field, value, data)
        if not valid:
            errors[field.name] = msg
    return (len(errors) == 0), errors

def determine_step_from_data(data):
    """Return the index of the first incomplete page.
       If everything is filled, return len(FORMS_NON_DICT)."""
    data = data or {}
    for i, page in enumerate(FORMS_NON_DICT):
        for field in page["fields"]:
            fname = getattr(field, "name", None)   # FormField, not dict
            if fname and fname not in data:
                return i
    return len(FORMS_NON_DICT)

def acquire_lock(entry_id, username):
    """Try to claim the lock; returns (success_flag, entry)."""
    now = datetime.now(EASTERN_TZ)

    # ---- new WHERE clause (no imports needed) -----------------
    q = (
        TestEntry.query
        .filter(
            TestEntry.id == entry_id,                     # implicit AND
            (                                             # explicit OR via |
                TestEntry.lock_owner.is_(None) |          #   • lock is free
                (TestEntry.lock_acquired_at + LOCK_TIMEOUT == now)  # • or expired turned off rn,  fix this or implement it
            )
        )
    )
    # -----------------------------------------------------------

    updated = q.update(
        {"lock_owner": username, "lock_acquired_at": now},
        synchronize_session=False,
    )
    db.session.commit()
    return updated == 1, db.session.get(TestEntry, entry_id)

def release_lock(entry):
    """Free the lock on a TestEntry row that you already own."""
    entry.lock_owner = None
    entry.lock_acquired_at = None
    db.session.commit()

def process_file_fields(fields, rq, upload_folder, data):
    """Safely saves uploaded files with timestamped names inside a CM-specific subfolder.
    Ensures paths are safe and alphanumeric. Updates the data dictionary with relative paths."""

    updated_data = data.copy()

    for field in fields:
        if field.type_field == "file":
            file = rq.files.get(field.name)
            cm_serial = data.get("CM_serial")
            if not cm_serial:
                raise ValueError("CM Serial number is required for file uploads.")
            if not re.fullmatch(r"[A-Za-z0-9]+", cm_serial):
                raise ValueError("Invalid CM Serial number: must be alphanumeric.")

            # Safe subfolder name using alphanumeric check and prefix
            subfolder_name = f"CM{cm_serial}"
            subfolder_safe = secure_filename(subfolder_name)
            save_dir = os.path.abspath(os.path.join(upload_folder, subfolder_safe))

            # Ensure save_dir is within upload_folder
            upload_folder_abs = os.path.abspath(upload_folder)
            if not save_dir.startswith(upload_folder_abs):
                raise ValueError("Unsafe file path detected.")

            os.makedirs(save_dir, exist_ok=True)

            if file and file.filename:
                timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S-%f')
                safe_filename = secure_filename(file.filename)
                full_filename = f"{timestamp}_{safe_filename}"
                file_path = os.path.join(save_dir, full_filename)
                file.save(file_path)

                # Store relative path from upload_folder
                relative_path = os.path.join(subfolder_safe, full_filename)
                updated_data[field.name] = relative_path
            else:
                if field.name in data:
                    updated_data[field.name] = data[field.name]

    return updated_data

def current_user():
    uid = session.get("user_id")
    if uid is None:
        return None
    user = User.query.get(uid)
    if user is None:
        # Session is stale – user was deleted or DB reset
        session.pop("user_id", None)
    return user

def authenticate_admin():
    """Returns True if current user is admin, False otherwise.
    Logs non-admin or unauthenticated users to fishy_users."""
    user = current_user()
    if not user or not user.administrator:
        username = user.get_username() if user else "unknown"
        fishy_users[username] = fishy_users.get(username, 0) + 1
        return False
    return True
