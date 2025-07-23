"""
constants.py

Defines shared configuration constants used across the Flask web application.

Constants:
- SERIAL_OFFSET: Starting serial number used to align form index mapping with CM serials.
- SERIAL_MIN: Minimum valid CM serial number (same as SERIAL_OFFSET).
- SERIAL_MAX: Maximum valid CM serial number.
- LOCK_TIMEOUT: Duration after which a form lock is considered expired and can be reassigned.
"""

from datetime import timedelta


# Constants
SERIAL_OFFSET = 3000 # to prevent wasting memory make this the first serial number so 'forms_per_serial'[0] maps to CM3000
SERIAL_MAX = 3050
SERIAL_MIN = SERIAL_OFFSET
LOCK_TIMEOUT = timedelta(minutes=20)   # how long before a stale lock is considered free
