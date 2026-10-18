' Neustart-Lauf Strategie 3 Pro (ab 17.10.2026): Pro.1 Baseline, Pro.3 Volumen, C+ - unbefristet, unsichtbar, mit Watchdog.
' Startet engine\run_loop.py --neustart und startet es nach einem Absturz nach 30 s automatisch neu.
' Der Lauf nimmt nach jedem Neustart aus dem START_MANIFEST wieder auf und holt verpasste 4h-Kerzen nach.
' Kontrollierter Stopp: Datei paper_runtime_neustart\STOP anlegen (siehe "NEUSTART-LAUF stoppen.bat").
' AUTOSTART: Diese Datei gehoert in den Autostart-Ordner (shell:startup). Der alte Eintrag TradingBot_2Monate.vbs
' muss dort deaktiviert sein (Umbenennen in TradingBot_2Monate.vbs.disabled).
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
stopFile = "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\paper_runtime_neustart\STOP"
cmd = """C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\venv\Scripts\pythonw.exe"" ""C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\engine\run_loop.py"" --neustart"
Do
  If fso.FileExists(stopFile) Then WScript.Quit
  WshShell.Run cmd, 0, True
  WScript.Sleep 30000
Loop
