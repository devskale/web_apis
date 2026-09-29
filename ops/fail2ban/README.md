# fail2ban on amd — versioniert in diesem Repo

Diese drei Dateien sind der **deployte Sollzustand** von `/etc/fail2ban/` auf
amd. Sie liegen hier im Repo, damit sie nicht nur auf einer Maschine existieren.

| Datei | Ziel |
|-------|------|
| `api-auth.conf` | `/etc/fail2ban/filter.d/api-auth.conf` |
| `api-auth-jail.conf` | `/etc/fail2ban/jail.d/api-auth-jail.conf` |
| `01-ignoreip-own-infra.conf` | `/etc/fail2ban/jail.d/01-ignoreip-own-infra.conf` |

Deploy (auf amd, als root):

```bash
cp ops/fail2ban/api-auth.conf            /etc/fail2ban/filter.d/
cp ops/fail2ban/api-auth-jail.conf        /etc/fail2ban/jail.d/
cp ops/fail2ban/01-ignoreip-own-infra.conf /etc/fail2ban/jail.d/
fail2ban-client -t          # config prüfen
fail2ban-client restart     # jails neu laden (ignoreip ist global)
```

## Warum die Werte so sind

**Filter `api-auth`** zählt nur echte Ablehnungen: `no-auth` **und** HTTP 401.
Ein token-loser Aufruf, der **erfolgreich** ist, wird von `web_apis` als
`no-auth-ok` geloggt und kann nicht matchen. Vorher matchte jedes `no-auth` —
auch erfolgreiche 200er auf öffentlichen Endpoints.

**Jail `api-auth`: `maxretry=10 / findtime=1h / bantime=1h`** (vorher
`5 / 10m / 1 Monat`).

Der jail prüft einen Application-Layer-Token, keinen Port-Scan — 401er sind
**normal** (abgelaufener Token, falscher Client, Tippfehler). „5 Fehlversuche
in 10 Minuten = 30 Tage" hat amd und die Heim-Linie offline genommen
(DB-Pfad und autossh-Tunnel, 509× Timeout), weil ein **inbound** Ban beide
Richtungen kappt: die gebannte Gegenstelle braucht unsere SYN-ACKs. Progression
statt One-Shot: 1 Stunde, nicht 1 Monat.

**`banaction` wird hier nicht gesetzt** — die Zeilen kommen aus
`defaults-debian.conf` `[DEFAULT]`. Sie zusätzlich hier zu setzen bricht auf
fail2ban 1.1.0 die Action-Interpolation (`nftables[port="8001",`).

## ignoreip

Eigene Infrastruktur, plus die geteilte CGNAT-IP von ubugrill
(`91.141.100.14`). **Achtung:** eine CGNAT-IP nimmt auch andere Nutzer desselben
NAT aus — der api-auth-jail ist deshalb nicht die einzige Verteidigungslinie,
sondern nur die Grobe (`web_apis` selbst zählt inzwischen nur noch echte 401s).
