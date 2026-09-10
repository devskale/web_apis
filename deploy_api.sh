#!/bin/bash
set -e
cd /home/ubuntu/code/web_apis
git pull
export PATH="$HOME/.local/bin:$PATH"
uv sync --frozen
sudo systemctl restart fastapi
