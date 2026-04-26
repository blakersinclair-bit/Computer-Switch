@echo off
:loop
echo Starting Flask Server...
"C:\Users\blake\AppData\Local\Programs\Python\Python313\python.exe" App.py
echo.
echo Server crashed or stopped. Restarting in 2 seconds...
timeout /t 2
goto loop