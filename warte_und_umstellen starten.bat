@echo off
rem Einmaliger Wartebot fuer die Umstellung am 17.10.2026 (unsichtbar). Keine Windows-Aufgabe, kein Autostart.
start "" "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\venv\Scripts\pythonw.exe" "C:\Users\denro\Desktop\Claude Code\Trading_Bot\warte_und_umstellen.py"
echo Wartebot gestartet. Er sendet um 09:00 eine Vorab-Nachricht und stellt um 12:15 um. Protokoll: umstellung_log.txt
echo Den PC bis zur Erfolgsmeldung nicht neu starten und nicht in den Standby schicken.
