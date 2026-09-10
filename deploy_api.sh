#!/bin/bash
set -e
cd /home/ubuntu/code/web_apis
git pull
export PATH="$HOME/.local/bin:$PATH"
uv sync --frozen
# Disk hygiene (amd is small): drop cache entries not needed by the current
# lockfile — old dependency versions accumulate otherwise on every deploy.
uv cache prune --ci
sudo systemctl restart fastapi
