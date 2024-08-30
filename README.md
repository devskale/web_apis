# web_apis

# installing APIs on a VPS
Prerequisites

- OCI VPS: Ensure you have an Oracle Cloud Infrastructure (OCI) Virtual Private Server (VPS) set up with a Linux distribution (e.g., Ubuntu 20.04).
- Nginx: Make sure Nginx is installed on your VPS (sudo apt install nginx -y).

Deploying FastAPI on OCI VPS

1.	Connect to Your VPS
2.  Install requirements
3. run fastapi
```uvicorn main:app --host 0.0.0.0 --port 8001```
3.  Configure nginx route

```
sudo nano /etc/nginx/sites-available/fastapi
```

```
sudo ln -s /etc/nginx/sites-available/fastapi /etc/nginx/sites-enabled/
sudo systemctl restart nginx
```
after updating api sources

sudo systemctl status fastapi

```
sudo systemctl restart fastapi
```
```
sudo nano /etc/systemd/system/fastapi.service
```