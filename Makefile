# Makefile for Apollo CM testing Web app, borrowed from chess-status

.PHONY: default clean update deploy

default: .venv

.venv:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

clean:
	rm -rf .venv
	find . -name "*~" -delete
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete

update:
	[ -d '.venv' ]
	git pull
	.venv/bin/pip install -U -r requirements.txt

# TODO: fix this for proper deployment
#deploy: .venv
#	rsync --delete -avz . chess_svc@chess15:/mnt/services/release/chess-status/chess-status-devel/
