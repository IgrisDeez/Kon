Copyright (c) 2026 Igers. All rights reserved. Kon. is proprietary software. Unauthorized copying, modification, redistribution, reverse engineering, or derivative use is prohibited without written permission from Igers.

# Kon.

Kon. is a Windows desktop automation and OCR assistant for rolling and monitoring Specs and Powers. It uses a PySide6 UI with backend OCR parsing, startup/recovery checks, popup handling, watchdog safety, Discord reporting, and local debug logs.

The Python package is still named `aelrith_forge` for compatibility with existing settings, logs, scripts, and imports.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- Tesseract OCR installed at:
  `C:\Program Files\Tesseract-OCR\tesseract.exe`
- The game/client visible on screen while the macro is running

EasyOCR is optional. Install it only if you want EasyOCR-assisted reads:

```powershell
python -m pip install easyocr
```

## Setup

From the repository folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For development or tests:

```powershell
python -m pip install -r requirements-dev.txt
```

## Run

Launch from PowerShell:

```powershell
python -m aelrith_forge
```

Or use the Windows launcher:

```powershell
.\Launch_Aelrith_Forge.bat
```

## First-Time Configuration

1. Open Kon.
2. Choose the roll domain: Specs or Powers.
3. Configure the target rules you want to keep.
4. Set the OCR regions for the current roll, preview/current spec area, popup area, and shard counters.
5. Set click points for Auto, reroll/manual confirmation, and popup confirmation.
6. Run a short manual test and watch the logs before leaving the macro unattended.

Kon. stores settings locally and does not ship with a Discord webhook configured.

## Discord Webhook Privacy

Discord webhook reporting is optional. Each user must enter their own webhook URL in Settings.

Do not share a webhook URL publicly. Kon. can report roll stats, shard counts, screenshots, macro stops, and recovery alerts to the configured webhook.

The repository defaults keep webhook settings blank:

- `webhook_url`: blank
- `player_ping`: blank

Local settings are ignored by Git so personal webhook URLs, regions, click points, and debug output are not committed.

## Local Files

Kon. writes local settings, logs, screenshots, OCR traces, and diagnostics beside the app process:

- `config/aelrith_forge_settings.json`
- `output/json/aelrith_forge_history.json`
- `output/json/aelrith_forge_near_misses.json`
- `output/logs/aelrith_forge_logs.json`
- `output/captures/`
- `output/diagnostics/`
- `output/ocr/`

These folders are intentionally ignored because they can contain personal settings, webhook URLs, screenshots, OCR dumps, and runtime diagnostics.

## Testing

Run the safety harness:

```powershell
python -m pytest -q
python -m compileall aelrith_forge tests
python -c "import aelrith_forge; import aelrith_forge.backend.bot; print('ok')"
```

The tests focus on parser, OCR normalization, shard parsing, Powers evaluation, startup/recovery guards, and webhook formatting without requiring a live desktop automation session.

## Backend Connection Points

- `aelrith_forge/backend/bot.py` contains OCR, roll checking, near-miss detection, screenshot capture, webhook logic, startup/recovery, and watchdog behavior.
- `aelrith_forge/backend/controller.py` is the Qt-safe adapter used by the UI.
- `aelrith_forge/ui/main_window.py` owns navigation, status updates, preview dialogs, region picking, export, and shutdown behavior.
- `aelrith_forge/ui/pages/main_page.py` owns the run configuration, target cards, stat rows, and live result tables.
