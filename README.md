Copyright © 2026 Igers. All rights reserved. Kon. is proprietary software. Unauthorized copying, modification, redistribution, reverse engineering, or derivative use is prohibited without written permission from Igers.

# Kon.

A native PySide6 desktop rebuild of the original automation script, now branded as Kon.

## Run

```powershell
python -m pip install -r requirements.txt
python -m aelrith_forge
```

EasyOCR is optional. Install it separately with `python -m pip install easyocr` if you want the same EasyOCR-assisted stat reads from the original script.

## Passive Shard Reports

Open Settings, set the Passive shard region, and keep Webhook URL configured. The app reports the shard count every 20 minutes by default and sends an attention message if shards read as 0 or rolling recovery fails.

## Backend Connection Points

- `aelrith_forge/backend/bot.py` preserves the OCR, roll checking, near-miss detection, screenshot capture, and webhook logic.
- `aelrith_forge/backend/controller.py` is the Qt-safe adapter. The UI talks to this file through signals and slots.
- `aelrith_forge/ui/main_window.py` owns page navigation, status strip updates, preview dialogs, region picking, export, and shutdown behavior.
- `aelrith_forge/ui/pages/main_page.py` owns the Run Configuration card, target spec cards, capped stat rows, and live result tables.

Settings and history are saved beside the app process using the original JSON names:

- `config/aelrith_forge_settings.json`
- `output/json/aelrith_forge_history.json`
- `output/json/aelrith_forge_near_misses.json`
- `output/logs/aelrith_forge_logs.json`
- `output/captures/`
- `output/diagnostics/`
- `output/ocr/`
