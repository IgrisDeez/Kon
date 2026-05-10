# AGENTS.md

Project instructions for future Codex work in this repository.

This repository contains the Kon. desktop automation/macro project. Optimize all work for reliability, observability, and safe incremental change.

## Project Priorities

1. Engine stability
2. Startup reliability
3. OCR quality
4. Recovery correctness
5. Dev tooling
6. UI polish

## Core Rules

- Preserve existing behavior unless the user explicitly requests a change.
- Prefer small, scoped patches over broad rewrites.
- Do not mix unrelated systems in one patch.
- Do not redesign working engine, recovery, OCR, parser, watchdog, popup, autoroll, or webhook logic without a confirmed root cause.
- Do not remove safety checks, cooldowns, confirmations, recovery gates, rollback paths, or debug visibility unless explicitly requested.
- Preserve rollback safety wherever possible.
- Keep startup, recovery, autoroll, and watchdog behavior deterministic and observable.

## Context And Command Discipline

- Keep command output small and focused.
- Byte-cap potentially large output, for example:
  - PowerShell: `COMMAND 2>&1 | Out-String -Width 200 | Select-Object -First 1`
  - Prefer targeted reads over full-file dumps.
- Use `rg` / `rg --files` for searches.
- Inspect only relevant files and nearby code.
- Avoid loading generated logs, artifacts, screenshots, or large debug files unless needed.
- Do not create extra docs, folders, reports, or artifacts unless requested.

## Logs-First Debugging

- Inspect relevant logs before proposing fixes.
- Diagnose from current behavior, logs, config, and call flow before editing code.
- Prefer actionable logs over noisy logs.
- Keep logs useful for recovery decisions, parser confidence, OCR results, webhook failures, popup handling, and autoroll verification.
- Do not spam high-frequency loops with repeated logs unless gated, sampled, or state-change based.

## Startup And Recovery Safety

- Treat startup, watchdog, recovery, rollback, and autoroll verification as critical systems.
- Preserve deterministic startup order and recovery checkpoints.
- Do not weaken recovery validation or skip verification to make a flow appear successful.
- Keep failure states observable and recoverable.
- Avoid changing startup and recovery logic in the same patch as unrelated UI or parser work.

## OCR And Parser Safety

- Prefer coherent OCR parses over raw-confidence noisy parses.
- Preserve parser confidence rules unless explicitly asked to tune them.
- Treat OCR parsing, region detection, popup interpretation, and autoroll verification as safety-sensitive.
- Do not broaden accepted OCR outputs without validation against failure cases.
- Keep parser changes narrow and testable with representative log/debug samples.

## UI Safety

- Keep public UI simple and stable.
- Keep dev/debug controls separate from normal user-facing UI.
- Do not redesign the UI unless explicitly requested.
- UI polish must not change backend behavior, engine timing, recovery behavior, or automation safety.
- Read version/display metadata from the project version source rather than hardcoding labels.

## Compatibility

- Preserve existing config formats, saved state, debug artifacts, webhook payload expectations, and user workflows unless explicitly asked to migrate them.
- Prefer backward-compatible additions over breaking changes.
- If a migration is unavoidable, make it explicit, deterministic, and reversible where practical.

## Validation

- Validate the smallest relevant surface area for the change.
- For debugging or stability fixes, confirm the diagnosis from logs or code flow before patching.
- After changes, run only relevant checks unless the user asks for broader validation.
- Confirm no unrelated behavior changed.
- Do not run tests/builds when the user explicitly says not to.

## Default Maintenance Workflow

Unless the user explicitly says otherwise, every debugging, stability, workflow, polish, or feature update should include:

- Apply the requested fix or change.
- Bump the app version with semantic versioning:
  - `PATCH` for bug fixes, debugging, parser/OCR stability, and polish.
  - `MINOR` for user-facing features or workflow improvements.
  - `MAJOR` for major redesigns or breaking changes.
- Run the version bump script after code changes:
  - `python tools/bump_version.py`
  - `python tools/bump_version.py minor`
  - `python tools/bump_version.py major`
- Update `CHANGELOG.md` with a short summary for the new version.
- Ensure UI titles and startup logs read the current version from `aelrith_forge/version.py`.
- Add the current version to debug/log artifact names where reasonable.
- Search for and remove leftover hardcoded old version strings.
- Run a quick post-change audit.

## Version Source

- The app version lives in `aelrith_forge/version.py`.
- Do not hardcode app version strings in UI, backend logs, or packaging files.
- Use `APP_VERSION`, `APP_DISPLAY_NAME`, or `APP_BASE_NAME` from `aelrith_forge.version` / `aelrith_forge`.

## Post-Change Audit

- Confirm the app still reads version metadata from `aelrith_forge/version.py`.
- Confirm build/package naming uses `APP_BASE_NAME` only.
- Confirm display, UI title, and log naming use `APP_DISPLAY_NAME`.
- Confirm no unnecessary build artifacts were created.
- Confirm no unrelated logic was changed.
