# Web APIs Service

This is a FastAPI-based web service that provides various web scraping and search APIs. The service runs as a systemd service on port 8001.

## API Overview

This service provides multiple endpoint groups for web scraping, search functionality, and Austrian company register (Firmenbuch) data.

### Authentication

All API endpoints require authentication using Bearer tokens defined in your `.env` file. Include the header `Authorization: Bearer YOUR_TOKEN` in your requests.

The base URL for all endpoints is `/api`.

---

## Firmenbuch (Austrian Company Register)

Access Austrian company register data from **evi.gv.at** (free) and the **BMJ HVD SOAP API** (requires token). Includes ÖNACE industry classification from Statistik Austria.

**Data sources:**
| Source | Auth | What it provides |
|--------|------|-----------------|
| evi.gv.at | None (free) | Status, registration date, share capital, fiscal year, representation text, publications, Aufsichtsrat, Gesellschafter |
| BMJ HVD SOAP | HVDAT_TOKEN | Structured address, persons with DOB + nationality, functions with representation details, Vollzug (filing history), EUID, branch offices, legal proceedings |
| Statistik Austria | None (public) | ÖNACE industry classification |

**Attribution:** Republik Österreich — Bundesministerium für Justiz, Bundesministerium für Kunst, Kultur, öffentlicher Dienst und Sport. Licensed under CC BY 4.0.

### Test Companies

| FN | Company |
|----|---------|
| `475207i` | Brantner Österreich GmbH |
| `188942g` | Riener Nachfolger GmbH |
| `46653h` | Saubermacher DienstleistungsAG |

---

#### GET /firmenbuch/search

Search companies by name via evi.gv.at (free, no HVD token needed).

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | ✅ | Company name (fuzzy search) |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/search?query=brantner"
```

**Response:**
```json
{
  "results": [
    {"fn": "475207i", "name": "Brantner Österreich GmbH"},
    {"fn": "128972s", "name": "Brantner Gruppe GmbH"},
    {"fn": "273103y", "name": "Brantner Saubermacher Umweltservice GmbH"}
  ]
}
```

---

#### GET /firmenbuch/search/rich

Search companies with seat (city) info. Makes one additional request per unique FN.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | ✅ | Company name (fuzzy search) |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/search/rich?query=riener+nachfolger"
```

**Response:**
```json
{
  "results": [
    {"fn": "188942g", "name": "Riener Nachfolger GmbH", "seat": "Wien"}
  ]
}
```

---

#### GET /firmenbuch/lookup

Look up a company by Firmenbuchnummer (FN) on evi.gv.at.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fn` | string | ✅ | Firmenbuchnummer, e.g. `475207i` |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/lookup?fn=188942g"
```

**Response:**
```json
{
  "name": "evi.gv.at | Riener Nachfolger GmbH 1210 Wien | Firmenbuch",
  "fn": "188942g",
  "status": "Aktiv",
  "address": "Pastorstraße 47, 1210 Wien",
  "city": "Wien",
  "registered": "16.12.1999",
  "legal_form": "Gesellschaft mit beschränkter Haftung",
  "fiscal_year_end": "31.12.",
  "share_capital": "EUR 35.000",
  "purpose": "Güterbeförderungsgewerbe",
  "representation": "Die Gesellschaft wird durch zwei Geschäftsführer gemeinsam vertreten...",
  "persons": [
    {"name": "Adeeb Riener", "role": "Geschäftsführer/in", "since": "16.12.1999"},
    {"name": "Ursula Riener", "role": "Geschäftsführer/in", "since": "05.11.2013"}
  ],
  "publications": [
    {"date": "05.11.2013", "type": "Eingetragen im Firmenbuch", "details": ["..."]}
  ]
}
```

---

#### GET /firmenbuch/lookup/merged ⭐

Full company record merged from evi + HVD + ÖNACE. **Recommended endpoint** for complete data.

