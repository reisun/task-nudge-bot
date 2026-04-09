#!/bin/bash
set -e

# Copy read-only mounted auth files to writable locations
if [ -d /mnt/claude ]; then
  cp -r /mnt/claude/. "$HOME/.claude/"
fi

# Restore .claude.json from backup if not directly available
if [ -f /mnt/claude.json ]; then
  cp /mnt/claude.json "$HOME/.claude.json"
elif ls "$HOME/.claude/backups/.claude.json.backup."* 1>/dev/null 2>&1; then
  latest=$(ls -t "$HOME/.claude/backups/.claude.json.backup."* | head -1)
  cp "$latest" "$HOME/.claude.json"
fi

exec "$@"
