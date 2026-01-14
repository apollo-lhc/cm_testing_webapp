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
import math
from datetime import datetime
from pathlib import Path
from flask import session
from werkzeug.utils import secure_filename

from models import db, User, TestEntry
from form_config import FORMS_NON_DICT
from constants import LOCK_TIMEOUT, EASTERN_TZ, OPTIONAL_TEXT_KEYWORDS, REQUIRED_TYPES, ALLOWED_EXTS, EYESCAN_RE, DATE_RE, APOLLO_ROOT

fishy_users = {}

def is_field_required(field):
    """
    Returns True if this field is required to be filled.
    """

    # Skip non-form / non-history fields
    if not field.display_form or not field.display_history:
        return False

    if field.type_field in (None, "blank"):
        return False

    # Always required
    if field.type_field in REQUIRED_TYPES:
        return True

    # Conditional required: text fields
    if field.type_field == "text":
        name = (field.name or "").lower()
        label = (field.label or "").lower()

        if any(k in name for k in OPTIONAL_TEXT_KEYWORDS):
            return False
        if any(k in label for k in OPTIONAL_TEXT_KEYWORDS):
            return False

        return True

    return False

def page_is_complete(page, entry_data):
    """
    Page is complete if ALL required fields are valid.
    """

    required_fields = [f for f in page.fields if is_field_required(f)]
    if not required_fields:
        return False

    for field in required_fields:
        value = entry_data.get(field.name)
        valid, _ = validate_field_value(field, value, entry_data, required=True)
        if not valid:
            return False

    return True

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

def validate_field_value(field, value, data=None, *, required=None):
    """
    Validate a field value.
    - Required fields must be present
    - Optional fields are validated ONLY if a value is provided
    Returns (is_valid, error_message)
    """

    if required is None:
        required = is_field_required(field)

    # Normalize empty values
    empty = value in (None, "", [], {}, " ")

    # Custom validator ALWAYS runs if value exists
    if field.validate and not empty:
        valid, msg = field.validate(value)
        if not valid:
            return False, msg

    # Required check
    if required:
        if field.type_field == "file":
            existing = data.get(field.name) if data else None
            if not value and not existing:
                return False, "File is required."
        else:
            if empty:
                return False, "This field is required."

    # If optional and empty → skip type validation
    if empty:
        return True, ""

    # Type validation (only when value exists)
    if field.type_field == "integer":
        try:
            int(value)
        except ValueError:
            return False, "Must be an integer."

    elif field.type_field == "float":
        try:
            float(value)
        except ValueError:
            return False, "Must be a number."

    elif field.type_field == "boolean":
        if value not in ("yes", "no"):
            return False, "Please select yes or no."

    elif field.type_field == "file":
        # file exists → OK
        pass

    return True, ""

def validate_form(fields, req, data=None):
    """
    Validate all fields in the form.
    Returns (is_valid, errors_dict).
    """
    errors = {}

    for field in fields:
        if field.type_field == "file":
            file = req.files.get(field.name)
            value = file.filename if file and file.filename else None
        else:
            value = req.form.get(field.name)

        valid, msg = validate_field_value(field, value, data)
        if not valid:
            errors[field.name] = msg

    # if(len(errors) > 0):
    #     print(f"Form validation errors: {errors}")

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

# ==== EYESCAN VIS BROWSING HELPERS ====

def _safe_under(root: Path, rel: str):
    rel = (rel or "").strip()
    if rel.startswith(("/", "\\")) or ".." in rel:
        raise ValueError("invalid rel path")
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise ValueError("escapes root")
    return p

def _list_serial_dirs():
    """
    List directories under APOLLO_ROOT that have a 'scans' subdirectory.
    This matches your pattern: APOLLO_ROOT/CM3006/scans/...
    """
    out = []
    if not APOLLO_ROOT.exists():
        return out

    for d in APOLLO_ROOT.iterdir():
        if not d.is_dir():
            continue
        scans = d / "scans"
        if scans.exists() and scans.is_dir():
            out.append(d.name)

    return sorted(out, key=str.lower)

def _list_dates(serial_dir: str):
    scans_dir = _safe_under(APOLLO_ROOT, f"{serial_dir}/scans")
    if not scans_dir.exists() or not scans_dir.is_dir():
        return []
    dates = [x.name for x in scans_dir.iterdir() if x.is_dir() and DATE_RE.match(x.name)]
    # sort by actual date string
    return sorted(dates, reverse=True)

