# Issue: `pdf2md` scheitert an großen Text-PDFs — mp.Queue-Deadlock im pdfplumber-Child (504 nach exakt 60s)

**Status:** offen (Diagnose abgeschlossen, Fix-Vorschlag steht)
**Schwere:** hoch für den Use-Case — JEDES Text-PDF mit >~45 Seiten (Ergebnis >64KB) scheitert deterministisch
**Aufgetreten:** 2026-10-13, `pdf2md ~/Documents/tu-forschung/thesis.pdf` (149 Seiten, 3,1MB, Text-PDF)
**Reporter:** Session-Diagnose

---

## 1. Symptom

```
$ time pdf2md ~/Documents/tu-forschung/thesis.pdf --out /tmp/thesis.md
error: 504 job deadline exceeded server-side (default 20 min) — retry with --no-wait
real  1m1.458s
```

Drei Irreführungen auf einmal:
- Es war **kein Job** — pdfplumber läuft synchron, das Job-System gilt nur für llamaparse.
- Die Frist war nicht „20 min", sondern der 60s-Konvertierungs-Watchdog (`PDF_CONVERT_TIMEOUT_S`).
- `--no-wait` ist llamaparse-only — für pdfplumber wirkungslos.

## 2. Ursache: Queue-Deadlock, nicht Performance

Gegenproben (lokal, pdfplumber 0.11.10):

- **149 Seiten komplett: 4,7s** (Ø 0,03s/page, langsamste Seite 0,26s, 1415 chars/page — echtes Text-PDF, kein Scan)

Das Dokument ist harmlos — der Child auf amd **hängt**, statt langsam zu sein
(504 heißt `proc.is_alive()` nach 60s: der Child lebt noch und hat kein Ergebnis geliefert).

Der Code in `pdf/router.py::pdf_to_md` (pdfplumber-Zweig):

```python
proc.start()
proc.join(PDF_CONVERT_TIMEOUT_S)      # ← Parent wartet hier 60s
...
status, payload = out_q.get_nowait()  # ← Queue wird ERST DANACH gelesen
```

Das ist der in der Python-Doku dokumentierte mp.Queue-Deadlock: die Pipe hinter
`multiprocessing.Queue` puffert ~64KB. `put()` eines größeren Ergebnisses kehrt
zurück, aber der Feeder-Thread kann nicht flushen, während der Parent nicht liest.
Der Child-Exit blockiert auf den Feeder (Queue-Finalizer `join_thread()`), der
Parent blockiert in `join()` — beide warten aufeinander, bis der Watchdog killt.

**Warum kleine PDFs laufen:** Ergebnis < Pipe-Puffer (~64KB ≈ <45 Seiten Text)
→ Feeder flusht sofort → Child exitet sauber → `join()` kehrt zurück.
**Warum große deterministisch sterben:** Ergebnis > 64KB → Deadlock → immer
exakt 60s → Kill → 504. Messung: 61,4s für die 149-Seiten-Thesis (~210KB Text).

## 2b. Smoking-Gun-Repro (2026-10-13, lokal, spawn-Kontext wie Server)

`/tmp/queue_deadlock_repro.py` — Server-Muster exakt nachgebaut (spawn-Child,
mp.Queue, `join(timeout)` vor Drain, 300KB-Ergebnis):

```
server-pattern (join first): alive_after_join=True result=ok 300KB (15.0s)  <- DEADLOCK proven
fix-pattern    (drain first): alive=False result=ok 300KB in 0.1s
leftover children: []
```

Beide Punkte bestätigt: (1) der Child hängt am Feeder-Flush, solange der
Parent nicht liest; (2) `get_nowait()` NACH dem Join-Timeout findet das
fertige Ergebnis — d.h. der Server killt einen Child, dessen Arbeit bereits
erledigt war, und verwirft sie mit der 504.

## 3. Betroffene Fläche

| Komponente | Betroffen? | Anmerkung |
|---|---|---|
| `pdf/router.py` pdfplumber-Zweig | ✅ **ja** | Deadlock: join vor Queue-Drain |
| Skill `pdf2md` | ✅ teils | 504-Meldung pauschal auf llamaparse-Text gemappt (falscher Remedial-Hinweis) |
| llamaparse-Pfad (Jobs) | ❌ nein | eigener Worker-Thread, keine mp.Queue |
| Grenzen 10MB/500 Seiten | ❌ nein | nicht erreicht (3,1MB/149 Seiten) |

## 4. Fix-Vorschlag

### Fix 1 (chirurgisch, behebt die Deadlock-Klasse): Queue DRAINEN vor join

```python
proc.start()
# Drain the queue BEFORE joining — mp.Queue pipes buffer ~64KB; a result
# bigger than that blocks the child's feeder thread while the parent sits
# in join(): the documented multiprocessing deadlock. get(timeout=...) keeps
# the watchdog; join afterwards is safe (child can exit once flushed).
try:
    status, payload = out_q.get(timeout=PDF_CONVERT_TIMEOUT_S)
except queue_mod.Empty:
    proc.kill()
    proc.join()
    logging.error(...)
    raise HTTPException(504, detail="PDF processing timed out.")
proc.join(PDF_CONVERT_TIMEOUT_S)  # jetzt harmlos: Feeder kann flushen
```

- Watchdog bleibt (get-Timeout statt join-Timeout), RLIMIT_AS bleibt, gunicorn-120s bleibt eingehalten.
- Wirkung: jedes Text-PDF, dessen Konvertierung <60s CPU braucht (auf amd: mehrere
  hundert Seiten), konvertiert korrekt. Die Thesis: ~5–25s.

### Fix 2 (Client, pdf2md-Skill): 504-Meldung pro Methode

- pdfplumber-504: „server conversion watchdog (60s) hit — likely pathological PDF"
- llamaparse-504: wie bisher (Job-Deadline / --no-wait Hinweis)

### Fix 3 (optional, erst bei Bedarf): pdfplumber >40 Seiten als async Job

Wie llamaparse: 202 + Poll. Erst nötig, wenn Dokumente >60s CPU brauchen
(500-Seiten-Wälzer auf der kleinen amd-Box). Der Client pollt 202 bereits generisch.

## 5. Abgewogene Optionen (Nutzer-Vorschläge)

1. **„Große PDFs nur mit key"** — nicht nötig: serverseitig ist bereits ALLES
   hinter `FETCH_URL_BEARER` (verify_token). Kosten-/Cloud-Kritisch ist nur
   llamaparse — das bleibt opt-in (`--method llamaparse`); pdfplumber ist lokal
   auf amd und gratis. Mit Fix 1 gibt es keinen Grund, große Text-PDFs zu gate'n.
2. **„Nicht nur PDFs, sondern Docs (Office, Images)"** — valides Folge-Thema,
   separater Skill/Issue (mammoth/openpyxl/python-pptx lokal, OCR für Images,
   llamaparse als Scan-Fallback). NICHT in diesen Fix mischen: dieser hier ist
   ein 3-Zeilen-Deadlock-Fix mit sicherer Diagnose.

## 6. Workaround (bis zum Fix)

Ergebnis unter 64KB halten: Seitenbereiche konvertieren (z.B. qpdf/mlp splitten)
oder `--method llamaparse` (läuft über das Job-System, uploadet das Dokument aber
in die LlamaCloud — für eine TU-Thesis unerwünscht).
