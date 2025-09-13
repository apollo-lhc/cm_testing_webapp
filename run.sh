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

: "${IPADDR:="172.31.5.80"}"
SVC_OPTS="--bind=${IPADDR}:5001 --workers=${GUNICORN_WORKERS:-2} --threads=${GUNICORN_THREADS:-2} --timeout=${GUNICORN_TIMEOUT:-120} --graceful-timeout=${GUNICORN_GRACEFUL_TIMEOUT:-30}"

ensure_venv () {
	if [ ! -x "${VENV_DIR}/bin/python3" ]; then
		echo "Virtual environment not found at ${VENV_DIR}."
		printf "Would you like to create it now? [Y/N]: "
		read ans
		case "$ans" in
			[yY]*)
				echo "Creating virtual environment at ${VENV_DIR}..."
				python3 -m venv "${VENV_DIR}" || {
					echo "Failed to create venv at ${VENV_DIR}"
					return 1
				}
				# Upgrade pip and install requirements
				"${VENV_DIR}/bin/pip" install --upgrade pip
				"${VENV_DIR}/bin/pip" install \
					Flask==3.0.2 \
					Flask-SQLAlchemy==3.1.1 \
					Werkzeug==3.0.1 \
					gunicorn==23.0.0 || {
					echo "Failed to install required packages"
					return 1
				}
				echo "Virtual environment created and packages installed."
				;;
			*)
				echo "Aborting start: virtual environment is required."
				return 1
				;;
		esac
	fi
	return 0
}

cm_webapp_start () {
	echo "Starting cm_webapp"

	# Ensure venv exists
	ensure_venv || return 1

	# Ensure required directories exist (minimal changes)
	mkdir -p ./data
	mkdir -p "${BASE_DIR}/cm_webapp"
	mkdir -p "${LOG_DIR}/cm_webapp-status"

	# Generate 64-character hex key
	# (Reuse existing key if present; only generate on first run)
	if [ -f "./data/$KEY_FILE" ]; then
		SECRET_KEY=$(cat "./data/$KEY_FILE")
	else
		SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))") || {
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
	
	cd "${BASE_DIR}/cm_webapp" || {
		echo "Directory ${BASE_DIR}/cm_webapp not found"; return 1;
	}

	# Verify virtual environment and gunicorn exist
	if [ ! -x "${VENV_DIR}/bin/gunicorn" ]; then
		echo "Gunicorn not found at ${VENV_DIR}/bin/gunicorn."
		return 1
	fi

	# Prepare log files
	ACCESS_LOG="${LOG_DIR}/cm_webapp-status/access.log"
	ERROR_LOG="${LOG_DIR}/cm_webapp-status/error.log"
	STARTUP_LOG="${LOG_DIR}/cm_webapp-status/startup.log"
	PID_FILE="${BASE_DIR}/cm_webapp/gunicorn.pid"

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
		echo "Failed to start cm_webapp. Check $STARTUP_LOG"
		return 1
	fi
}

cm_webapp_stop () {
	echo "Stopping cm_webapp"
	PID_FILE="${BASE_DIR}/cm_webapp/gunicorn.pid"
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
