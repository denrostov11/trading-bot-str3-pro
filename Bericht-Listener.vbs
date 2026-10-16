' Bericht-Listener (Telegram-Abruf "bericht" in der Gruppe STR3 System) - unsichtbar, mit Watchdog.
' Startet notify\report_listener.py und startet es nach einem Absturz nach 30 s automatisch neu.
' Kontrollierter Stopp: Datei report_listener_runtime\STOP anlegen (siehe "Bericht-Listener stoppen.bat").
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
stopFile = "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\report_listener_runtime\STOP"
cmd = """C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\venv\Scripts\pythonw.exe"" ""C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\notify\report_listener.py"""
Do
  If fso.FileExists(stopFile) Then WScript.Quit
  WshShell.Run cmd, 0, True
  WScript.Sleep 30000
Loop
