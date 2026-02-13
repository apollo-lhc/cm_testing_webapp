#!/bin/sh
# Run script for Apollo CM testing Web app (no conda)
# Usage: ./run.sh start|stop|restart
# Creates/checks a Python venv from environment.yml (or requirements.txt),
# detects drift, and runs Gunicorn.

set -eu

# --------- Paths & defaults ----------
: "${BASE_DIR:=/nfs/cms/tracktrigger/cm_testing_webapp_run}"
LOG_DIR="${BASE_DIR}/log"
VENV_DIR="${BASE_DIR}/.venv"
SPEC_CACHE="${BASE_DIR}/.venv_spec.txt"          # cached pip-style spec generated from environment.yml
KEY_FILE="flask_secret_key"

# Network bind
: "${IPADDR:=0.0.0.0}"
: "${PORT:=5002}"
SVC_OPTS="--bind=${IPADDR}:${PORT} --workers=${GUNICORN_WORKERS:-2} --threads=${GUNICORN_THREADS:-2} --timeout=${GUNICORN_TIMEOUT:-120} --graceful-timeout=${GUNICORN_GRACEFUL_TIMEOUT:-30}"

# --------- Helpers ----------
err() { echo "[$(date)] ERROR: $*" >&2; }
info() { echo "[$(date)] $*"; }

check_bind_ip() {
  if [ "$IPADDR" = "0.0.0.0" ] || [ "$IPADDR" = "127.0.0.1" ] || [ -z "$IPADDR" ]; then return 0; fi
  if ip -o -4 addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$IPADDR"; then
    return 0
  else
    err "$IPADDR not on any interface. Use one of:"
    ip -o -4 addr show | awk '{print $4, $NF}' | sed 's:/[0-9]\+::'
    exit 1
  fi
}

find_env_yml() {
  if [ -f "${BASE_DIR}/environment.yml" ]; then printf '%s' "${BASE_DIR}/environment.yml"; return 0; fi
  if [ -f "./environment.yml" ]; then printf '%s' "./environment.yml"; return 0; fi
  return 1
}

find_requirements_txt() {
  if [ -f "${BASE_DIR}/requirements.txt" ]; then printf '%s' "${BASE_DIR}/requirements.txt"; return 0; fi
  if [ -f "./requirements.txt" ]; then printf '%s' "./requirements.txt"; return 0; fi
  return 1
}

# Parse environment.yml -> produce a pip-style spec in ${SPEC_CACHE}
gen_spec_from_env_yml() {
  ENV_YML="$1"
  PY_PIN=""
  : > "${SPEC_CACHE}"
  awk '
    BEGIN { deps=0 }
    /^\s*dependencies\s*:\s*$/ { deps=1; next }
    deps==1 && /^\s*-\s*/ {
      line=$0
      gsub(/^\s*-\s*/, "", line)
      if (line ~ /^pip(\s*$|[[:space:]=].*$)/) next
      gsub(/=/, "==", line)
      print line
    }
  ' "${ENV_YML}" | sed '/^\s*$/d' > "${SPEC_CACHE}"

  PY_PIN=$(awk -F'==' '/^python==/ {print $2; exit}' "${SPEC_CACHE}" || true)
  sed -i.bak '/^python==/d' "${SPEC_CACHE}" 2>/dev/null || true
  rm -f "${SPEC_CACHE}.bak"

  if [ ! -s "${SPEC_CACHE}" ]; then
    cat >> "${SPEC_CACHE}" <<'EOF'
Flask==3.0.2
Flask-SQLAlchemy==3.1.1
Werkzeug==3.0.1
gunicorn==23.0.0
EOF
  fi

  printf '%s' "${PY_PIN}"
}

