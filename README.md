# Web APIs

This document describes the available API endpoints. The base URL for all endpoints is `/api`.

## Endpoints

### 1. Echo

-   **Endpoint:** `/echo`
-   **Method:** `GET`
-   **Description:** Returns the input text as an echo.
-   **Query Parameters:**
    -   `text` (optional): The text to echo. Defaults to "Hello, World!". Minimum length of 1 character.
-   **Example Request:** `/api/echo?text=MyEcho`
-   **Example Response:**

    ```json
    {
        "echo": "MyEcho"
    }
    ```

### 2. W3m Fetch

-   **Endpoint:** `/w3m`
-   **Method:** `GET`
-   **Description:** Fetches the content of a given URL using the w3m browser.
-   **Query Parameters:**
    -   `url` (required): The URL to fetch.
-   **Example Request:** `/api/w3m?url=https://example.com`
-   **Example Response:**

    ```json
    {
      "content": "<html>...</html>"
    }
    ```
-   **Error Response:**

    ```json
      {
        "detail": "Error Message from W3m"
      }
    ```

    (Returns 500 status code)

### 3. W3m Google Search

-   **Endpoint:** `/w3m_google`
-   **Method:** `GET`
-   **Description:** Performs a Google search using w3m.
-   **Query Parameters:**
    -   `query` (required): The search query.
    -   `num_results` (optional): The number of results to return. Defaults to 10.
    -   `domain` (optional): The search domain, defaults to "at".
-   **Example Request:** `/api/w3m_google?query=fastapi&num_results=5&domain=com`
-   **Example Response:**

    ```json
    {
      "content": "<html>...</html>"
    }
    ```
-   **Error Response:**

    ```json
      {
          "detail": "Error Message from W3m"
      }
    ```

    (Returns 500 status code)

### 4. DuckDuckGo News Search

-   **Endpoint:** `/duck/news`
-   **Method:** `GET`
-   **Description:** Searches for news on DuckDuckGo.
-   **Query Parameters:**
    -   `topic` (required): The topic to search for.
-   **Example Request:** `/api/duck/news?topic=technology`
-   **Example Response:**

    ```json
    {
      "results": [
        {"title": "News 1", "url": "url1", "source":"source1"},
        {"title": "News 2", "url": "url2", "source":"source2"}
       ]
    }
    ```
-   **Error Response:**

    ```json
      {
        "detail": "No news found."
      }
    ```

    (Returns 404 status code)

### 5. DuckDuckGo Text Search

-   **Endpoint:** `/duck/text`
-   **Method:** `GET`
-   **Description:** Searches for text on DuckDuckGo.
-   **Query Parameters:**
    -   `topic` (required): The topic to search for.
-   **Example Request:** `/api/duck/text?topic=python`
-  **Example Response:**

    ```json
    {
    "results": [
        {"title": "Title 1", "url": "url1", "body": "Body 1"},
        {"title": "Title 2", "url": "url2", "body": "Body 2"}
      ]
    }
    ```
-   **Error Response:**

    ```json
      {
          "detail": "No text found."
      }
    ```

    (Returns 404 status code)

### 6. DuckDuckGo Maps Search

-   **Endpoint:** `/duck/maps`
-   **Method:** `GET`
-   **Description:** Searches for maps on DuckDuckGo.
-   **Query Parameters:**
    -   `topic` (required): The topic to search for (e.g., location).
    -   `place` (optional): The specific place to search for.
-   **Example Request:** `/api/duck/maps?topic=coffee&place=vienna`
-   **Example Response:**

    ```json
    {
      "results": [
        {"title": "Place 1", "url": "url1", "address":"address1"},
        {"title": "Place 2", "url": "url2", "address":"address2"}
      ]
    }
    ```
-   **Error Response:**

    ```json
      {
          "detail": "No maps found."
      }
    ```

    (Returns 404 status code)

### 7. DuckDuckGo Translate

-   **Endpoint:** `/duck/translate`
-   **Method:** `GET`
-   **Description:** Translates text using DuckDuckGo.
-   **Query Parameters:**
    -   `topic` (required): The text to translate.
    -   `to_language` (required): The target language code (e.g., "de", "fr", "es").
-   **Example Request:** `/api/duck/translate?topic=hello&to_language=de`
-   **Example Response:**

    ```json
    {
        "results": "Hallo"
    }
    ```
-   **Error Response:**

    ```json
      {
          "detail": "No translation found."
      }
    ```

    (Returns 404 status code)

### 8. Google Search

-   **Endpoint:** `/goog`
-   **Method:** `GET`
-   **Description:** Performs a Google search.
-   **Query Parameters:**
    -   `query` (required): The search query.
    -   `num_results` (optional): The number of results to return. Defaults to 10.
-   **Example Request:** `/api/goog?query=fastapi&num_results=5`
-  **Example Response:**

    ```json
    {
      "results": [
        {"title": "Result 1", "url": "url1"},
        {"title": "Result 2", "url": "url2"}
      ]
    }
    ```
-   **Error Response:**

    ```json
      {
          "detail": "No results found."
      }
    ```

    (Returns 404 status code)

### 9. Lynx URL Fetch

-   **Endpoint:** `/lynx`
-   **Method:** `GET`
-   **Description:** Fetches the content of a given URL using the lynx browser.
-   **Query Parameters:**
    -   `url` (required): The URL to fetch.
-   **Example Request:** `/api/lynx?url=https://example.com`
-   **Example Response:**

    ```json
    {
      "results": "<html>...</html>"
    }
    ```
-   **Error Response:**

    ```json
      {
          "detail": "No results found."
      }
    ```

    (Returns 404 status code)

## Running the Application

1.  Make sure you have Python installed.
2.  Install the required packages using pip:

    ```bash
    pip install fastapi uvicorn
    ```
3.  Run the application using:

    ```bash
    python main.py
    ```

The API will be available at `http://localhost:8001/api`.

## Key Points

*   **Clear Headers:** Uses clear headers to organize the information.
*   **Endpoint Details:** Provides each endpoint's path, method, description, parameters, example request and responses.
*   **Error Handling:** It also mentions the 404 and 500 error responses.
*   **Usage Instructions:** Gives basic instructions on how to run the application and access the API.
*   **Markdown:** It's formatted as a Markdown file for easy readability on platforms like GitHub.
*   **Root Path:** It correctly specifies that the API's root path is `/api`.

This README should give users a good starting point for understanding and using your API.

# web_apis

# Installing APIs on a VPS

## Prerequisites

- OCI VPS: Ensure you have an Oracle Cloud Infrastructure (OCI) Virtual Private Server (VPS) set up with a Linux distribution (e.g., Ubuntu 20.04).
- Nginx: Make sure Nginx is installed on your VPS (`sudo apt install nginx -y`).

## Deploying FastAPI on OCI VPS

1.  Connect to Your VPS
2.  Install requirements
3.  Run FastAPI:
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8001
    ```
4.  Configure Nginx route:

    ```bash
    sudo nano /etc/nginx/sites-available/fastapi
    ```

## Usage

```bash
sudo ln -s /etc/nginx/sites-available/fastapi /etc/nginx/sites-enabled/
sudo systemctl restart nginx
