@echo off
if exist "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\report_listener_runtime\STOP" del "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\report_listener_runtime\STOP"
start "" wscript.exe "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Bericht-Listener.vbs"
echo Bericht-Listener gestartet (laeuft unsichtbar, Neustart bei Absturz).
