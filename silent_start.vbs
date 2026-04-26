Set WshShell = CreateObject("WScript.Shell")
' The 0 at the end tells Windows to run the batch file in hidden mode
WshShell.Run chr(34) & "C:\Users\blake\Documents\School\Projects\Code\GitHub\Computer Switch\run_remote.bat" & chr(34), 0
Set WshShell = Nothing