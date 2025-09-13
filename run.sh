#! /bin/sh
# Makefile for Apollo CM testing Web app, with inspiration from chess-status
# run with ./run.sh start|stop !
# Intended to be run _outside_ a Docker container, to start/stop the web app
# Uses Gunicorn to run the Flask app, with a default configuration

# Set BASE_DIR to default if not already set
: "${BASE_DIR:=/nfs/cms/tracktrigger/cm_testing_webapp_run}"
LOG_DIR="${BASE_DIR}/log"
VENV_DIR="${BASE_DIR}/.venv"

# set secret key file
KEY_FILE="flask_secret_key"

#switch ip after figuring out why it breaks
#: "${IPADDR:="127.0.0.1"}"
: "${IPADDR:="172.31.5.80"}"
: "${PORT:="5001"}"
SVC_OPTS="--bind=${IPADDR}:${PORT} --workers=${GUNICORN_WORKERS:-2} --threads=${GUNICORN_THREADS:-2} --timeout=${GUNICORN_TIMEOUT:-120} --graceful-timeout=${GUNICORN_GRACEFUL_TIMEOUT:-30}"

ensure_venv () {
	# If the prefix env doesn't exist, offer to create it with conda
	if [ ! -x "${VENV_DIR}/bin/python" ]; then
		echo "Virtual environment (Conda prefix) not found at ${VENV_DIR}."
		if ! command -v conda >/dev/null 2>&1; then
			echo "Error: 'conda' command not found. Please install Conda (or Mamba) and re-run."
			return 1
		fi

		# Find environment.yml (prefer one in BASE_DIR)
		ENV_YML=""
		[ -f "${BASE_DIR}/environment.yml" ] && ENV_YML="${BASE_DIR}/environment.yml"
		[ -z "$ENV_YML" ] && [ -f "./environment.yml" ] && ENV_YML="./environment.yml"

		if [ -z "$ENV_YML" ]; then
			echo "Error: environment.yml not found in ${BASE_DIR} or current directory."
			return 1
		fi

		printf "Create Conda env from %s at prefix %s ? [Y/N]: " "$ENV_YML" "$VENV_DIR"
		read ans
		case "$ans" in
			[yY]*)
				echo "Creating Conda env at ${VENV_DIR} ..."
				conda env create -f "$ENV_YML" -p "${VENV_DIR}" || {
					echo "Failed to create Conda env at ${VENV_DIR}"
					return 1
				}
				;;
			*)
				echo "Aborting start: virtual environment is required."
				return 1
				;;
		esac
	fi

	# Sanity checks: ensure Python is usable and has zoneinfo (Python >= 3.9)
	if ! "${VENV_DIR}/bin/python" -c "import sys; import zoneinfo; print(sys.version)" >/dev/null 2>&1; then
		echo "Error: ${VENV_DIR} Python is missing 'zoneinfo' (need Python >= 3.9)."
		echo "If your environment.yml pins python=3.12, recreate the env:"
		echo "  rm -rf '${VENV_DIR}'"
		echo "  conda env create -f environment.yml -p '${VENV_DIR}'"
		return 1
	fi

	# Ensure gunicorn is installed in the prefix (environment.yml should include it)
	if [ ! -x "${VENV_DIR}/bin/gunicorn" ]; then
		echo "Error: gunicorn not found in ${VENV_DIR}/bin. Add it to environment.yml and recreate the env."
		return 1
	fi
	return 0
}

