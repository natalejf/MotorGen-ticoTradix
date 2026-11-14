@echo off
cd /d "%~dp0"
title TradingNote - Motor Genetico & Creador de Algoritmos
color 0F

echo ===============================================================================
echo                TRADINGNOTE · MOTOR GENETICO & LABORATORIO                     
echo ===============================================================================
echo.
echo [1/2] Verificando entorno Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python en el sistema. Asegurate de tener Python instalado y anadido al PATH.
    pause
    exit /b
)
echo [OK] Python detectado.
echo.
echo [2/2] Iniciando servidor backend y abriendo el navegador...
echo.
echo La aplicacion estara disponible en: http://127.0.0.1:8000
echo Para detener el servidor en cualquier momento, presiona CTRL+C o cierra esta ventana.
echo ===============================================================================
echo.

python run.py
pause
