@echo off
setlocal enabledelayedexpansion

:: ------------------------------------------------------------------
:: Guarantee this window stays open no matter what happens below.
:: Double-clicking a .bat runs it via "cmd /c", which closes the
:: console the instant the script finishes OR hits anything that
:: aborts the batch early - sometimes before a `pause` further down
:: is ever reached. That's almost always why a .bat appears to
:: "flash and close instantly." Relaunching ourselves once inside a
:: persistent `cmd /k` window sidesteps that completely: cmd /k keeps
:: the window open even if the script inside crashes outright.
:: ------------------------------------------------------------------
if /i "%~1"=="__edith_relaunched__" (
    shift
) else (
    start "E.D.I.T.H." cmd /k "%~f0" __edith_relaunched__
    exit /b
)

chcp 65001 >nul
title E.D.I.T.H. - Intelligence Framework
cd /d "%~dp0"

echo.
echo  ============================================================
echo    E.D.I.T.H. - Starting All Systems
echo  ============================================================
echo.

:: -- Clear stale Python bytecode cache --------------------------
:: NOTE: intentionally NOT using "for /d /r ... do ( ... )" here.
:: cmd.exe's FOR /R, combined with a multi-line parenthesized DO
:: block, breaks with "...was unexpected at this time." whenever the
:: current directory path contains parentheses (e.g. a folder named
:: "EDITH_v7_fixed (2)", which Windows creates automatically when you
:: extract/save a duplicate). Using "dir" to list matches and feeding
:: them through "for /f" instead sidesteps that bug entirely, since
:: the paths are handled as plain text rather than re-parsed as code.
echo [EDITH] Clearing Python cache...
for /f "delims=" %%d in ('dir /s /b /ad "__pycache__" 2^>nul') do (
    rd /s /q "%%d" 2>nul
)
del /s /q *.pyc >nul 2>nul

:: -- Locate Python ------------------------------------------------
set "PYTHON="
for %%P in (python python3 py) do (
    if not defined PYTHON (
        %%P --version >nul 2>&1
        if not errorlevel 1 set "PYTHON=%%P"
    )
)
if not defined PYTHON (
    color 0C
    echo.
    echo  [ERROR] Python not found. Install Python 3.10+ from https://python.org
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    goto :end
)

:: -- Confirm main.py exists ---------------------------------------
if not exist "main.py" (
    color 0C
    echo.
    echo  [ERROR] main.py not found in this folder: %cd%
    echo  Move run.bat into the same folder as main.py and try again.
    echo.
    goto :end
)

:: -- Launch ---------------------------------------------------------
echo [EDITH] Launching with !PYTHON!...
echo.
!PYTHON! main.py
if errorlevel 1 (
    color 0C
    echo.
    echo  [ERROR] E.D.I.T.H. exited with an error. See the messages above.
)

:end
echo.
echo  ------------------------------------------------------------
echo  Press any key to close this window...
pause >nul