# ------- UPDATED: pyenv-aware interpreter selection -------
select_python() {
  REQ="$1"  # e.g. "3.12" or ""
  # 1) explicit override
  if [ -n "${PYTHON_BIN:-}" ] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    v=$("$PYTHON_BIN" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "")
    if [ -z "$REQ" ] || [ "$v" = "$REQ" ]; then printf '%s' "$PYTHON_BIN"; return 0; fi
  fi

  # 2) pyenv exact match (e.g., 3.12.5) or any 3.12.*
  if command -v pyenv >/dev/null 2>&1; then
    if [ -n "$REQ" ]; then
      # Try an exact 3.12.5 first if user has it (common on your box)
      for pv in "${REQ}.5" "${REQ}.0" "$REQ"; do
        if pyenv prefix "$pv" >/dev/null 2>&1; then
          bin="$(pyenv prefix "$pv")/bin/python"
          if [ -x "$bin" ]; then
            v=$("$bin" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "")
            if [ "$v" = "$REQ" ]; then printf '%s' "$bin"; return 0; fi
          fi
        fi
      done
      # Fallback: first pyenv version that starts with REQ (e.g., 3.12.5)
      pv="$(pyenv versions --bare | awk -v r="^${REQ}" '$0 ~ r {print; exit}')"
      if [ -n "$pv" ] && pyenv prefix "$pv" >/dev/null 2>&1; then
        bin="$(pyenv prefix "$pv")/bin/python"
        if [ -x "$bin" ]; then
          v=$("$bin" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "")
          if [ "$v" = "$REQ" ]; then printf '%s' "$bin"; return 0; fi
        fi
      fi
      # As a last pyenv convenience, try the common path if it exists
      if [ -x "$HOME/.pyenv/versions/${REQ}.5/bin/python" ]; then
        bin="$HOME/.pyenv/versions/${REQ}.5/bin/python"
        v=$("$bin" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "")
        if [ "$v" = "$REQ" ]; then printf '%s' "$bin"; return 0; fi
      fi
    fi
  fi

  # 3) system pythons
  candidates=""
  if [ -n "$REQ" ]; then candidates="python${REQ}"; fi
  candidates="$candidates python3.12 python3 python"
  for bin in $candidates; do
    if command -v "$bin" >/dev/null 2>&1; then
      v=$("$bin" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "")
      if [ -z "$REQ" ] || [ "$v" = "$REQ" ]; then printf '%s' "$bin"; return 0; fi
    fi
  done

  return 1
}

create_venv() {
  PYBIN="$1"
  info "Creating venv at ${VENV_DIR} with ${PYBIN}"
  "$PYBIN" -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null
}

install_spec() {
  if [ -s "${SPEC_CACHE}" ]; then
    info "Installing from spec (${SPEC_CACHE})"
    "${VENV_DIR}/bin/pip" install -r "${SPEC_CACHE}"
  else
    REQ_TXT="$(find_requirements_txt || true)"
    if [ -n "${REQ_TXT}" ]; then
      info "Installing from requirements (${REQ_TXT})"
      "${VENV_DIR}/bin/pip" install -r "${REQ_TXT}"
    else
      err "No dependency spec found (neither SPEC_CACHE nor requirements.txt)."
      return 1
    fi
  fi
}

compare_env_to_spec() {
  if [ ! -x "${VENV_DIR}/bin/pip" ]; then return 2; fi
  if [ ! -s "${SPEC_CACHE}" ]; then
    REQ_TXT="$(find_requirements_txt || true)"
    if [ -n "${REQ_TXT}" ]; then
      SPEC_FILE="$REQ_TXT"
    else
      return 2
    fi
  else
    SPEC_FILE="${SPEC_CACHE}"
  fi

  DRIFT=0
  while IFS= read -r line; do
    case "$line" in ""|\#*) continue ;; esac
    pkg=$(printf '%s' "$line" | cut -d'=' -f1)
    exp=$(printf '%s' "$line" | awk -F'==' '{print $2}')
    if [ -z "$pkg" ] || [ -z "$exp" ]; then continue; fi
    got=$("${VENV_DIR}/bin/python" -m pip show "$pkg" 2>/dev/null | awk -F': ' '/^Version:/{print $2; exit}' || true)
    if [ -z "$got" ] || [ "$got" != "$exp" ]; then
      echo "  - Drift: $pkg expected $exp, got ${got:-<not installed>}"
      DRIFT=1
    fi
  done < "$SPEC_FILE"

  return $DRIFT
}

ensure_secret_key() {
  mkdir -p ./data
  if [ -f "./data/$KEY_FILE" ]; then
    SECRET_KEY=$(cat "./data/$KEY_FILE")
  else
    SECRET_KEY=$("${VENV_DIR}/bin/python" -c "import secrets; print(secrets.token_hex(32))")
    echo "$SECRET_KEY" > "./data/$KEY_FILE"
    chmod 600 "./data/$KEY_FILE"
    info "Saved new FLASK_SECRET_KEY to ./data/$KEY_FILE"
  fi
  export FLASK_SECRET_KEY="$SECRET_KEY"
}