HVD provides structured address, person birthdates, nationalities, Vollzug history, EUID, and branch offices. evi supplements with status, publications, and representation text. Every field's origin is tracked in `_sources`.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fn` | string | ✅ | Firmenbuchnummer, e.g. `475207i` |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/lookup/merged?fn=475207i"
```

**Response (truncated):**
```json
{
  "fn": "475207i",
  "name": "Brantner Österreich GmbH",
  "status": "Aktiv",
  "address": {
    "strasse": "Dr. Franz Wilhelm-Straße",
    "hausnummer": "2a",
    "plz": "3500",
    "ort": "Krems an der Donau",
    "staat": "AUT"
  },
  "address_text": "Dr. Franz Wilhelm-Straße, 2a, 3500, Krems an der Donau",
  "seat": "Krems an der Donau",
  "registered": "27.07.2017",
  "legal_form": "Gesellschaft mit beschränkter Haftung",
  "legal_form_code": "GES",
  "share_capital": {"amount": 450000.0, "currency": "EUR"},
  "persons": [
    {
      "name": "Josef Scheidl",
      "role": "Geschäftsführer/in",
      "since": "2018-09-18",
      "source": "hvd,evi",
      "birthdate": "1969-07-01"
    },
    {
      "name": "Otto Burger",
      "role": "Prokurist/in",
      "since": "2018-10-03",
      "source": "hvd,evi",
      "birthdate": "1967-06-15"
    }
  ],
  "vollzug": [
    {
      "vnr": "001",
      "vollzugsdatum": "2017-07-27",
      "court": {"code": "217", "text": "Bezirksgericht Krems an der Donau"},
      "antragstext": ["Firmenbuchnummer 475207 i"]
    }
  ],
  "oenace": {
    "oenace_code": "38110",
    "section": "Wasserversorgung und Abfallentsorgung",
    "division": "Sammlung und Beseitigung von Abfällen",
    "subclass": "Sammlung nicht gefährlicher Abfälle"
  },
  "_sources": {
    "fn": "hvd", "name": "hvd", "status": "evi", "address": "hvd",
    "seat": "hvd", "registered": "evi", "legal_form": "hvd",
    "share_capital": "hvd", "persons": "hvd,evi", "vollzug": "hvd",
    "oenace": "statistik.gv.at"
  }
}
```

---

#### GET /firmenbuch/oenace

Look up ÖNACE industry classification for a company.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fn` | string | ✅ | Firmenbuchnummer |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/oenace?fn=475207i"
```

**Response:**
```json
{
  "oenace_code": "38110",
  "source": "statistik.gv.at (CC BY 4.0)",
  "section": "Wasserversorgung und Abfallentsorgung",
  "division": "Sammlung und Beseitigung von Abfällen",
  "subclass": "Sammlung nicht gefährlicher Abfälle"
}
```

---

### HVD Endpoints (require HVDAT_TOKEN)

These endpoints query the BMJ HVD SOAP API directly. They require `HVDAT_TOKEN` in the server's `.env` file.

---

#### GET /firmenbuch/hvd/token-check

Validate the HVD API token.

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/hvd/token-check"
```

**Response:**
```json
{"status": "ok", "message": "Token accepted by HVD endpoint"}
```

---

#### GET /firmenbuch/hvd/suche-firma

