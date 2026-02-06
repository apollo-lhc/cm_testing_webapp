"""
constants.py

Defines shared configuration constants used across the Flask web application.

Constants:
- SERIAL_OFFSET: Starting serial number used to align form index mapping with CM serials.
- SERIAL_MIN: Minimum valid CM serial number (same as SERIAL_OFFSET).
- SERIAL_MAX: Maximum valid CM serial number.
- LOCK_TIMEOUT: Duration after which a form lock is considered expired and can be reassigned.
- EASTERN_TZ: Timezone object for Eastern Time, used for date and time handling.
"""

import os
import re
from datetime import timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

# Constants
SERIAL_OFFSET = 3000 # to prevent wasting memory make this the first serial number so 'forms_per_serial'[0] maps to CM3000
SERIAL_MAX = 3050 # change these when we get different serial number bounds
SERIAL_MIN = SERIAL_OFFSET
LOCK_TIMEOUT = timedelta(minutes=20)   # how long before a stale lock is considered free (not implemented)

EASTERN_TZ = ZoneInfo("America/New_York")

OPTIONAL_TEXT_KEYWORDS = ("comment", "comments", "note", "notes", "text")
REQUIRED_TYPES = {"integer", "float", "boolean", "file"} # used for check if you are adding new types of form fields you need to add here if they need to be ignored

# ====== EYESCAN VIS BROWSING CONFIG ==========

APOLLO_ROOT = Path(os.environ.get(
    "APOLLO_ROOT",
    "/nfs/cms/tracktrigger/apollo"
)).resolve()

# "date folders" look like 11-14-25
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{2}$")

# Eyescan files are named like:
# eyescan_F1_1_Quad_121_X0Y4_to_F1_1_Quad_121_X0Y4.png
EYESCAN_RE = re.compile(
    r"^eyescan_(?P<a>.+?)_to_(?P<b>.+?)\.(?P<ext>png|pdf|csv)$",
    re.IGNORECASE
)

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_EXTS = IMG_EXTS | {".pdf", ".csv", ".txt", ".log", ".json"}
