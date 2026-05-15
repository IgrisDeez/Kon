from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover - exercised when requests is missing in packaged envs
    requests = None

from ..version import APP_BASE_NAME, APP_RELEASE_ASSET_PATTERN, APP_UPDATE_REPO, APP_VERSION

GITHUB_API_BASE = "https://api.github.com"
PRESERVED_UPDATE_DIRS = (
    "config",
    "output",
    "logs",
    "screenshots",
    "debug",
    "godroll_captures",
    "json",
    "ocr_debug_crops",
    "diagnostic_snapshots",
)


@dataclass(frozen=True)
class UpdateCheckResult:
    status: str
    current_version: str
    latest_version: str = ""
    release_url: str = ""
    asset_url: str = ""
    asset_name: str = ""
    asset_size: int = 0
    notes: str = ""
    message: str = ""

    @property
    def update_available(self) -> bool:
        return self.status == "available"


def parse_version(version: str) -> tuple[int, ...] | None:
    raw = str(version or "").strip()
    if raw.lower().startswith("v"):
        raw = raw[1:]
    if not raw or re.search(r"[^0-9.]", raw):
        return None
    parts = raw.split(".")
    if not parts or any(part == "" for part in parts):
        return None
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return None


def is_newer_version(candidate: str, current: str) -> bool:
    candidate_parts = parse_version(candidate)
    current_parts = parse_version(current)
    if candidate_parts is None or current_parts is None:
        return False
    width = max(len(candidate_parts), len(current_parts))
    candidate_padded = candidate_parts + (0,) * (width - len(candidate_parts))
    current_padded = current_parts + (0,) * (width - len(current_parts))
    return candidate_padded > current_padded


def select_release_asset(assets: list[dict], pattern: str = APP_RELEASE_ASSET_PATTERN) -> dict | None:
    for asset in assets or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name and url and fnmatch.fnmatch(name, pattern):
            return asset
    return None


def check_for_update(
    current_version: str = APP_VERSION,
    repo: str = APP_UPDATE_REPO,
    asset_pattern: str = APP_RELEASE_ASSET_PATTERN,
    timeout: float = 8.0,
    session=None,
) -> UpdateCheckResult:
    current_parts = parse_version(current_version)
    if current_parts is None:
        return UpdateCheckResult("failed", current_version, message="Current app version is not valid.")

    client = session or requests
    if client is None:
        return UpdateCheckResult("failed", current_version, message="The requests package is not available.")

    url = f"{GITHUB_API_BASE}/repos/{repo}/releases/latest"
    try:
        response = client.get(url, timeout=timeout, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        release = response.json()
    except Exception as exc:
        return UpdateCheckResult("failed", current_version, message=f"Update check failed: {exc}")

    if not isinstance(release, dict):
        return UpdateCheckResult("failed", current_version, message="GitHub returned an invalid release response.")
    if release.get("draft") or release.get("prerelease"):
        return UpdateCheckResult("current", current_version, message="Latest release is not a stable public release.")

    latest_version = str(release.get("tag_name") or release.get("name") or "").strip()
    if parse_version(latest_version) is None:
        return UpdateCheckResult("failed", current_version, message="Latest release version is not valid.")
    if not is_newer_version(latest_version, current_version):
        return UpdateCheckResult("current", current_version, latest_version=latest_version, message="Kon. is up to date.")

    asset = select_release_asset(list(release.get("assets") or []), asset_pattern)
    if asset is None:
        return UpdateCheckResult(
            "failed",
            current_version,
            latest_version=latest_version,
            release_url=str(release.get("html_url") or ""),
            message=f"No portable release ZIP matched {asset_pattern}.",
        )

    return UpdateCheckResult(
        "available",
        current_version=current_version,
        latest_version=latest_version,
        release_url=str(release.get("html_url") or ""),
        asset_url=str(asset.get("browser_download_url") or ""),
        asset_name=str(asset.get("name") or ""),
        asset_size=int(asset.get("size") or 0),
        notes=str(release.get("body") or "").strip()[:1600],
        message="Update available.",
    )


def download_release_asset(result: UpdateCheckResult, target_dir: Path | None = None, timeout: float = 30.0, session=None) -> Path:
    if not result.update_available or not result.asset_url:
        raise ValueError("No update asset is available to download.")
    client = session or requests
    if client is None:
        raise RuntimeError("The requests package is not available.")

    root = Path(target_dir or tempfile.mkdtemp(prefix="kon_update_"))
    root.mkdir(parents=True, exist_ok=True)
    filename = result.asset_name or f"{APP_BASE_NAME}-{result.latest_version}-portable.zip"
    path = root / filename
    partial = path.with_suffix(path.suffix + ".part")
    response = client.get(result.asset_url, stream=True, timeout=timeout)
    try:
        response.raise_for_status()
        with partial.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    fh.write(chunk)
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    partial.replace(path)
    return path


def app_install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def is_portable_runtime() -> bool:
    if getattr(sys, "frozen", False):
        return True
    return (app_install_dir() / f"{APP_BASE_NAME}.exe").exists()


def find_updater_script(app_dir: Path | None = None) -> Path | None:
    root = Path(app_dir or app_install_dir())
    candidates = (
        root / "update_kon.ps1",
        root / "scripts" / "update_kon.ps1",
    )
    for path in candidates:
        if path.exists():
            return path
    return None


def launch_updater(zip_path: Path, app_dir: Path | None = None, exe_name: str | None = None) -> None:
    root = Path(app_dir or app_install_dir()).resolve()
    script = find_updater_script(root)
    if script is None:
        raise FileNotFoundError("update_kon.ps1 was not found beside the app.")
    exe = exe_name or (Path(sys.executable).name if getattr(sys, "frozen", False) else f"{APP_BASE_NAME}.exe")
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-ZipPath",
        str(Path(zip_path).resolve()),
        "-AppDir",
        str(root),
        "-ExeName",
        exe,
        "-ParentPid",
        str(os.getpid()),
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(command, cwd=str(root), creationflags=flags)


def update_cache_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path(tempfile.gettempdir()) / f"kon_update_{stamp}"
