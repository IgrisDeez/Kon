@echo off
cd /d "%~dp0"
python run_aelrith_forge.py
if errorlevel 1 (
  echo.
  echo Python launcher failed. Trying py...
  py run_aelrith_forge.py
)
pause