cm_webapp_start () {
	echo "Starting cm_webapp"

	# Ensure venv exists (Conda prefix) and is valid
	ensure_venv || return 1

	# Ensure required directories exist (minimal changes)
	mkdir -p ./data
	mkdir -p "${LOG_DIR}/cm_webapp-status"

	# Generate 64-character hex key
	# (Reuse existing key if present; only generate on first run)
	if [ -f "./data/$KEY_FILE" ]; then
		SECRET_KEY=$(cat "./data/$KEY_FILE")
	else
		SECRET_KEY=$("${VENV_DIR}/bin/python" -c "import secrets; print(secrets.token_hex(32))") || {
			echo "Failed to generate FLASK_SECRET_KEY"
			return 1
		}
		echo "$SECRET_KEY" > "./data/$KEY_FILE"
		chmod 600 "./data/$KEY_FILE"
		echo "Saved new FLASK_SECRET_KEY to ./data/$KEY_FILE"
	fi

	# Export it to the current shell environment
	export FLASK_SECRET_KEY="$SECRET_KEY"
	echo "FLASK_SECRET_KEY has been generated, saved to ./data/$KEY_FILE, and exported."
	
	# Work from base directory (wsgi.py lives here)
	cd "${BASE_DIR}" || {
	echo "Directory ${BASE_DIR} not found"; return 1;
	}

	# Make sure Python can import the app module(s) from BASE_DIR
	export PYTHONPATH="${BASE_DIR}:${PYTHONPATH}"
	# Prefer the env's bin on PATH for consistency
	export PATH="${VENV_DIR}/bin:${PATH}"

	# Verify gunicorn exists in prefix
	if [ ! -x "${VENV_DIR}/bin/gunicorn" ]; then
		echo "Gunicorn not found at ${VENV_DIR}/bin/gunicorn."
		return 1
	fi

	# Prepare log files and PID path (all under BASE_DIR now)
	ACCESS_LOG="${LOG_DIR}/cm_webapp-status/access.log"
	ERROR_LOG="${LOG_DIR}/cm_webapp-status/error.log"
	STARTUP_LOG="${LOG_DIR}/cm_webapp-status/startup.log"
	PID_FILE="${BASE_DIR}/gunicorn.pid"

	# If a stale PID file exists, remove it
	if [ -f "$PID_FILE" ] && ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
		echo "Removing stale PID file at $PID_FILE"
		rm -f "$PID_FILE"
	fi

	# Launch gunicorn (daemonized via nohup); let gunicorn write its own PID file
	nohup "${VENV_DIR}/bin/gunicorn" $SVC_OPTS \
		--pid "$PID_FILE" \
		--access-logfile "$ACCESS_LOG" \
		--error-logfile "$ERROR_LOG" \
		--log-level "${GUNICORN_LOG_LEVEL:-info}" \
		wsgi:app \
		>"$STARTUP_LOG" 2>&1 &

	# Confirm start
	sleep 1
	if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
		echo "cm_webapp started (PID $(cat "$PID_FILE")). Logs: $STARTUP_LOG"
		return 0
	else
		echo "Failed to start cm_webapp. Check $STARTUP_LOG and $ERROR_LOG"
		return 1
	fi
}

cm_webapp_stop () {
	echo "Stopping cm_webapp"
	PID_FILE="${BASE_DIR}/gunicorn.pid"
	if [ -f "$PID_FILE" ]; then
		pid=$(cat "$PID_FILE")
		if kill -TERM "$pid" 2>/dev/null; then
			# Wait up to ~10s for graceful shutdown
			for i in 1 2 3 4 5 6 7 8 9 10; do
				if kill -0 "$pid" 2>/dev/null; then
					sleep 1
				else
					rm -f "$PID_FILE"
					echo "cm_webapp stopped"
					return 0
				fi
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

cm_webapp_restart () {
	echo "Restarting cm_webapp"
	cm_webapp_stop
	sleep 2
	if [ $? -eq 0 ]; then
		cm_webapp_start
		return $?
	else
		return 1
	fi
}

echo "argument is $1"
case "$1" in
	start)		cm_webapp_start
			exit $?
			;;
	stop)		cm_webapp_stop
			exit $?
			;;
	restart)	cm_webapp_restart
			exit $?
			;;
	*)		echo "Usage: $0 start|stop|restart"
			exit 2
			;;
esac
