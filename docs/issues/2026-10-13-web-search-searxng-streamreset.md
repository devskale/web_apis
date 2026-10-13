# Issue: `web-search`-Skill schlägt fehl mit h2 `StreamReset` — öffentliche SearXNG-Instanzen

**Status:** offen (Diagnose abgeschlossen, Fix-Vorschlag steht)
**Schwere:** mittel — betrifft nur den `web-search`-Skill, nicht die API
**Aufgetreten:** 2026-10-13, pi-Session (`web-search "process reward model …"`)
**Reporter:** Session-Diagnose (unii/uniinfer-Kontext)

---

## 1. Symptom

Der pi-Skill `web-search` (`~/.local/bin/web-search` →
`~/.pi/agent/git/github.com/devskale/skale-skills/skills/web-search/`) bricht
mit einem h2-Fehler ab:

```
tu error: <StreamReset stream_id:3, error_code:2, remote_reset:True>
```

`error_code:2` = HTTP/2 `INTERNAL_ERROR`, `remote_reset:True` = **der Server**
hat den Stream abgebrochen. `stream_id:3` = der dritte Stream auf einer
einzigen HTTP/2-Verbindung.

**Wichtig:** das Label „tu error" im Prompt ist irreführend — der Fehler kommt
**nicht** von TU Aqueduct, nicht von uniinfer und nicht von pi. Er kommt aus
dem `web-search`-Skill selbst.

## 2. Ursache

Der Skill nutzt per Default **öffentliche SearXNG-Instanzen** (`pyproject.toml`:
`requests>=2.31.0`, `credgoo`; `scripts/search.py` mit `urllib`/`requests`).
Öffentliche Instanzen sind chronisch überlastet, drosseln pro IP und brechen
mitten im Request die Verbindung ab. Über eine langlebige HTTP/2-Verbindung
(keep-alive) trifft das den zweiten oder dritten Request — daher `stream_id:3`.

Gegenprobe: unser eigener Proxy (`uniioai-proxy` auf amd) läuft mit
`httpx` + `http2=True` gegen TU Aqueduct und hatte im selben Zeitraum bei 43+
Streams **null** Resets. h2 ist also stabil, wenn der Gegenüber mitspielt.

## 3. Betroffene Fläche

| Komponente | Betroffen? | Anmerkung |
|---|---|---|
| `web_apis` `/duck/search` (diese API) | ❌ nein | Läuft über ddgs (amd, yahoo) + private SearXNG (lubu) mit Circuit Breaker |
| `web-search`-Skill (skale-skills) | ✅ **ja** | Default = öffentliche SearXNG-Instanzen |
| uniinfer / TU Aqueduct | ❌ nein | String existiert im Package nicht (0 grep-Treffer) |
| pi | ❌ nein | Der Fehler war User-Input, keine Assistant-Message |

## 4. Fix-Vorschlag

Der Skill hat bereits einen **privaten Duck-API-Backend-Modus** über
`credgoo`. Der wäre stabiler als die öffentlichen Instanzen — und es gibt eine
eigene, gut gewartete Such-API auf `https://amd.skale.dev/api/duck/search`:

- Cache (12 h TTL, 1000 Einträge LRU)
- Primary: ddgs/yahoo von der amd-Datacenter-IP
- Fallback: private SearXNG auf lubu mit Circuit Breaker (2 Fehler → offen,
  Half-Open-Probe nach 5 Min)
- Burst-Schutz: ddgs-Calls box-weit serialisiert (flock), übersättigte Queues
  failen schnell mit 502 statt zu stauen

**Konkret:** den Skill auf die eigene API zeigen statt auf öffentliche
SearXNG-Instanzen. Das eliminiert die gesamte Klasse
„öffentliche Instanz kappt die Verbindung".

## 5. Zu klären

1. Soll der Skill Default auf `https://amd.skale.dev/api/duck/search` zeigen
   (Token via credgoo), mit öffentlichen SearXNG-Instanzen nur noch als
   letzten Fallback?
2. Oder reicht es, die Instanz-Liste im Skill zu rotieren (mehr/weniger
   öffentliche Endpunkte)?
3. Separat, aber verwandt: der Skill sollte den Fehler nicht als „tu error"
   labeln — das Label hat mich initially auf die falsche Fährte (uniinfer/TU)
   geführt. Der Absender gehört in die Message.

## 6. Workaround (sofort wirksam)

Solange kein Fix landet: `web-search`-Aufrufe mit Geduld wiederholen — der
Fehler ist transient (nicht jeder Request trifft eine überlastete Instanz).
Oder direkt die API nutzen:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://amd.skale.dev/api/duck/search?query=<urlencoded>&max_results=10"
```
