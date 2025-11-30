# Web APIs Service

This is a FastAPI-based web service that provides various web scraping and search APIs. The service runs as a systemd service on port 8001.

## API Overview

This service provides multiple endpoints for web scraping and search functionality using different search engines and web browsers.

### Authentication

All API endpoints require authentication using Bearer tokens defined in your `.env` file. Include the header `Authorization: Bearer YOUR_TOKEN` in your requests.

The base URL for all endpoints is `/api`.

### Endpoints

#### 1. Echo
- **Endpoint:** `/echo`
- **Method:** `GET`
- **Description:** Returns the input text as an echo.
- **Query Parameters:**
  - `text` (optional): The text to echo. Defaults to "Hello, World!". Minimum length of 1 character.
- **Example Request:** `/api/echo?text=MyEcho`
- **Example Response:**
```json
{
    "echo": "MyEcho"
}
```

#### 2. W3m Fetch
- **Endpoint:** `/w3m`
- **Method:** `GET`
- **Description:** Fetches the content of a given URL using the w3m browser.
- **Query Parameters:**
  - `url` (required): The URL to fetch.
- **Example Request:** `/api/w3m?url=https://example.com`
- **Example Response:**
```json
{
  "content": "<html>...</html>"
}
```
- **Error Response:**
```json
{
  "detail": "Error Message from W3m"
}
```
(Returns 500 status code)

#### 3. W3m Google Search
- **Endpoint:** `/w3m_google`
- **Method:** `GET`
- **Description:** Performs a Google search using w3m.
- **Query Parameters:**
  - `query` (required): The search query.
  - `num_results` (optional): The number of results to return. Defaults to 10.
  - `domain` (optional): The search domain, defaults to "at".
- **Example Request:** `/api/w3m_google?query=fastapi&num_results=5&domain=com`
- **Example Response:**
```json
{
  "content": "<html>...</html>"
}
```
- **Error Response:**
```json
{
  "detail": "Error Message from W3m"
}
```
(Returns 500 status code)

#### 4. DuckDuckGo News Search
- **Endpoint:** `/duck/news`
- **Method:** `GET`
- **Description:** Searches for news on DuckDuckGo.
- **Query Parameters:**
  - `topic` (required): The topic to search for.
- **Example Request:** `/api/duck/news?topic=technology`
- **Example Response:**
```json
{
  "results": [
    {"title": "News 1", "url": "url1", "source":"source1"},
    {"title": "News 2", "url": "url2", "source":"source2"}
   ]
}
```
- **Error Response:**
```json
{
  "detail": "No news found."
}
```
(Returns 404 status code)

#### 5. DuckDuckGo Text Search
- **Endpoint:** `/duck/text`
- **Method:** `GET`
- **Description:** Searches for text on DuckDuckGo.
- **Query Parameters:**
  - `topic` (required): The topic to search for.
- **Example Request:** `/api/duck/text?topic=python`
- **Example Response:**
```json
{
"results": [
    {"title": "Title 1", "url": "url1", "body": "Body 1"},
    {"title": "Title 2", "url": "url2", "body": "Body 2"}
  ]
}
```
- **Error Response:**
```json
{
  "detail": "No text found."
}
```
(Returns 404 status code)

#### 6. DuckDuckGo Maps Search
- **Endpoint:** `/duck/maps`
- **Method:** `GET`
- **Description:** Searches for maps on DuckDuckGo.
- **Query Parameters:**
  - `topic` (required): The topic to search for (e.g., location).
  - `place` (optional): The specific place to search for.
- **Example Request:** `/api/duck/maps?topic=coffee&place=vienna`
- **Example Response:**
```json
{
  "results": [
    {"title": "Place 1", "url": "url1", "address":"address1"},
    {"title": "Place 2", "url": "url2", "address":"address2"}
  ]
}
```
- **Error Response:**
```json
{
  "detail": "No maps found."
}
```
(Returns 404 status code)

#### 7. DuckDuckGo Translate
- **Endpoint:** `/duck/translate`
- **Method:** `GET`
- **Description:** Translates text using DuckDuckGo.
- **Query Parameters:**
  - `topic` (required): The text to translate.
  - `to_language` (required): The target language code (e.g., "de", "fr", "es").
- **Example Request:** `/api/duck/translate?topic=hello&to_language=de`
- **Example Response:**
```json
{
  "results": "Hallo"
}
```
- **Error Response:**
```json
{
  "detail": "No translation found."
}
```
(Returns 404 status code)

#### 8. Google Search
- **Endpoint:** `/goog`
- **Method:** `GET`
- **Description:** Performs a Google search.
- **Query Parameters:**
  - `query` (required): The search query.
  - `num_results` (optional): The number of results to return. Defaults to 10.
- **Example Request:** `/api/goog?query=fastapi&num_results=5`
- **Example Response:**
```json
{
  "results": [
    {"title": "Result 1", "url": "url1"},
    {"title": "Result 2", "url": "url2"}
  ]
}
```
- **Error Response:**
```json
{
  "detail": "No results found."
}
```
(Returns 404 status code)

#### 9. Lynx URL Fetch
- **Endpoint:** `/lynx`
- **Method:** `GET`
- **Description:** Fetches the content of a given URL using the lynx browser.
- **Query Parameters:**
  - `url` (required): The URL to fetch.
- **Example Request:** `/api/lynx?url=https://example.com`
- **Example Response:**
```json
{
  "results": "<html>...</html>"
}
```
- **Error Response:**
```json
{
  "detail": "No results found."
}
```
(Returns 404 status code)

## Service Management

The API runs as a systemd service named `fastapi.service`.

### Service Commands

- **Start the service:**
```bash
sudo systemctl start fastapi
```

- **Stop the service:**
```bash
sudo systemctl stop fastapi
```

- **Restart the service:**
```bash
sudo systemctl restart fastapi
```

- **Check service status:**
```bash
sudo systemctl status fastapi
```

- **Enable service at boot:**
```bash
sudo systemctl enable fastapi
```

- **Disable service at boot:**
```bash
sudo systemctl disable fastapi
```

### Deployment

The `deploy_api.sh` script handles updating and restarting the service:
```bash
./deploy_api.sh
```

This script will:
1. Pull the latest code from the repository
2. Update Python dependencies
3. Restart the fastapi service

### Logs

Service logs can be viewed with:
```bash
sudo journalctl -u fastapi -f
```

API access logs are stored in `api.log`.

## Prerequisites

- Python 3.8+
- Virtual environment (recommended)
- Required packages (see requirements.txt)

## Installation on VPS

### Prerequisites
- Linux VPS (Ubuntu 20.04+ recommended)
- Nginx installed (`sudo apt install nginx -y`)

### Steps
1. Clone the repository
2. Set up virtual environment
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables (TOKENS in .env file)
5. Create systemd service file at `/etc/systemd/system/fastapi.service`
6. Enable and start the service
7. Configure Nginx reverse proxy (optional):
   ```bash
   sudo nano /etc/nginx/sites-available/fastapi
   ```
8. Enable the Nginx site:
   ```bash
   sudo ln -s /etc/nginx/sites-available/fastapi /etc/nginx/sites-enabled/
   sudo systemctl restart nginx
   ```

## Configuration

The service runs on port 8001 and uses gunicorn with uvicorn workers for optimal performance.
The service runs as user 'ubuntu' with group 'www-data'.
Working directory is set to `/home/ubuntu/code/web_apis`.

## Security

- Authentication is required for all endpoints using Bearer tokens
- Tokens are configured in the .env file and loaded at startup
- CORS is configured to allow all origins (for development)
- Rate limiting and input validation are implemented