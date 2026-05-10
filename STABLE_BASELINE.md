# Kon. Stable Baseline

## Baseline Name

v1.93 Stable Engine Rollback

## Preserved Rollback Build

`APP_VERSION = "v1.93"`

Snapshot date: 2026-04-20
Source snapshot: `Kon. Project v1.93 Stable.zip`

## Current Working Version

`APP_VERSION = "v1.100.6"`

## Rollback Purpose

This checkpoint preserves the first Kon. build where the startup autoroll path, bad-mythical manual reroll auto-resume path, and unexpected no-roll watchdog auto re-enable path are all working together as the current most stable engine.

Future speed, OCR, parser, recovery, watchdog, or UI changes should be compared against this rollback first so regressions can be isolated quickly.

## Known Strong Areas

- Startup autoroll can reopen the guarded Auto click path instead of falsely trusting weak OCR-only refresh signals.
- Bad mythical manual reroll flow can clear the popup and restore Auto with bounded verification instead of stalling with Auto off.
- Unexpected no-roll watchdog can re-enable Auto when rolling silently stops instead of suppressing recovery on weak OCR-only trait/current-spec refresh.
- Popup handling still verifies the popup clears before continuing.
- Structured runtime logs, decision-chain data, near-miss history, and OCR/debug artifacts are available for diagnosis.
- Current backend regression tests cover the guarded startup click, manual auto-resume safety, and watchdog auto re-enable behavior.

## Known Remaining Weak Spots

- Checkbox OCR can still return ambiguous reads and may require bounded recovery clicks.
- OCR parsing can still hit edge cases on noisy Rampage/Executioner reads.
- Transition and watchdog speed have been tightened after this snapshot, so future performance tweaks should still be compared back to this rollback.
- Full overnight runtime proof is still stronger than lab-only verification; long sessions should continue to be observed after each engine patch.

## Next Planned Work

- Measure future transition/watchdog speed changes against this rollback and keep them bounded.
- Continue live testing OCR stability and long-session watchdog behavior.
- Keep future parser, recovery, popup, webhook, and UI changes small and separately verifiable.

## Safe Snapshot Workflow

- Preserve this source tree before risky changes by creating a local zip or copy of the project directory.
- Keep `aelrith_forge/version.py`, `CHANGELOG.md`, `STABLE_BASELINE.md`, tests, and current config defaults with the snapshot.
- Run the test suite before and after risky changes, then compare behavior against this rollback.
- If a future pass regresses rolling, recovery, watchdog behavior, OCR, or diagnostics, roll back to this v1.93 snapshot and reapply only the proven parts.
