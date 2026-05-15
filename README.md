Copyright (c) 2026 Igers. All rights reserved. Kon. is proprietary software. Unauthorized copying, modification, redistribution, reverse engineering, or derivative use is prohibited without written permission from Igers.

# Kon.

Kon. is a Windows desktop automation and OCR assistant for rolling and monitoring Specs and Powers. It reads the game screen, checks rolls against your saved targets, keeps God Rolls, reports useful results to Discord, and writes local logs so startup, recovery, and OCR decisions are visible.

The Python package is still named `aelrith_forge` for compatibility with existing settings, logs, scripts, and imports.

## Download

For normal users, use the GitHub page:

1. Open the repository on GitHub.
2. Click `Code`.
3. Click `Download ZIP`.
4. Extract the ZIP somewhere permanent, such as `Documents\Kon`.
5. Open the extracted folder before running the launcher.

If a packaged release is available, download the release ZIP or EXE instead. Releases are easier for non-developers because they do not need the source setup steps below.

## Requirements

- Windows 10 or 11.
- Python 3.11 or newer if you are running from source.
- Tesseract OCR installed at `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- The game/client visible on screen while the macro is running.

EasyOCR is optional. Install it only if you want EasyOCR-assisted reads:

```powershell
python -m pip install easyocr
```

## Source Setup

Use these steps if you downloaded the repository source instead of a packaged release.

1. Install Python 3.11 or newer from python.org.
2. Install Tesseract OCR for Windows.
3. Open PowerShell in the Kon. folder.
4. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

5. Install the app packages:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For development or tests, also install:

```powershell
python -m pip install -r requirements-dev.txt
```

## Run

The easiest way to start Kon. is the Windows launcher:

```powershell
.\Launch_Aelrith_Forge.bat
```

The launcher checks whether the required Python packages are installed and offers to install them if they are missing.

You can also launch directly from PowerShell:

```powershell
python -m aelrith_forge
```

## First-Time Setup In The App

1. Open Kon.
2. Choose whether you are rolling `Specs` or `Powers`.
3. Add the targets you want to keep.
4. Set the OCR regions for the current roll, preview/current roll area, popup area, and shard counters.
5. Set click points for Auto, reroll/manual confirmation, and popup confirmation.
6. Use the test buttons to confirm OCR, popup detection, and click positions.
7. Start with a short manual run while watching the logs.

Kon. is designed to stop or observe when it cannot safely confirm what is on screen. If OCR reads are weak, regions are wrong, or the Auto checkbox cannot be trusted, fix the setup before leaving it unattended.

## Discord Webhook Setup

Discord reporting is optional. Each user should create and enter their own webhook in Kon. settings.

1. In Discord, open the server channel that should receive roll alerts.
2. Go to `Edit Channel` > `Integrations` > `Webhooks`.
3. Create or copy a webhook URL.
4. In Kon., open `Settings`.
5. Paste the webhook URL into the Discord webhook field.
6. Add an optional player ping if you want God Roll alerts to mention someone.
7. Use `Test Webhook` to confirm Discord can receive messages.

Webhook settings are local-only. Kon. stores webhook URL, ping, live status options, screenshot options, and related Discord preferences in:

```text
config/aelrith_forge_webhook.local.json
```

That local file is ignored by Git so webhook secrets do not get committed or shared. Debug exports and settings backups should only expose whether a webhook is configured, not the actual URL or ping.

## What Discord Alerts Mean

Kon. sends readable Markdown messages for both Specs and Powers:

- `Kon. Kept Spec Roll` or `Kon. Kept Power Roll` means the roll matched your keep rules.
- `Kon. Near Miss - Spec` or `Kon. Near Miss - Power` means the roll was close, but at least one target stat missed.
- `What happened` gives the short result.
- `Roll` shows the trait or power and rolled stat lines.
- `Target check` explains why it was kept or what missed.
- `Session` includes uptime, timestamp, and shard summary when available.
- `OCR` includes a compact raw OCR excerpt for troubleshooting.

Kept/God Roll alerts keep screenshot attachment behavior. Near-miss alerts stay deduped and do not ping unless the configured Discord behavior allows it.

## Local Files

Kon. writes settings, logs, screenshots, OCR traces, and diagnostics beside the app process:

- `config/aelrith_forge_settings.json`
- `config/aelrith_forge_webhook.local.json`
- `output/json/aelrith_forge_history.json`
- `output/json/aelrith_forge_near_misses.json`
- `output/logs/aelrith_forge_logs.json`
- `output/captures/`
- `output/diagnostics/`
- `output/ocr/`

These files and folders are intentionally ignored because they can contain personal settings, screenshots, OCR dumps, runtime diagnostics, and local Discord preferences.

## Troubleshooting

- If Kon. cannot read rolls, confirm Tesseract is installed and the OCR regions cover the correct on-screen text.
- If Discord does not receive messages, recheck the local webhook URL and run `Test Webhook`.
- If startup stops instead of rolling, check the logs. Kon. may be refusing to click Auto because the current screen is unreadable or not a confirmed BAD listed mythical roll.
- If clicks land in the wrong place, recalibrate the Auto, reroll/manual confirmation, and popup confirmation click points.
- If the game window moved or display scaling changed, recheck all OCR regions and click points.

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
