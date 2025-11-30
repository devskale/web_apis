#!/bin/bash
cd /home/ubuntu/code/web_apis
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart fastapi