Advanced company search via HVD with filters.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | ✅ | Company name |
| `exakt` | bool | No | Exact search (default: phonetic) |
| `gericht` | string | No | Court code, e.g. `007` (Handelsgericht Wien) |
| `rechtsform` | string | No | Legal form code, e.g. `GES` (GmbH), `AG`, `KG` |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/hvd/suche-firma?query=riener+nachfolger"
```

**Response:**
```json
{
  "results": [
    {
      "fnr": "188942g",
      "status": "",
      "name_lines": ["Riener Nachfolger GmbH"],
      "sitz": "Wien",
      "rechtsform_code": "GES",
      "rechtsform_text": "Gesellschaft mit beschränkter Haftung",
      "gericht_code": "007",
      "gericht_text": "Handelsgericht Wien"
    }
  ]
}
```

---

#### GET /firmenbuch/hvd/suche-urkunde

Search documents (Urkunden) by FN or Aktenzeichen.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fnr` | string | One of | Firmenbuchnummer, e.g. `188942g` |
| `az` | string | One of | Aktenzeichen, e.g. `007 61 Fr 2164/15 w` |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/hvd/suche-urkunde?fnr=188942g"
```

**Response:**
```json
{
  "results": [
    {
      "key": "188942_0070710602369_000___000_00_437575_PDF",
      "fnr": "188942 g",
      "az": "007 071 Fr 2369/06 f",
      "dokumentart_code": "48",
      "dokumentart_text": "Jahresabschluss",
      "content_type": "application/pdf",
      "dateiendung": "pdf",
      "groesse": 150074
    }
  ]
}
```

---

#### GET /firmenbuch/hvd/auszug

Full structured Firmenbuchauszug (extract) via HVD. Returns the most comprehensive company record including all persons, functions, capital, branch offices, legal proceedings, and filing history.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `fnr` | string | ✅ | Firmenbuchnummer, e.g. `188942g` |
| `stichtag` | string | ✅ | Date in YYYY-MM-DD format |
| `umfang` | string | No | `Kurzinformation` (default) |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/hvd/auszug?fnr=475207i&stichtag=2025-04-08"
```

**Response (truncated):**
```json
{
  "fnr": "475207 i",
  "stichtag": "2025-04-08",
  "umfang": "Kurzinformation",
  "pruefsumme": "BD6B1FED9AF9856BFDD7810599B14EEC",
  "company_name": ["Brantner Österreich GmbH"],
  "company_address": {
    "strasse": "Dr. Franz Wilhelm-Straße",
    "hausnummer": "2a", "plz": "3500",
    "ort": "Krems an der Donau", "staat": "AUT"
  },
  "company_seat": "Krems an der Donau",
  "company_legal_form": {"code": "GES", "text": "Gesellschaft mit beschränkter Haftung"},
  "company_share_capital": [{"currency": "EUR", "capital": 450000.0, "aufrecht": true}],
  "persons_with_functions": [
    {
      "pnr": "I", "name": "Josef Scheidl",
      "birthdate": "1969-07-01", "nationality": ["AUT"],
      "functions": [
        {"fken": "GF", "fkentext": "GESCHÄFTSFÜHRER/IN",
         "representation": [{"since": "2018-09-18", "aufrecht": true}]}
      ]
    }
  ],
  "vollzug": [...],
  "euids": [...],
  "branch_offices": [...]
}
```

---

#### GET /firmenbuch/hvd/veraenderungen-firma

Query company changes (new registrations, modifications, deletions) in a date range. **Maximum 7 days** per request.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `von` | string | ✅ | Start date YYYY-MM-DD |
| `bis` | string | ✅ | End date YYYY-MM-DD (max 7 days from `von`) |
| `gericht` | string | No | Court code, e.g. `239` |
| `rechtsform` | string | No | Legal form code, e.g. `GES` |
| `art` | string | No | Change type, e.g. `EINTRITT_IN_FUNKTION` |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/hvd/veraenderungen-firma?von=2024-01-01&bis=2024-01-07"
```

**Response:**
```json
{
  "results": [
    {
      "fnr": "226 h",
      "vnr": "037",
      "vollzugsdatum": "2024-01-06",
      "art_veraenderung": "Änderung",
      "details": []
    }
  ]
}
```

---

#### GET /firmenbuch/hvd/veraenderungen-urkunde

Query document changes in a date range. **Maximum 7 days** per request.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `von` | string | ✅ | Start date YYYY-MM-DD |
| `bis` | string | ✅ | End date YYYY-MM-DD (max 7 days from `von`) |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/firmenbuch/hvd/veraenderungen-urkunde?von=2024-01-01&bis=2024-01-07"
```

