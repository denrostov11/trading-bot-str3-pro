@echo off
if exist "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\paper_runtime_neustart\STOP" del "C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\paper_runtime_neustart\STOP"
start "" wscript.exe "C:\Users\denro\Desktop\Claude Code\Trading_Bot\TradingBot_Neustart.vbs"
echo NEUSTART-LAUF gestartet (Pro.1 Baseline, Pro.3 Volumen, C+; unbefristet; laeuft unsichtbar, Neustart bei Absturz).
