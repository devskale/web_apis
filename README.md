# Web APIs Service

This is a FastAPI-based web service providing web scraping, search, PDF/image conversion, and Austrian company/electricity data APIs.

> **Live deployment:** hosted at **`https://amd.skale.dev/api`** on the `amd` box, running as systemd service `fastapi.service` on port 8001 behind gunicorn + uvicorn workers.

## API Overview

This service provides multiple endpoint groups for web scraping, search functionality, and Austrian company register (Firmenbuch) data.

### Agent discovery

`GET /api/help` (no auth) returns a compact JSON orientation for agents: auth model, base URL, endpoint groups with one-liners, and example calls. The full machine-readable spec is at `GET /api/openapi.json` (no auth, includes the `HTTPBearer` security scheme); humans get Swagger UI at `GET /api/docs`.

### Authentication

All API endpoints require authentication using Bearer tokens defined in your `.env` file. Include the header `Authorization: Bearer YOUR_TOKEN` in your requests.

The base URL for all endpoints is `/api` (live: `https://amd.skale.dev/api`). Replace `https://your-server` in the examples below with `https://amd.skale.dev`.

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

#### GET /firmenbuch/oenace/tree

Browse the ÖNACE 2025 classification hierarchy (sections A–V, levels 1–5).

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `section` | string | No | Filter by section letter (A–V), e.g. `E` |
| `level` | int | No | Filter by level (1–5) |

**Example response:**
```json
{
  "codes": [
    {"edv_code": "F", "level": 1, "code_display": "F", "label_de": "Bau", "section": "F", "numeric_code": ""},
    {"edv_code": "F41", "level": 2, "code_display": "F 41", "label_de": "Hochbau", "section": "F", "numeric_code": "41"}
  ]
}
```

#### GET /firmenbuch/oenace/status

Show ÖNACE database status and last update.

**Example response:**
```json
{
  "oenace": {"rows": 326575, "description": "FN → ÖNACE-Zuordnungen"},
  "oenace_codes": {"rows": 1758, "description": "ÖNACE 2025 Hierarchie"},
  "last_update": "2026-07-02T02:00:04.505492+02:00",
  "source": "Statistik Austria (CC BY 4.0)",
  "db": "pind.mooo.com:9043/firmenbuch"
}
```

#### GET /firmenbuch/oenace/companies

Find companies by ÖNACE code (supports prefix matching, e.g. `F` = all Bau/Handel). With `seat` set, filters server-side to companies whose cached seat matches (case-insensitive substring).

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | ✅ | ÖNACE code or prefix, e.g. `6820` or `F` |
| `limit` | int | No | Max results (default 50, max 200) |
| `seat` | string | No | Filter by seat/city (substring, case-insensitive) |