ensure_venv() {
  ENV_YML="$(find_env_yml || true)"
  PY_REQ=""
  if [ -n "$ENV_YML" ]; then
    PY_REQ="$(gen_spec_from_env_yml "$ENV_YML")"
    [ -n "$PY_REQ" ] && info "Detected Python pin: ${PY_REQ}"
  else
    if ! find_requirements_txt >/dev/null 2>&1; then
      err "No environment.yml or requirements.txt found."
      return 1
    fi
  fi

  PYBIN="$(select_python "$PY_REQ" || true)"
  if [ -z "$PYBIN" ]; then
    err "Could not find a python interpreter matching ${PY_REQ:-<any>}.
Hint: set PYTHON_BIN=/home/lap284/.pyenv/versions/3.12.5/bin/python or install python${PY_REQ}."
    return 1
  fi
  info "Using Python: $("$PYBIN" -V)"

  if [ ! -x "${VENV_DIR}/bin/python" ]; then
    create_venv "$PYBIN"
    # fail-fast guard in case wrong interpreter slipped in
    VVER="$("${VENV_DIR}/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
    if [ -n "${PY_REQ:-}" ] && [ "$VVER" != "$PY_REQ" ]; then
      err "Venv python ($VVER) does not match required ${PY_REQ}. Check PYTHON_BIN/pyenv."
      return 1
    fi
    install_spec || return 1
  else
    if ! "${VENV_DIR}/bin/python" -c "import zoneinfo" >/dev/null 2>&1; then
      err "Incompatible Python in ${VENV_DIR} (missing zoneinfo). Recreating."
      rm -rf "${VENV_DIR}"
      create_venv "$PYBIN"
      install_spec || return 1
    fi
  fi

  COMP_OK=2
  if compare_env_to_spec; then
    COMP_OK=0
  else
    COMP_OK=$?
  fi

  if [ $COMP_OK -eq 1 ]; then
    echo "Detected drift between ${VENV_DIR} and spec."
    printf "Reinstall to match spec? This will (re)install packages in %s. [Y/N]: " "$VENV_DIR"
    read -r ans
    case "$ans" in
      [yY]*) install_spec || return 1 ;;
      *)     echo "Continuing with existing env (not recommended)." ;;
    esac
  elif [ $COMP_OK -eq 2 ]; then
    echo "Warning: Skipping env drift check (no spec found or pip unavailable)."
  fi

  if [ ! -x "${VENV_DIR}/bin/gunicorn" ]; then
    err "gunicorn not found in venv; installing as per spec."
    install_spec || return 1
    [ -x "${VENV_DIR}/bin/gunicorn" ] || { err "gunicorn still missing."; return 1; }
  fi

  return 0
}

cm_webapp_start() {
  info "Starting cm_webapp"
  ensure_venv || exit 1
  check_bind_ip || exit 1

  mkdir -p "${LOG_DIR}/cm_webapp-status"
  cd "${BASE_DIR}" || { err "Directory ${BASE_DIR} not found"; exit 1; }
  export PYTHONPATH="${BASE_DIR}:${PYTHONPATH:-}"
  export PATH="${VENV_DIR}/bin:${PATH}"
  ensure_secret_key

  ACCESS_LOG="${LOG_DIR}/cm_webapp-status/access.log"
  ERROR_LOG="${LOG_DIR}/cm_webapp-status/error.log"
  STARTUP_LOG="${LOG_DIR}/cm_webapp-status/startup.log"
  PID_FILE="${BASE_DIR}/gunicorn.pid"

  if [ -f "$PID_FILE" ] && ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    info "Removing stale PID file at $PID_FILE"
    rm -f "$PID_FILE"
  fi

  nohup "${VENV_DIR}/bin/gunicorn" $SVC_OPTS \
    --pid "$PID_FILE" \
    --access-logfile "$ACCESS_LOG" \
    --error-logfile "$ERROR_LOG" \
    --log-level "${GUNICORN_LOG_LEVEL:-info}" \
    wsgi:app \
    >"$STARTUP_LOG" 2>&1 &

  sleep 1
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    info "cm_webapp started (PID $(cat "$PID_FILE")). Logs: $STARTUP_LOG"
    return 0
  else
    err "Failed to start cm_webapp. Check $STARTUP_LOG and $ERROR_LOG"
    return 1
  fi
}

cm_webapp_stop() {
  info "Stopping cm_webapp"
  PID_FILE="${BASE_DIR}/gunicorn.pid"
  if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE")
    if kill -TERM "$pid" 2>/dev/null; then
      for i in 1 2 3 4 5 6 7 8 9 10; do
        if kill -0 "$pid" 2>/dev/null; then sleep 1; else rm -f "$PID_FILE"; info "cm_webapp stopped"; return 0; fi
      done
      echo "Process did not exit gracefully; sending KILL"
      kill -KILL "$pid" 2>/dev/null || true
      rm -f "$PID_FILE"
      return 0
    else
      echo "Failed to signal process with PID $pid; removing stale PID file"
      rm -f "$PID_FILE"
      return 1
    fi
  else
    echo "PID file not found. Is the service running?"
    return 1
  fi
}

cm_webapp_restart() {
  info "Restarting cm_webapp"
  cm_webapp_stop || true
  sleep 2
  cm_webapp_start
}

case "${1:-}" in
  start)   cm_webapp_start ; exit $? ;;
  stop)    cm_webapp_stop  ; exit $? ;;
  restart) cm_webapp_restart ; exit $? ;;
  *)       echo "Usage: $0 start|stop|restart" ; exit 2 ;;
esac
