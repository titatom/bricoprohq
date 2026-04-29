#!/bin/sh
# Wrapper that disables BuildKit so docker compose build works on older
# Docker/buildx versions (e.g. Unraid). Pass any docker compose args:
#   ./start.sh up --build -d
#   ./start.sh down
#   ./start.sh logs -f
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0
docker compose "$@"
