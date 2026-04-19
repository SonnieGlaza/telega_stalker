#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Data migration: consolidate DB and backup files into the persistent volume.
# Runs before the bot starts so /data always holds the most recent data.
# ---------------------------------------------------------------------------
DATA_DIR="/data"
DB_FILE="stalker_game.db"
BACKUP_FILE="stalker_game.backup.json"

echo "[migrate] Creating persistent data directory: ${DATA_DIR}"
mkdir -p "${DATA_DIR}"

migrate_file() {
    local filename="$1"
    local dest="${DATA_DIR}/${filename}"
    # Candidate locations to search, in priority order.
    local candidates=(
        "/app/${filename}"
        "/workspace/${filename}"
        "./${filename}"
    )
    for src in "${candidates[@]}"; do
        if [ -f "${src}" ] && [ "${src}" != "${dest}" ]; then
            echo "[migrate] Found ${src} — copying to ${dest}"
            cp -p "${src}" "${dest}"
            # Keep only the first (highest-priority) match.
            break
        fi
    done
}

migrate_file "${DB_FILE}"
migrate_file "${BACKUP_FILE}"

echo "[migrate] Contents of ${DATA_DIR}:"
ls -lh "${DATA_DIR}" || true
echo "[migrate] Migration step complete."
# ---------------------------------------------------------------------------

python3 run.py
