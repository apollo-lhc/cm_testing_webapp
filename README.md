# Apollo CM Testing Webapp

A Flask + SQLite web application for logging Apollo Command Module (CM) test results via a **multi-step, dynamically configurable form** with **file uploads**, **history & CSV export**, **admin tooling**, and **visualization pages** (eyescan artifacts, FPGA temperature data, and power metrics).

This repository is designed to be maintainable by someone who did **not** originally write the code. This README explains **what exists**, **where logic lives**, and **how to safely extend it**.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Layout](#repository-layout)
- [Quickstart (Local Development)](#quickstart-local-development)
- [Docker Usage](#docker-usage)
- [Production Run Script](#production-run-script)
- [Authentication Model](#authentication-model)
- [Multi-Step Form System](#multi-step-form-system)
- [Form States & Retest Logic](#form-states--retest-logic)
- [Locking & Concurrency](#locking--concurrency)
- [File Upload System](#file-upload-system)
- [History, Detail View, CSV Export](#history-detail-view-csv-export)
- [Admin Functionality](#admin-functionality)
- [Visualization System](#visualization-system)
- [Common Update Tasks](#common-update-tasks)
- [Gotchas & Maintenance Notes](#gotchas--maintenance-notes)

---

## Architecture Overview

This application is a **Flask monolith** with clear internal separation.

### Core Files

| File | Purpose |
|-----|--------|
| `app.py` | Main Flask app: routing, auth, form flow, history, CSV export |
| `models.py` | SQLAlchemy models + `FormField` / `FormPage` abstractions |
| `form_config.py` | Loads/saves active form definition |
| `utils.py` | Shared helpers (validation, locking, uploads, filesystem parsing) |
| `admin_routes.py` | Admin-only routes |
| `admin_form_editor.py` | Admin GUI for editing form structure |
| `visualizaions.py` | Visualization blueprint (`/vis/*`) |
| `constants.py` | Serial bounds, regexes, filesystem rules |
| `recovery_logger.py` | Request/audit logging |
| `wsgi.py` | Gunicorn entrypoint |

---

## Repository Layout

```
cm_testing_webapp/
├── README.md
├── app.py
├── models.py
├── form_config.py
├── utils.py
├── constants.py
├── admin_routes.py
├── admin_form_editor.py
├── visualizaions.py
├── recovery_logger.py
├── wsgi.py
├── Dockerfile
├── run.sh
├── requirements.txt
├── templates/
├── static/
├── data/
│   ├── test.db
│   ├── users.db
│   ├── recovery.db
│   ├── presence.db
│   └── forms_config.json
└── uploads/
```

---

## Quickstart (Local Development)

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Required environment variable

The app will **not start** without this.

```bash
export FLASK_SECRET_KEY="your-long-random-secret"
```

### 3. Run

```bash
python app.py
```

Default port is typically **5001**.

---

## Docker Usage

### Build

```bash
docker build -t cm-testing-webapp .
```

### Run (Flask dev server)

```bash
docker run -p 5001:5001 \
  -e FLASK_SECRET_KEY="secret" \
  -v $(pwd)/uploads:/app/uploads \
  cm-testing-webapp
```

### Run (Gunicorn)

```bash
docker run -p 5001:5001 \
  -e SERVER_TYPE=gunicorn \
  -e FLASK_SECRET_KEY="secret" \
  -v $(pwd)/uploads:/app/uploads \
  cm-testing-webapp
```

Gunicorn behavior is configurable via:

- `GUNICORN_WORKERS`
- `GUNICORN_TIMEOUT`
- `GUNICORN_KEEPALIVE`

---

## Production Run Script

`run.sh` supports a non-Docker, production-style deployment.

It:
- creates or reuses a virtual environment
- runs Gunicorn
- reads a secret key from a file

Before using, adjust:
- `BASE_DIR`
- `PORT`
- secret key file location

---

## Authentication Model

### Users
- `/register`
- `/login`
- stored in `users.db`

### Password handling (important)

Passwords are:
- **SHA-256 hashed client-side**
- **PBKDF2 hashed server-side**

If modifying auth:
- `User.set_password()` expects a SHA-256 hash
- `User.check_password()` compares SHA-256 → PBKDF2

---

## Multi-Step Form System

### Core concept

Each test entry is collected through **ordered pages (steps)**.

- `FormPage`: page label + list of fields
- `FormField`: name, type, label, help text, validation rules

Defined in `models.py`.

### Persistence

Active form definition is stored in:

```
data/forms_config.json
```

If missing or invalid, defaults from `form_config.py` are used.

### Step 0 (Serial Number)

The first page is special:
- collects CM serial
- validated against bounds in `constants.py`
- checked for existing saved/failed entries

This step **must exist**.

---

## Form States & Retest Logic

Each `TestEntry` tracks:

| Field | Meaning |
|-----|--------|
| `is_saved` | User saved and exited |
| `is_finished` | Final submission |
| `failure` | Test failed |
| `fail_stored` | Failure pending retest |
| `fail_reason` | Text reason |
| `parent_id` | Retest linkage |

Routes manage:
- save & exit
- fail test
- retest
- clear failed submission

---

## Locking & Concurrency

Prevents multiple users editing the same entry.

### Key fields
- `User.form_id`
- `TestEntry.lock_owner`
- `TestEntry.lock_acquired_at`

### Helpers
- `acquire_lock()`
- `release_lock()`

Admins can clear stale locks.

---

## File Upload System

### Storage

Uploads live under:

```
uploads/
```

Typically organized by CM serial.

### Behavior
- filenames replaced with UUIDs
- metadata stored in `TestEntry.data`
- served via `/uploads/<path>`
- path traversal is blocked

---

## History, Detail View, CSV Export

### Features
- history list
- entry detail page
- CSV export

CSV export flattens stored JSON automatically.

If you rename fields, **verify CSV output**.

---

## Admin Functionality

Admin routes live under `/admin/*`.

### Features
- promote/demote users
- unlock stuck forms
- delete entries (with archival)
- inject dummy test data
- edit live form structure

Templates live in:

```
templates/admin/
```

---

## Visualization System

Mounted at:

```
/vis/*
```

Supports browsing:
- eyescan artifacts
- FPGA temperature data
- power metrics

Filesystem root:

```
APOLLO_ROOT=/nfs/cms/tracktrigger/apollo
```

Patterns & regex live in `constants.py`.

Filesystem parsing helpers are in `utils.py`.

---

## Common Update Tasks

### Add a new form field
1. Use admin form editor
2. Confirm validation in `utils.validate_form`
3. Check detail view + CSV export

### Add a new step
1. Add page via admin editor
2. Confirm step routing
3. Test resume behavior

### Add a visualization
1. Add route in `visualizaions.py`
2. Add template in `templates/vis`
3. Update filesystem helpers if needed

---

## Gotchas & Maintenance Notes

- `FLASK_SECRET_KEY` **must** be set
- `visualizaions.py` spelling is intentional
- `UserSession` has conflicting DB bind keys (likely bug)
- Serial bounds live in `constants.py`
