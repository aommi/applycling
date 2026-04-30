#!/bin/bash
# applycling deploy script — run from /opt/applycling/app
set -e

echo "=== Pulling latest code ==="
git pull

echo "=== Starting Postgres ==="
docker compose -f docker-compose.prod.yml up -d postgres

echo "=== Waiting for Postgres ==="
until docker compose -f docker-compose.prod.yml exec postgres pg_isready -U applycling; do
  echo "  waiting..."
  sleep 2
done

echo "=== Running migrations ==="
docker compose -f docker-compose.prod.yml run --rm applycling alembic upgrade head

echo "=== Deploying ==="
docker compose -f docker-compose.prod.yml up -d --build

echo "=== Health check ==="
sleep 2
curl -s http://localhost:8080/healthz
echo ""

echo "=== Done ==="
docker compose -f docker-compose.prod.yml ps
