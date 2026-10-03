#!/usr/bin/env bash
# Combined coverage: tests/ then platform_tests/ (needs the running compose Postgres).
# Usage: MSYS_NO_PATHCONV=1 bash scripts/run_combined_coverage.sh
set -u
cd "$(dirname "$0")/.."
env_of() { docker inspect environmental-platform-api-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep "^$1=" | cut -d= -f2-; }
URL=$(env_of ESP_DATABASE_URL | sed 's#/platform$#/coverage_tests#')
KEY=$(env_of ESP_SECRET_KEY)
docker run --rm --network environmental-platform_default \
  -v "$(pwd -W 2>/dev/null || pwd):/workspace" -w /workspace \
  -e COVERAGE_FILE=/tmp/.cov -e ESP_DATABASE_URL="$URL" -e ESP_SECRET_KEY="$KEY" \
  -e ESP_REDIS_URL=redis://redis:6379/15 -e ESP_ENVIRONMENT=test \
  environmental-platform-backend-tests:local sh -c "
python -m pytest tests -o addopts= -q -p no:cacheprovider --tb=short -W ignore --cov=app --cov=legacy_algorithms 2>&1 | tail -15;
python -m pytest platform_tests -o addopts= -q -p no:cacheprovider --tb=short -W ignore --cov=app --cov=legacy_algorithms --cov-append --cov-report=term-missing:skip-covered 2>&1 | tail -150"
