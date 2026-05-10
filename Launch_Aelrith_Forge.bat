@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON_CMD="

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_CMD=.venv\Scripts\python.exe"
)

if not defined PYTHON_CMD (
  py -3 -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo Python was not found.
  echo Install Python 3, then run this launcher again.
  pause
  exit /b 1
)

echo Launching Kon. with: %PYTHON_CMD%

%PYTHON_CMD% -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo.
  echo Required app packages are missing for this Python environment.
  echo.
  echo Recommended command:
  echo   %PYTHON_CMD% -m pip install -r requirements.txt
  echo.
  set /p INSTALL_DEPS="Install requirements now? [y/N] "
  if /i "!INSTALL_DEPS!"=="Y" (
    %PYTHON_CMD% -m pip install -r requirements.txt
    if errorlevel 1 (
      echo.
      echo Dependency installation failed.
      pause
      exit /b 1
    )
  ) else (
    echo.
    echo Launch cancelled. Install requirements, then run this file again.
    pause
    exit /b 1
  )
)

if /i "%~1"=="--check" (
  echo Launcher check passed.
  exit /b 0
)

%PYTHON_CMD% -m aelrith_forge
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Kon. exited with error code %EXIT_CODE%.
)

pause
exit /b %EXIT_CODE%
