#!/usr/bin/env bash
# prose-lint-server.sh -- manage the local LanguageTool container (OrbStack).
#
# The grammar linter checks against a LOCAL LanguageTool server only; repo
# content is never sent to the public API. This starts a stock
# erikvl87/languagetool container bound to localhost, kept alive by the Docker
# engine (OrbStack) with a restart policy so it survives reboots.
#
# Usage: prose-lint-server.sh {start|stop|status|restart}
set -euo pipefail

IMAGE="erikvl87/languagetool:latest"
NAME="prose-lint-lt"
HOST_PORT="${PROSE_LINT_PORT:-8081}"
CONTAINER_PORT="8010" # the image listens on 8010 internally
URL="http://localhost:${HOST_PORT}"

die() {
	echo "prose-lint-server: $*" >&2
	exit 1
}
command -v docker >/dev/null 2>&1 || die "docker (OrbStack) not found on PATH"

running() { [ -n "$(docker ps -q -f "name=^${NAME}$")" ]; }
exists() { [ -n "$(docker ps -aq -f "name=^${NAME}$")" ]; }

start() {
	if running; then
		echo "already running at ${URL}"
		return 0
	fi
	if exists; then
		docker start "${NAME}" >/dev/null
	else
		# --restart unless-stopped: OrbStack brings it back on boot.
		# Java_Xmx caps heap; no n-gram data in v1 (large download).
		docker run -d \
			--name "${NAME}" \
			--restart unless-stopped \
			-p "127.0.0.1:${HOST_PORT}:${CONTAINER_PORT}" \
			-e "Java_Xmx=1g" \
			"${IMAGE}" >/dev/null
	fi
	echo "starting ${NAME} at ${URL} ..."
	for _ in $(seq 1 30); do
		if curl -fsS "${URL}/v2/languages" >/dev/null 2>&1; then
			echo "ready at ${URL}"
			return 0
		fi
		sleep 1
	done
	die "server did not become ready within 30s (see: docker logs ${NAME})"
}

stop() {
	running && docker stop "${NAME}" >/dev/null && echo "stopped" || echo "not running"
}

status() {
	if running; then
		echo "running at ${URL}"
		curl -fsS "${URL}/v2/languages" >/dev/null 2>&1 && echo "health: OK" || echo "health: NOT READY"
	else
		echo "not running"
		exit 1
	fi
}

case "${1:-}" in
start) start ;;
stop) stop ;;
restart)
	stop
	start
	;;
status) status ;;
*) die "usage: $0 {start|stop|status|restart}" ;;
esac
