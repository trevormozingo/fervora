#!/usr/bin/env bash
set -euo pipefail

docker compose -f backend/docker-compose.yaml up --build
