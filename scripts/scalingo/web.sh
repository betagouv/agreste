#!/usr/bin/env bash
set -euo pipefail

# DISABLE_COLLECTSTATIC: review apps / one-click deploys skip ``collectstatic``
# during slug compile because DATABASE_URL is not injected yet (this is the
# Scalingo Python buildpack flag). Run it here on web boot, once addon env
# vars are present. Files collected in postdeploy would not persist on the
# web container
if [[ "${DISABLE_COLLECTSTATIC:-}" == "1" ]]; then
    python manage.py collectstatic --noinput
fi

exec gunicorn config.wsgi --log-file - --access-logfile - \
    --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)s'
