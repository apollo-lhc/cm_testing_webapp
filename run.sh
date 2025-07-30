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
	return 0
}

cm_webapp_stop () {
	echo "Stopping cm_webapp"
	pid=$(ps ax | grep '[g]unicorn' | awk '{print $1}' | head -n 1)
	if [ -n "$pid" ]; then
		if kill $pid; then
			return 0
		else
			return 1
		fi
	fi
	return 0
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