**Example response:**
```json
{
  "oenace_code": "38110",
  "count": 2,
  "companies": [
    {"fn": "010142s", "oenace_code": "38110", "oenace_label": null}
  ]
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

### Crawl & Cache (Postgres-backed review layer)

These endpoints read from a Postgres cache of ~302k crawled Austrian companies and power a crawl-review UI. They live in the `firmenbuch_AT` module, **not** this repo. All require a valid Bearer token.

#### GET /firmenbuch/cache/status

Show company cache status (rows, hits, TTLs). `available=false` if the cache is not deployed.

**Example response:**
```json
{
  "enabled": true,
  "available": true,
  "rows": 302144,
  "with_name": 302139,
  "with_merged": 302139,
  "total_hits": 302149,
  "last_fetch": "2026-07-02T08:49:00.396646+02:00",
  "ttl_lookup_days": 3,
  "ttl_merged_days": 14
}
```

#### GET /firmenbuch/crawl/enabled

Whether live crawl actions (refresh/resolve) are enabled. Returns `403` for live actions unless `CRAWL_API_ENABLED=1` is set on the server. **Response:** `{"enabled": true}`

#### GET /firmenbuch/crawl/search

Production loader: server-side filtered + paginated company search. One `COUNT` + one `LIMIT/OFFSET` SELECT per request (never loads the whole 300k+ table). Each company includes `merged_data` for the detail view.

**Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Name search (ILIKE) |
| `oenace` | string | ÖNACE code or prefix, e.g. `629` or `F` |
| `plz` | string | PLZ (ILIKE) |
| `seat` | string | Seat/city (ILIKE) |
| `legal` | string | Legal form (ILIKE), e.g. `GmbH` |
| `street` | string | Street (ILIKE) |
| `person` | string | Person name (ILIKE across all roles: GF, Gesellschafter, Prokurist, Aufsichtsrat) |
| `fn` | string | FN (ILIKE) |
| `sort` | string | `fn\|name\|legal\|plz\|seat\|oenace\|when` |
| `dir` | string | `asc\|desc` |
| `page` | int | Page number |
| `size` | int | Page size |

**Example response:**
```json
{
  "total": 1688,
  "page": 1,
  "size": 2,
  "pages": 844,
  "companies": [
    {
      "fn": "672463t",
      "name": "Service-Center Schmidberger GmbH",
      "legal_form": "Gesellschaft mit beschränkter Haftung",
      "status": "Aktiv",
      "seat": "Kematen an der Krems",
      "plz": "4531",
      "street": "Linzer Straße 54",
      "oenace_code": "95310",
      "fetched_at": "2026-07-02T08:44:50.823486+02:00",
      "merged_data": {"...": "full merged record (evi + HVD + ÖNACE)"}
    }
  ]
}
```

#### GET /firmenbuch/crawl/recent

Most recently crawled companies (newest `fetched_at` first). **Param:** `limit` (int).

#### GET /firmenbuch/crawl/sections

ÖNACE sections (A–V) with labels + firm counts, for the filter dropdown.

**Example response:**
```json
{
  "sections": [
    {"section": "F", "label": "Bau", "firms": 0},
    {"section": "G", "label": "HANDEL", "firms": 0}
  ]
}
```

#### GET /firmenbuch/crawl/shareholders/{fn}

Corporate shareholders of `fn` with resolved-FN status.

**Example response:**
```json
{
  "enabled": true,
  "available": true,
  "fn": "475207i",
  "shareholders": [
    {"name": "Brantner Environment Group GmbH", "role": "Gesellschafter/in", "since": "18.08.2017", "resolved_fn": "34776t"}
  ]
}
```

#### GET /firmenbuch/crawl/beteiligungen/{fn}

Reverse ownership lookup: companies where `fn` is a shareholder (name-matched against the cached subset). Returns `{"enabled":..., "fn":..., "beteiligungen":[...]}`.

#### GET /firmenbuch/crawl/refresh/{fn}  ⚠️ live

Re-crawl one company (evi, optionally HVD). **Guarded:** `403` unless `CRAWL_API_ENABLED=1`. **Param:** `hvd` (bool, default false — uses metered HVD when true).

**Example response:** `{"fn":"475207i","status":"ok","hvd":"off","merged":true,"name":"Brantner Österreich GmbH"}`

#### GET /firmenbuch/crawl/resolve/{fn}  ⚠️ live

Resolve + crawl the corporate shareholders of `fn` so ownership edges become bidirectional. **Guarded:** `403` unless `CRAWL_API_ENABLED=1`. **Param:** `hvd` (bool).

---

### Firmenbuch Error Codes

| HTTP Code | When |
|-----------|------|
| 200 | Success |
| 400 | Invalid FN format, date > 7 days, bad parameters |
| 401 | Missing or invalid Bearer token |
| 403 | HVD token rejected, or live crawl disabled (`CRAWL_API_ENABLED≠1`) |
| 404 | Company not found, no search results, no changes in period |
| 429 | Rate limit exceeded (`/firmenbuch/*`: 30 req/min per token **per worker** — in-memory limiter, ~60/min effective with the current 2-worker unit) |
| 502 | evi.gv.at or HVD upstream error |
| 503 | HVD not configured (missing deps or token) |

---

## Electricity (E-Control AT)

> ⚠️ **Separate auth.** The `electricity` module validates its **own** Bearer token (`STROM_TARIF_API_KEY`): no credentials → `401` (global gate), a global `TOKENS` value → `403` (module rejects it), the electricity key → `200`. It is loaded dynamically from a separate `electricity` module (gitignored), like `firmenbuch_AT`.

Austrian electricity data: tariff lists and day-ahead spot-price charts.

---

### GET /electricity/tarifliste

Get a list of electricity tariffs.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `rows` | int | No | Number of tariffs to return (1–100, default 10) |
| `contentformat` | string | No | Response format (always `json`, default `json`) |

**Response:** dictionary with a `tariffs` list and metadata.

---

### GET /electricity/spotprices/chart/latest

Get the latest available day-ahead spot-price chart.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `range` | string | No | `singleday` (default) → `price_chart_YYYY-MM-DD.svg`; `range` → `price_chart_YYYY-MM-DD_YYYY-MM-DD.svg` |

**Response:** an SVG chart file.

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
| `timelimit` | string | No | `d`, `w`, `m` (default), `y` |
| `max_results` | int | No | Default: 8 |
| `page` | int | No | Results page number |
| `backend` | string | No | `auto`, `bing`, `duckduckgo`, `yahoo`, ... |
| `proxy` | string | No | Proxy URL passed to the search backend, e.g. `socks5h://127.0.0.1:9150` |
| `verify` | bool | No | Verify SSL for backend requests (default `true`) |

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
| `safesearch` | string | No | `on`, `moderate`, `off` (default) |
| `timelimit` | string | No | `d`, `w`, `m`, `y` |
| `site` | string | No | Restrict to domain |
| `exact` | bool | No | Exact phrase match |
| `exclude` | string | No | Comma-separated terms to exclude |
| `page` | int | No | Results page number |
| `filetype` | string | No | Filter by extension |
| `inurl` | string | No | Filter by URL fragment |
| `backend` | string | No | Search backend selection |
| `proxy` | string | No | Proxy URL passed to the search backend |
| `verify` | bool | No | Verify SSL for backend requests (default `true`) |

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

Returns the input text, sanitized to letters, digits and whitespace (everything else is stripped). Useful for health checks.

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" "https://your-server/api/echo?text=ping"
```

### GET /fetch_url

Fetch URL content using w3m or lynx. Only `http(s)` URLs are accepted (`file://` etc. return `400`); upstream failures return `502`.

**Parameters:** `url` (required), `tool` (`w3m` or `lynx`, default: `w3m`)

### GET /w3m_google

Web search backed by **DuckDuckGo** (historical name — w3m is no longer used on this path), with region mapping per domain.

**Parameters:** `query` (required), `num_results` (default: 10), `domain` (`at` default, `de`, `com`)

### GET /lynx

Fetch URL content using the lynx browser. Same `http(s)`-only rule as `/fetch_url`.

**Parameters:** `url` (required)

---

## PDF Conversion

### POST /pdf/to_md

Convert a PDF (≤10MB **and** ≤500 pages, `413` above either) to Markdown-like text. Anything that isn't a valid PDF returns `400`; scanned PDFs without OCR return `422` (no text extracted) with the local converter. Local conversion runs in a killable child process — a pathological PDF (e.g. decompression bomb) returns `504` after ~60s instead of hanging the worker.

**Converters (`method`):**
| `method` | Where | Notes |
|----------|-------|-------|
| `pdfplumber` *(default)* | local | fast, text-layer PDFs, no OCR |
| `llamaparse` | ☁️ LlamaCloud (US) | OCR + complex layouts (tables, multi-column); **the document is uploaded to an external service** |

With `method=llamaparse` these optional params apply: `tier` selects the LlamaParse mode (`fast` default, `cost_effective`, `agentic`, `agentic_plus` — higher tiers cost more credits), `language` the OCR language hint (ISO code, default `de`), **`wait`** (default `true`) and **`transfer`** (`inline` default, `throway`).

**Async jobs:** llamaparse documents beyond **~40 pages** are auto-converted as background jobs (a sync request would die at the 120s worker timeout — llamaparse runs at ~2s/page); `wait=false` forces it for any size. Async answer is `202` with `{"job_id", "status", "poll"}`; poll `GET /pdf/jobs/{job_id}` (same Bearer auth) until `status: done|failed`. Jobs are ephemeral (in-memory, evicted after 2h, gone on service restart), **max 1 llamaparse conversion at a time**, more than 10 jobs → `429`.

**No job zombies:** every job carries a hard deadline — default **20 minutes** (`PDF_JOB_DEADLINE_MIN` env). It's enforced at three points: the worker won't wait for the conversion slot past it, it aborts before writing results past it, and any status read flips an overdue queued/running job to `failed` (`"error": "auto-killed: …"`). Job files are evicted after 2h; results shared via throway expire independently after 4h.

**RAM discipline** (the box has ~1GB): queued async jobs spill their upload payload to disk (zero heap while waiting), the worker reads bytes only while holding the single conversion slot, explicit `gc.collect()` returns big buffers immediately, and throway-transferred results are dropped from memory. Local (pdfplumber) conversion runs in a child process capped at 1GB address space; the systemd unit caps the whole service at `MemoryMax=400M`.

**`transfer=throway`:** the markdown is uploaded to [skale.dev/throway](https://skale.dev/throway) (4h TTL, 5MB cap) and the response contains only `markdown_url` + `expires_in` instead of the full text — recommended for large documents. Auth for LlamaParse comes from `LLAMA_CLOUD_API_KEY` (env/.env) with a credgoo `llamacloud` fallback. Error mapping: key missing → `503`, quota/rate limit → `429`, LlamaParse failure → `502`, job timeout → `504`. The transfer target can be disabled per deployment with `THROWAY_ENABLED=0` (then `transfer=throway` answers `503`).

#### GET /pdf/jobs/{job_id}

Status/result of an async conversion job (same Bearer auth).

```json
{"job_id": "…", "status": "done", "created_at": "…", "pages": 23, "chars": 53689,
 "expires_in": 14400, "markdown_url": "https://skale.dev/throway/…"}
```

`status`: `queued` → `running` → `done` | `failed`. On `done`: `markdown` (inline) or `markdown_url` (with `transfer=throway`). On `failed`: `error` — including `"auto-killed: …"` when the job exceeded its deadline.

Multipart upload:

```bash
# small document, sync:
curl -H "Authorization: Bearer YOUR_TOKEN" -F file=@doc.pdf \
  "https://your-server/api/pdf/to_md"

# large scan: async job + result as throway link
curl -H "Authorization: Bearer YOUR_TOKEN" -F file=@scan.pdf \
  "https://your-server/api/pdf/to_md?method=llamaparse&wait=false&transfer=throway"
# → {"job_id": "...", "poll": "https://your-server/api/pdf/jobs/..."} → GET poll → markdown_url
```

**Response:** `{"filename", "converter", "pages", "chars", "markdown"}`

## Image → ASCII

### POST /itoa/convert

Convert an uploaded image to ASCII art. Multipart upload with form fields:

| Field | Type | Description |
|-------|------|-------------|
| `file` | file | Image file |
| `width` | int | Output width in characters (1–500, default 100) |
| `color` | bool | ANSI true-color output (default `false`) |
| `mode` | string | Palette name, e.g. `Standard`, `Blocks`, `Braille`, `Greek` (see app docs) |

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" -F file=@pic.png -F width=80 \
  "https://your-server/api/itoa/convert"
```

**Response:** `{"ascii": "..."}`


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

The service is deployed on the `amd` host and fronted at `https://amd.skale.dev/api`.

```bash
./deploy_api.sh
```

This script runs **on the server** and will:
1. `git pull` the **web_apis** repository into `/home/ubuntu/code/web_apis`
2. Sync dependencies via `uv sync --frozen` (updates `.venv` exactly per `uv.lock`)
3. Restart the `fastapi` systemd service

> **⚠️ Deployment note — dynamically-loaded modules.** `firmenbuch` (the Austrian company register + crawl/cache/ÖNACE layer, repo [firmenbuch_AT](https://github.com/devskale/firmenbuch_AT)) and `electricity` are **separate repositories**, symlinked into the project root and listed in `.gitignore`. They are **not pulled by `deploy_api.sh`** — to update their endpoints you must update/symlink those repos separately on the server. A normal deploy only touches the local modules (echo, w3m, lynx, duck, pdf, itoa). If a module's symlink is missing at startup, FastAPI logs `"<module> not found"` and its endpoints are simply absent.
>
> **Token scoping:** the global `TOKENS` gate every endpoint **except** `electricity`, which verifies its own Bearer token. Set `CRAWL_API_ENABLED=1` to allow the live `crawl/refresh` and `crawl/resolve` actions (otherwise they return `403`).
>
> **State:** `/firmenbuch/crawl/*` and `/firmenbuch/cache/*` require the Postgres cache (~302k companies, TTL: lookup 3 days / merged 14 days).

### Logs

```bash
sudo journalctl -u fastapi -f
```

API access logs are stored in `api.log`.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — manages Python (≥3.12) and the virtualenv itself
- Dependencies are declared in `pyproject.toml` and pinned in `uv.lock` (no `requirements.txt`); `uv sync` recreates `.venv` exactly. Note: the symlinked modules below share this venv, so their runtime deps (psycopg2, httpx, reportlab, rich, bs4, …) are part of `pyproject.toml` too.
- [firmenbuch_AT](https://github.com/devskale/firmenbuch_AT) — symlinked into project as `firmenbuch/` (gitignored; provides company register + crawl/cache + ÖNACE endpoints)
- `electricity/` — separate module symlinked into project (gitignored; provides `/electricity/*` with its own auth)

## Development

```bash
uv sync          # create .venv from uv.lock (includes dev group)
uv run pytest    # offline unit tests
TOKENS=devtoken uv run uvicorn main:app --reload   # local dev server on 127.0.0.1:8001
```

## Configuration

The service runs on port 8001 and uses gunicorn with uvicorn workers for optimal performance.

### Environment Variables (.env)

| Variable | Required | Description |
|----------|----------|-------------|
| `TOKENS` | ✅ | Comma-separated Bearer tokens |
| `HVDAT_TOKEN` | For HVD endpoints | BMJ HVD API token (or configure credgoo) |
| `LLAMA_CLOUD_API_KEY` | For llamaparse | LlamaParse key (credgoo `llamacloud` fallback) |
| `THROWAY_ENABLED` | No | `0` disables `transfer=throway` (default: enabled) |
| `PDF_JOB_DEADLINE_MIN` | No | Hard async-job deadline in minutes (default: 20) |
| `STROM_TARIF_API_KEY` | For electricity | E-Control API key (electricity module auth) |

### Security

> **⚠️ This repo is PUBLIC — never commit credentials.** No tokens, keys, or `.env` files belong in this repository (`.gitignore` covers `*.env` / `*.log*`). Tokens are configured server-side in `.env` or distributed via credgoo (`FETCH_URL_BEARER` etc.) — never hardcoded. Note: secrets from old commits remain in git history; history rewrites don't reliably un-leak them — rotate instead.

- Authentication is required for all endpoints using Bearer tokens; the app **fails closed** — with `TOKENS` missing or empty it refuses to start instead of disabling auth
- Tokens are configured in the .env file and loaded at startup (only the token count is logged, never the values)
- Token comparison is constant-time; bearer tokens are masked (short SHA-256 prefix) in access logs
- CORS allows all origins (handy for dev; active in production too — but `allow_credentials=False`, and auth is header-based, so no credentials are exposed cross-site)
- Rate limiting and input validation are implemented; the rate limiter is in-memory **per worker process** (see error table)
