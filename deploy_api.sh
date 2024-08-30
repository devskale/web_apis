#!/bin/bash
cd /path/to/your/project
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart fastapi