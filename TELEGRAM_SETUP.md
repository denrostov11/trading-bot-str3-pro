# TELEGRAM_SETUP.md — Str.3 Pro (Einrichtungsanleitung, ENTWURF)

> Status: ENTWURF (vor Implementierung). Enthält KEINE echten Tokens/Chat-IDs. Dient dir zur Vorbereitung
> der 10 Telegram-Ziele, damit bei Freigabe alles bereitliegt. Telegram ist optional und verursacht keine
> Claude-Credits; die lokale Datenbank bleibt die verbindliche Quelle.

## 1. Übersicht der 10 Ziele
| Ziel | Zweck | ENV-Schlüssel |
|---|---|---|
| Pro.1-Gruppe | Baseline | STR3_PRO1_CHAT_ID |
| Pro.2-Gruppe | EMA200 | STR3_PRO2_CHAT_ID |
| Pro.3-Gruppe | Volumenfilter | STR3_PRO3_CHAT_ID |
| Pro.4-Gruppe | ATR-Regime | STR3_PRO4_CHAT_ID |
| Pro.5-Gruppe | Kombinationsfilter | STR3_PRO5_CHAT_ID |
| Pro.6-Gruppe | Breakout-Qualität | STR3_PRO6_CHAT_ID |
| Pro.7-Gruppe | Trendqualität (diagnostisch) | STR3_PRO7_CHAT_ID |
| Pro.8-Gruppe | Daily-Marktstruktur (noch not_configured) | STR3_PRO8_CHAT_ID |
| Vergleichsgruppe | Variantenvergleich/Rankings | STR3_COMPARISON_CHAT_ID |
| Systemgruppe | Fehler/Datenqualität/Neustart | STR3_SYSTEM_CHAT_ID (optional) |

## 2. Bot erstellen (einmalig)
- In Telegram @BotFather → `/newbot` → Name + Benutzername → Token erhalten.
- Token gehört NUR in die lokale `.env` (`TELEGRAM_BOT_TOKEN=`). Niemals in Code/Backup/Chat posten.
- EIN Bot bedient alle 10 Gruppen (ein Token, viele Chat-IDs).

## 3. Gruppen anlegen und Bot hinzufügen
- 10 Telegram-Gruppen anlegen (Namen z. B. „Str3 Pro1 Baseline" … „Str3 Vergleich", „Str3 System").
- Den Bot in JEDE Gruppe als Mitglied hinzufügen; Rechte zum Posten (bei Bedarf Admin).
- In jeder Gruppe einmal eine Nachricht schreiben, damit der Bot die Gruppe „sieht".

## 4. Chat-IDs sicher ermitteln
- Ein Hilfsskript (bei Freigabe bereitgestellt) liest per getUpdates die Gruppen-Chat-IDs aus und zeigt sie
  dir an (Gruppen-IDs sind negativ). Du trägst sie selbst in `.env` ein. Chat-IDs erscheinen nie in Logs.

## 5. Autorisierte Nutzer
- Deine Telegram-User-ID (nicht die Gruppen-ID) in `TELEGRAM_AUTHORIZED_USER_IDS=` (kommagetrennt).
- Nur diese IDs dürfen Befehle auslösen; alle anderen werden ignoriert.

## 6. Befehle (nur lesend, keine Aktionen)
- Variantengruppe: `/status` `/offene_trades` `/letzte_trades` `/bilanz` `/wochenbericht` `/bericht_30_tage`
  `/watchlist` `/parameter` `/datenstatus`.
- Vergleichsgruppe: `/vergleich` `/ranking` `/vergleich_7_tage` `/vergleich_30_tage` `/vergleich_gesamt`
  `/filterwirkung` `/systemstatus` `/datenqualitaet` `/offene_trades_alle`.
- Befehle lösen nie echte Orders/Shell/Codeausführung aus; ändern keine Konfiguration; zeigen keine Geheimnisse.

## 7. Betrieb & Wartung (nach Implementierung)
- Testnachricht senden · Warteschlange prüfen · fehlgeschlagene Zustellungen erneut anstoßen · Berichte
  manuell anfordern · alle Telegram-Ausgaben vorübergehend deaktivieren (DISABLED_BY_CONFIGURATION) —
  Details folgen mit der Umsetzung. Bei deaktiviertem Telegram läuft Paper-Trading + lokale Auswertung normal.

## 8. Sicherheit (Kurz)
- `.env` nie in Versionskontrolle/Backup. Tokens/volle Chat-IDs nie in Logs/Fehlern/Berichten.
- Telegram ist nur Ausgabeschicht; ein Telegram-Ausfall ändert keine Trades und stoppt keinen Scan.
