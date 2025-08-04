#! /bin/sh
# Makefile for Apollo CM testing Web app, with inspiration from chess-status
# run with ./run.sh start|stop|restart|status|logs
# Intended to be run _outside_ a Docker container, to start/stop the web app
# Uses Gunicorn to run the Flask app, with a default configuration


# Set BASE_DIR to default if not already set
: "${BASE_DIR:=/nfs/cms/tracktrigger/cm_testing_webapp_run}"
LOG_DIR="${BASE_DIR}/log"

: "${IPADDR:="172.31.5.80"}"
SVC_OPTS="--bind=${IPADDR}:5001 --disable-redirect-access-to-syslog --log-syslog"


cm_webapp_start () {
	echo "Starting cm_webapp"
	cd ${BASE_DIR}/cm_webapp
	[ -d ${LOG_DIR} ] || mkdir ${LOG_DIR}
	nohup .venv/bin/python3 .venv/bin/gunicorn $SVC_OPTS wsgi:app \
		 >${LOG_DIR}/gunicorn.log 2>&1 &
	echo $! > ${BASE_DIR}/cm_webapp/gunicorn.pid
	return 0
}

cm_webapp_stop () {
	echo "Stopping cm_webapp"
	if [ -f ${BASE_DIR}/cm_webapp/gunicorn.pid ]; then
		pid=$(cat ${BASE_DIR}/cm_webapp/gunicorn.pid)
		if kill $pid; then
			rm -f ${BASE_DIR}/cm_webapp/gunicorn.pid
			return 0
		else
			echo "Failed to stop process with PID $pid"
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

cm_webapp_status () {
	if [ -f ${BASE_DIR}/cm_webapp/gunicorn.pid ]; then
		pid=$(cat ${BASE_DIR}/cm_webapp/gunicorn.pid)
		if ps -p $pid > /dev/null; then
			echo "cm_webapp is running with PID $pid"
			return 0
		else
			echo "cm_webapp is not running, but PID file exists"
			return 1
		fi
	else
		echo "cm_webapp is not running (no PID file found)"
		return 1
	fi
}

cm_webapp_logs () {
	if [ -f ${LOG_DIR}/gunicorn.log ]; then
		echo "Showing logs for cm_webapp (press Ctrl+C to exit)"
		tail -f ${LOG_DIR}/gunicorn.log
	else
		echo "No log file found. Is the service running?"
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
	status)		cm_webapp_status
			exit $?
			;;
	logs)		cm_webapp_logs
			exit $?
			;;
	*)		echo "Usage: $0 start|stop|restart|status|logs"
			exit 1
			;;
esac
