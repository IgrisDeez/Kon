from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "aelrith_forge" / "version.py"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"
VERSION_PATTERN = re.compile(r'^(APP_VERSION\s*=\s*)"v(\d+)\.(\d+)(?:\.(\d+))?"', re.MULTILINE)


def read_version_text() -> str:
    return VERSION_FILE.read_text(encoding="utf-8")


def bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def append_changelog_section(version: str) -> bool:
    heading = f"## {version}"
    if CHANGELOG_FILE.exists():
        changelog = CHANGELOG_FILE.read_text(encoding="utf-8")
    else:
        changelog = "# Changelog\n"

    if re.search(rf"^##\s+{re.escape(version)}(?:\s|$)", changelog, re.MULTILINE):
        return False

    section = f"{heading}\n\n- \n\n"
    lines = changelog.splitlines(keepends=True)
    if lines and lines[0].lstrip().startswith("# Changelog"):
        insert_at = 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
        prefix = "".join(lines[:insert_at]).rstrip() + "\n\n"
        suffix = "".join(lines[insert_at:]).lstrip()
        updated = prefix + section + suffix
    else:
        updated = "# Changelog\n\n" + section + changelog.lstrip()

    CHANGELOG_FILE.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump Kon. APP_VERSION.")
    parser.add_argument(
        "part",
        nargs="?",
        default="patch",
        choices=("major", "minor", "patch"),
        help="Version part to bump. Defaults to patch.",
    )
    args = parser.parse_args()

    text = read_version_text()
    match = VERSION_PATTERN.search(text)
    if not match:
        raise SystemExit(f"Could not find APP_VERSION in {VERSION_FILE}")

    current = (int(match.group(2)), int(match.group(3)), int(match.group(4) or 0))
    next_version = bump(current, args.part)
    if args.part == "patch":
        next_value = f"v{next_version[0]}.{next_version[1]}.{next_version[2]}"
    else:
        next_value = f"v{next_version[0]}.{next_version[1]}"
    updated = VERSION_PATTERN.sub(rf'\1"{next_value}"', text, count=1)
    VERSION_FILE.write_text(updated, encoding="utf-8")
    changelog_updated = append_changelog_section(next_value)

    print(f"Bumped APP_VERSION to {next_value}")
    if changelog_updated:
        print(f"Added CHANGELOG.md section for {next_value}")
    else:
        print(f"CHANGELOG.md already has a section for {next_value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
