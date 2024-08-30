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
# Usage

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
## w3m 
w3m is a text based web browser

```
usage: w3m [options] [URL or filename]
options:
    -t tab           set tab width
    -r               ignore backspace effect
    -l line          # of preserved line (default 10000)
    -I charset       document charset
    -O charset       display/output charset
    -B               load bookmark
    -bookmark file   specify bookmark file
    -T type          specify content-type
    -m               internet message mode
    -v               visual startup mode
    -M               monochrome display
    -N               open URL of command line on each new tab
    -F               automatically render frames
    -cols width      specify column width (used with -dump)
    -ppc count       specify the number of pixels per character (4.0...32.0)
    -ppl count       specify the number of pixels per line (4.0...64.0)
    -dump            dump formatted page into stdout
    -dump_head       dump response of HEAD request into stdout
    -dump_source     dump page source into stdout
    -dump_both       dump HEAD and source into stdout
    -dump_extra      dump HEAD, source, and extra information into stdout
    -post file       use POST method with file content
    -header string   insert string as a header
    +<num>           goto <num> line
    -num             show line number
    -no-proxy        don't use proxy
    -4               IPv4 only (-o dns_order=4)
    -6               IPv6 only (-o dns_order=6)
    -no-mouse        don't use mouse
    -cookie          use cookie (-no-cookie: don't use cookie)
    -graph           use DEC special graphics for border of table and menu
    -no-graph        use ASCII character for border of table and menu
    -s               squeeze multiple blank lines
    -W               toggle search wrap mode
    -X               don't use termcap init/deinit
    -title[=TERM]    set buffer name to terminal title string
    -o opt=value     assign value to config option
    -show-option     print all config options
    -config file     specify config file
    -help            print this usage message
    -version         print w3m version
    -reqlog          write request logfile
    -debug           DO NOT USE
```