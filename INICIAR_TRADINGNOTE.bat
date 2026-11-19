@echo off
setlocal
cd /d "%~dp0"
title TradingNote - Motor Genetico

:: 1. Entorno virtual local con dependencias
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import uvicorn, fastapi" >nul 2>&1
    if not errorlevel 1 (
        ".venv\Scripts\python.exe" run.py %*
        goto finished
    )
)

:: 2. Python en PATH con dependencias (ej. Python 3.10)
python -c "import uvicorn, fastapi" >nul 2>&1
if not errorlevel 1 (
    python run.py %*
    goto finished
)

:: 3. py -3.10 con dependencias
py -3.10 -c "import uvicorn, fastapi" >nul 2>&1
if not errorlevel 1 (
    py -3.10 run.py %*
    goto finished
)

:: 4. py -3.11 con dependencias
py -3.11 -c "import uvicorn, fastapi" >nul 2>&1
if not errorlevel 1 (
    py -3.11 run.py %*
    goto finished
)

:: 5. py -3 general con dependencias
py -3 -c "import uvicorn, fastapi" >nul 2>&1
if not errorlevel 1 (
    py -3 run.py %*
    goto finished
)

:: 6. Si ninguna instalacion tiene las librerias, buscar cualquier Python disponible para instalarlas
set "BASE_PY="
if exist ".venv\Scripts\python.exe" set "BASE_PY=.venv\Scripts\python.exe"
if "%BASE_PY%"=="" (
    python --version >nul 2>&1
    if not errorlevel 1 set "BASE_PY=python"
)
if "%BASE_PY%"=="" (
    py -3.10 --version >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3.10"
)
if "%BASE_PY%"=="" (
    py -3.11 --version >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3.11"
)
if "%BASE_PY%"=="" (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3"
)

if "%BASE_PY%"=="" (
    echo ======================================================================
    echo ERROR: No se encontro Python 3 instalado en el sistema.
    echo Por favor instala Python 3.10 o superior marcando "Add to PATH".
    echo ======================================================================
    pause
    exit /b 1
)

echo ======================================================================
echo Se detecto Python (%BASE_PY%), pero faltan dependencias requeridas.
echo Instalando dependencias desde requirements.txt...
echo ======================================================================
%BASE_PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Hubo un fallo al instalar las dependencias con pip.
    pause
    exit /b 1
)

%BASE_PY% run.py %*

:finished
set "stratixExit=%errorlevel%"
if not "%stratixExit%"=="0" pause
exit /b %stratixExit%
