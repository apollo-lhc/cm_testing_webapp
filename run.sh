#! /bin/sh
# Makefile for Apollo CM testing Web app, with inspiration from chess-status
# run with ./run.sh start|stop


# Set BASE_DIR to default if not already set
: "${BASE_DIR:=/nfs/cms/tracktrigger/cm_testing_webapp_run}"
LOG_DIR="${BASE_DIR}/log"

: "${IPADDR:="172.31.5.80"}"
SVC_OPTS="--bind=${IPADDR}:8000 --disable-redirect-access-to-syslog --log-syslog"


cm_webapp_start () {
	echo "Starting cm_webapp"
	cd ${BASE_DIR}/cm_webapp
	mkdir -p ${LOG_DIR}/cm_webapp-status
	nohup .venv/bin/python3 .venv/bin/gunicorn $SVC_OPTS app:app \
		 >${LOG_DIR}/cm_webapp-status/startup.log 2>&1 &
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

echo "argument is $1"
case "$1" in
	start)		cm_webapp_start
			exit $?
			;;
	stop)		cm_webapp_stop
			exit $?
			;;
	*)		echo "Usage: $0 start|stop"
esac