def _parse_label_from_filename(fname: str):
    """
    Turn eyescan_F1_1_Quad_121_X0Y4_to_F1_1_Quad_121_X0Y4.png
    into a compact label. We can refine later.
    """
    m = EYESCAN_RE.match(fname)
    if not m:
        return fname
    a = m.group("a")
    b = m.group("b")
    if a == b:
        return a.replace("_", " ")
    return f"{a.replace('_',' ')} → {b.replace('_',' ')}"

def _group_eyescan_artifacts(files):
    """
    Group png/pdf/csv of the same base scan into one card.
    """
    buckets = {}

    for f in files:
        p = Path(f)
        ext = p.suffix.lower()
        if ext not in ALLOWED_EXTS:
            continue

        m = EYESCAN_RE.match(p.name)
        if not m:
            continue

        base = p.stem
        if base not in buckets:
            buckets[base] = {
                "base": base,
                "label": _parse_label_from_filename(p.name),
                "png": None,
                "pdf": None,
                "csv": None,
            }

        if ext == ".png":
            buckets[base]["png"] = p.name
        elif ext == ".pdf":
            buckets[base]["pdf"] = p.name
        elif ext == ".csv":
            buckets[base]["csv"] = p.name

    items = list(buckets.values())
    items.sort(key=lambda x: x["label"].lower())
    return items

def _list_date_files(serial_dir: str, date: str):
    date_dir = _safe_under(APOLLO_ROOT, f"{serial_dir}/scans/{date}")
    if not date_dir.exists() or not date_dir.is_dir():
        return []
    return sorted([x.name for x in date_dir.iterdir() if x.is_file()])

# ====== FPGA Temp Vis Helpers ======

def parse_csv_floats(raw):
    """
    Parse comma-separated floats from form text.
    Accepts: "37, 41.3, 79, ..."
    Returns: [37.0, 41.3, 79.0]
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            try:
                fx = float(x)
                if not math.isnan(fx) and math.isfinite(fx):
                    out.append(fx)
            except Exception:
                continue
        return out

    s = str(raw).strip()
    if not s:
        return []

    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            fx = float(part)
            if math.isnan(fx) or not math.isfinite(fx):
                continue
            out.append(fx)
        except Exception:
            continue
    return out

def _entry_serial(entry) -> str:
    d = entry.data if isinstance(entry.data, dict) else {}
    serial = str(d.get("CM_serial", "")).strip()
    return serial

def _entry_fpga_temps(entry):
    d = entry.data if isinstance(entry.data, dict) else {}
    fpga1 = parse_csv_floats(d.get("link_test_fpga_temp_1"))
    fpga2 = parse_csv_floats(d.get("link_test_fpga_temp_2"))
    return fpga1, fpga2

def _summarize(series):
    if not series:
        return {"n": 0, "max": None, "avg": None}
    n = len(series)
    mx = max(series)
    avg = sum(series) / n
    return {"n": n, "max": mx, "avg": avg}

# ====== Power Test Vis Helpers ======

def _as_float(x):
    try:
        if x is None:
            return None
        if isinstance(x, bool):
            return None
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except (ValueError, TypeError):
        return None

def _entry_power_fields(e):
    """
    Pull scalar power-up-test fields from entry JSON:
      - management_power (mA)
      - power_supply_voltage (V)
      - current_draw (mA)
      - p_est_w = V * (mA/1000) if possible
    """
    d = e.data if isinstance(e.data, dict) else {}

    mgmt_ma = _as_float(d.get("management_power"))
    v = _as_float(d.get("power_supply_voltage"))
    i_ma = _as_float(d.get("current_draw"))

    p_est_w = None
    if v is not None and i_ma is not None:
        p_est_w = v * (i_ma / 1000.0)

    return {
        "management_power_ma": mgmt_ma,
        "power_supply_voltage_v": v,
        "current_draw_ma": i_ma,
        "p_est_w": p_est_w,
    }

def _has_any_power_data(p):
    return any(p.get(k) is not None for k in [
        "management_power_ma",
        "power_supply_voltage_v",
        "current_draw_ma",
        "p_est_w",
    ])
