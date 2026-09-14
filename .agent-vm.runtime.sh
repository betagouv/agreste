#!/usr/bin/env bash
set -euo pipefail
docker compose up -d db
echo "PostgreSQL is ready"
# Apply migrations
uv run python manage.py migrate --settings config.settings_test
echo "Migrations applied"
# Install cursor cli
curl https://cursor.com/install -fsS | bash