---

### Firmenbuch Error Codes

| HTTP Code | When |
|-----------|------|
| 200 | Success |
| 400 | Invalid FN format, date > 7 days, bad parameters |
| 401 | Missing or invalid Bearer token |
| 403 | HVD token rejected |
| 404 | Company not found, no search results, no changes in period |
| 502 | evi.gv.at or HVD upstream error |
| 503 | HVD not configured (missing deps or token) |

---

## DuckDuckGo Search

### GET /duck/news

Search for news articles with localization and filtering.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `topic` | string | ✅ | News search topic |
| `region` | string | No | `at-at`, `de-de`, `wt-wt` (default) |
| `safesearch` | string | No | `on`, `moderate`, `off` (default) |
| `timelimit` | string | No | `d`, `w`, `m`, `y` |
| `max_results` | int | No | Default: 8 |
| `backend` | string | No | `auto`, `bing`, `duckduckgo`, `google`, etc. |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/duck/news?topic=technology&region=at-at&timelimit=m"
```

### GET /duck/search

Text search with advanced filters. Supports operators: `site:`, `filetype:`, `inurl:`.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | ✅ | Search query |
| `max_results` | int | No | Default: 25 |
| `region` | string | No | Default: `wt-wt` |
| `site` | string | No | Restrict to domain |
| `exact` | bool | No | Exact phrase match |
| `exclude` | string | No | Comma-separated terms to exclude |
| `filetype` | string | No | Filter by extension |
| `inurl` | string | No | Filter by URL fragment |
| `backend` | string | No | Search backend selection |

**Example:**
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/duck/search?query=fastapi+site:github.com&max_results=10"
```

### GET /duck/translate

**Parameters:** `text` (required), `to_language` (required, e.g. `de`, `fr`, `es`)

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://your-server/api/duck/translate?text=hello&to_language=de"
```

---

## Utility Endpoints

### GET /echo

Returns input text. Useful for health checks.

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" "https://your-server/api/echo?text=ping"
```

### GET /fetch_url

Fetch URL content using w3m or lynx.

**Parameters:** `url` (required), `tool` (`w3m` or `lynx`, default: `w3m`)

### GET /w3m_google

Google search via w3m with domain-specific results.

**Parameters:** `query` (required), `num_results` (default: 10), `domain` (default: `at`)

### GET /lynx

Fetch URL content using lynx browser.

**Parameters:** `url` (required)

---

## Service Management

The API runs as a systemd service named `fastapi.service`.

### Service Commands

```bash
sudo systemctl start fastapi
sudo systemctl stop fastapi
sudo systemctl restart fastapi
sudo systemctl status fastapi
sudo systemctl enable fastapi
```

### Deployment

```bash
./deploy_api.sh
```

This script will:
1. Pull the latest code from the repository
2. Update Python dependencies
3. Restart the fastapi service

### Logs

```bash
sudo journalctl -u fastapi -f
```

API access logs are stored in `api.log`.

## Prerequisites

- Python 3.12+
- Virtual environment (recommended)
- Required packages (see requirements.txt)
- [firmenbuch_AT](https://github.com/devskale/firmenbuch_AT) — symlinked into project

## Configuration

The service runs on port 8001 and uses gunicorn with uvicorn workers for optimal performance.

### Environment Variables (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `TOKENS` | ✅ | Comma-separated Bearer tokens |
| `HVDAT_TOKEN` | For HVD endpoints | BMJ HVD API token (or configure credgoo) |

### Security

- Authentication is required for all endpoints using Bearer tokens
- Tokens are configured in the .env file and loaded at startup
- CORS is configured to allow all origins (for development)
- Rate limiting and input validation are implemented
