@echo off
setlocal
cd /d "%~dp0"
title Stratix
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py %*
    goto finished
)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    py -3 run.py %*
    goto finished
)
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: no se encontro Python 3. Instala Python o prepara .venv.
    pause
    exit /b 1
)
python run.py %*
:finished
set "stratixExit=%errorlevel%"
if not "%stratixExit%"=="0" pause
exit /b %stratixExit%
