from datetime import timedelta


# Constants
SERIAL_OFFSET = 3000 # to prevent wasting memory make this the first serial number so 'forms_per_serial'[0] maps to CM3000
SERIAL_MAX = 3050
SERIAL_MIN = SERIAL_OFFSET
LOCK_TIMEOUT = timedelta(minutes=20)   # how long before a stale lock is considered free
