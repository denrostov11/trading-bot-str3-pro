# Trading-Bot — Strategie 3 „Pro" (Trendlinien-Bruch, 4h-Swing)

Automatisierter **Paper-Trading**-Forward-Test einer rein technischen Trendlinien-Strategie
auf 4h-Charts. **Keine echten Orders, kein Geldfluss** — der Bot erzeugt ausschließlich
Signale/virtuelle Trades und meldet sie (optional) per Telegram. Ziel ist ein sauber
auditierter, look-ahead-freier Zwei-Monats-Vergleich mehrerer Filter-Varianten (Pro.1–Pro.8).

> ⚠️ **Kein Finanzrat.** Dieses Projekt ist ein Forschungs-/Testwerkzeug. Es führt keine
> realen Trades aus und gibt keine Anlageempfehlungen.

---

## Strategie in Kürze
- **A+-Trendlinie:** 3+ Wick-Taps, 6+ Kerzen Abstand, < 45°, Action- und Safety-Line bilden
  einen **konvergierenden Keil** (Safety Line muss intakt sein — keine Kerzen durchkreuzen).
- **Einstieg:** 4h-Kerze schließt jenseits der Action-Line → Fill = **Open der nächsten Kerze**.
- **Stop:** Safety-Line-Projektion an Kerze (Bruch + 4). **Ziel:** nächste relevante S/R-Zone.
- **Break-even:** klassenabhängige Automatik (Modi BE-0…BE-4), Prüfung auf 15-Min-Kerzen.
- **Varianten Pro.1–Pro.8:** Baseline + EMA200 / RVOL / ATR-Regime / Kombi / Breakout-Qualität /
  Trendqualität (diagnostisch) / Daily-Marktstruktur (nicht konfiguriert) — alle bewerten
  **denselben unveränderlichen Snapshot** (gemeinsame `parent_signal_id`).

## Architektur (`Prototyp/`)
| Paket | Inhalt |
|-------|--------|
| `engine/` | Kern-Engine: `dataaccess`, `cache`, `aggregate_4h`, `quality`, `baseline`, `features`, `variants`, `varstate`, `ledger`, `tracker`, `cycle`, `orchestrate`, `reporting(_pdf)`, `run_paper`, `run_reports`, `run_loop`, `instruments` |
| `notify/` | Telegram als **reine Ausgabeschicht**: `config`, `redact`, `transport`, `messages`, `router`, `queue`, `scheduling`, `commands`, `dispatcher`, `live` |
| `tests/` | pytest-Suite (aktuell **99 Tests grün**), inkl. Realdaten-Fixture + Golden-Output der Erkennung |
| `scan_100.py` | Kanonische Trendlinien-Erkennung (Pivots, Linien, A+-Prüfung, Safety/Keil) |

**Grundsätze:** Die lokale DB (JSON-Dateien) ist die verbindliche Quelle; Telegram ist nur
Ausgabe und darf niemals einen Trade verändern. Strikt kein Look-ahead — nur abgeschlossene
Kerzen. Jeder Kandidat wird protokolliert (auch abgelehnte: `REJECTED_*`/`DIAGNOSTIC`).

### Lücken-Aufholen (PC darf zwischendurch aus sein)
Läuft der Rechner nicht durchgehend, holt die Engine beim nächsten Start jede verpasste
4h-Kerze **der Reihe nach** nach (`analyze_instrument_history`) — jede Bewertung sieht nur
Daten bis zu *ihrer* Kerze (kein Look-ahead). Ein Wasserstand pro Symbol (`processed.json`)
verhindert Doppelverarbeitung. `run_loop.py` ist neustart-/resume-fest (Einzelinstanz-Sperre,
`--start-now`, Wiederaufnahme aus `START_MANIFEST.json`).

---

## Setup
```bash
# 1) Python 3.12, virtuelle Umgebung
python -m venv venv
venv/Scripts/activate            # Windows (Bash: source venv/Scripts/activate)
pip install -r Prototyp/requirements.txt

# 2) Konfiguration: .env aus Vorlage anlegen und ausfuellen (NIEMALS committen!)
cp Prototyp/.env.example Prototyp/.env
#   -> TELEGRAM_BOT_TOKEN, Chat-IDs, TELEGRAM_AUTHORIZED_USER_IDS eintragen

# 3) Tests
cd Prototyp && ../venv/Scripts/python -m pytest tests/ -q
```

## Ausführen
```bash
# Ein einzelner Paper-Zyklus (lokal, ohne Telegram):
Prototyp> ../venv/Scripts/python -c "from engine import run_paper; print(run_paper.run_once())"

# Dauer-Loop (STUFE 1, sofortiger Start):
Prototyp> ../venv/Scripts/python engine/run_loop.py --start-now --stage-days 3
```

## Sicherheit / Secrets
- **`.env` ist in `.gitignore` und wird nie versioniert.** Nur `.env.example` (Platzhalter) liegt im Repo.
- Der Telegram-Token und die Chat-IDs gehören ausschließlich in die lokale `.env`.
  Bei Verdacht auf Leak: beim BotFather `/revoke`, neuen Token in `.env`.
- Generierte Artefakte (PNG/PDF/DOCX/ZIP), Laufzeit-Zustand und `data_cache/` sind bewusst ausgeschlossen.

## Status & Fahrplan
Engine-Kern **v1.0** komplett. Reihenfolge des gestuften Rollouts:
**STUFE 1** (24 Symbole, 2–3 Tage) → **STUFE 2** (~100 Symbole, ~1 Woche) →
Testkonfiguration einfrieren → Freigabe → **Zwei-Monats-Haupttest**.
Projekt-Chronologie und Entscheidungen: siehe `CHANGELOG.md` und die Steuer-/Audit-Dokumente
im Wurzelverzeichnis (`AUDIT_REPORT.md`, `SPEC_CLEANED.md`, `ARCHITECTURE_PROPOSAL.md`, …).
