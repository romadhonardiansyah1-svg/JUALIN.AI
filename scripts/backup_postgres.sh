#!/usr/bin/env sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/var/backups/jualin-ai}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_PROJECT_DIR="${COMPOSE_PROJECT_DIR:-/app/jualin-ai}"
DB_CONTAINER="${DB_CONTAINER:-jualin-db}"
DB_USER="${DB_USER:-jualin}"
DB_NAME="${DB_NAME:-jualin_ai}"

mkdir -p "$BACKUP_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_file="$BACKUP_DIR/${DB_NAME}_${timestamp}.sql.gz"

cd "$COMPOSE_PROJECT_DIR"
docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$backup_file"
chmod 600 "$backup_file"

find "$BACKUP_DIR" -type f -name "${DB_NAME}_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete

echo "Backup written: $backup_file"
