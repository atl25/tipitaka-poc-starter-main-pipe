#!/usr/bin/env bash
# docker_reset.sh — Danger! Wipes ALL Docker containers, images, volumes & cache.
# Use from Git Bash / WSL / Linux / macOS. Not for PowerShell.
set -euo pipefail

echo "⚠️  This will STOP & DELETE *ALL* containers, images, volumes, and builder cache on this machine."
echo "   Continue in 5 seconds... (Ctrl+C to cancel)"
sleep 5

echo "→ Listing containers (all):"
docker ps -a || true

# Stop and remove all containers (if any)
if [ -n "$(docker ps -q)" ]; then
  echo "→ Stopping running containers..."
  docker stop $(docker ps -q)
fi

if [ -n "$(docker ps -aq)" ]; then
  echo "→ Removing all containers..."
  docker rm -f $(docker ps -aq)
fi

# Remove all images (best-effort)
if [ -n "$(docker images -q)" ]; then
  echo "→ Removing all images (this may take a while)..."
  docker rmi -f $(docker images -q) || true
fi

# Remove all volumes
if [ -n "$(docker volume ls -q)" ]; then
  echo "→ Removing all volumes..."
  docker volume rm $(docker volume ls -q) || true
fi

# Final prune
echo "→ docker system prune -a --volumes -f"
docker system prune -a --volumes -f || true

echo "✅ Docker reset complete."
