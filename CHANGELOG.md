# Changelog

## v1.100.19

- Sent near-miss Discord alerts through an explicit raw Markdown path and logged the v2 clean format before delivery.
- Stopped watchdog recovery from confirming rolling from repeated garbage/control OCR after an Auto re-enable attempt.
- Added off-target current-roll OCR diagnostics when the stats region reads UI text such as `orCode`, `OCRPass`, or `StartPowers`.

## v1.100.18

- Reformatted Discord near-miss alerts into a cleaner Markdown summary for Specs and Powers rolls.
- Added aligned stat-result, missed-stat, gap, uptime, and timestamp sections while preserving near-miss detection and dedup behavior.
- Added backend regressions for Rampage and Power near-miss alert bodies.

## v1.100.17

- Added a Powers startup observe-first guard so autoskip/non-target Power rolls do not risk toggling Auto from disabled/unknown checkbox reads.
- Logged `startup_powers_observe_without_toggle` decisions with checkbox confidence, OCR reason, change score, and autoskip support signals.
- Updated Powers startup regressions for disabled/unknown autoskip reads while preserving bounded Auto enable when no roll evidence exists.

## v1.100.16

- Skipped Specs startup Auto toggles when non-target/filler OCR already shows current-spec refresh activity.
- Added `startup_specs_observe_without_toggle` logging with checkbox confidence, OCR reason, startup class, and change score.
- Added regressions for disabled/unknown checkbox reads with roll-like OCR and for the no-refresh bounded enable path.

## v1.100.15

- Blocked generic Specs startup manual reroll fallback unless a BAD/DISABLED mythical or popup was confirmed.
- Logged blocked non-BAD Specs startup fallbacks with state, trait, startup class, Auto state, and popup confirmation status.
- Updated startup regressions so filler/non-target Specs startup fails safe instead of clicking manual reroll.

## v1.100.14

- Added a fast Powers loop OCR route that tries one psm6 candidate before escalating to broader primary/fallback OCR.
- Reused coherent stable BAD Power parses for fast loop confirmation and added sampled loop timing telemetry.
- Backed off passive shard OCR in Powers mode when the configured region is reading roll text, while keeping Power shard checks active.
- Added regressions for fast BAD confirmation, popup-cleared resume verification flags, and passive shard backoff.

## v1.100.13

- Treated unsupported, filler, and disabled Powers as autoskip/non-target rolls so only enabled listed Mythicals can trigger BAD manual reroll.
- Skipped slow startup trust/preflight OCR for Powers autoskip rolls and used compact Auto handling instead.
- Added regressions for disabled Power autoskip, enabled/disabled/unknown Auto autoskip startup, and BAD Mythical preservation.

## v1.100.12

- Confirmed manual reroll resume after a cleared popup when readable roll-like OCR appears below the general image-change threshold.
- Used the fast no-fallback OCR path to confirm strong startup BAD Power detections instead of repeating slow fallback candidate scans.
- Added regressions for below-threshold popup-cleared resume OCR and fast startup BAD Power confirmation.

## v1.100.11

- Restored unsupported/non-target Power handling so non-mythic or unsupported rolls remain Auto-roll filler instead of manual reroll targets.
- Routed supported BAD Powers found in startup verification samples into the existing stable BAD confirmation and manual reroll flow.
- Added regressions for unsupported Power filler behavior and sampled supported BAD Power startup reroll routing.

## v1.100.10

- Routed clear unsupported or non-target Powers such as Battleborn/Berserker into manual reroll instead of treating them as Auto-roll filler.
- Kept weak unreadable Power fallback OCR in rolling/uncertain state so noisy text alone still does not trigger confirmation clicks.
- Added regressions for unsupported Power classification and startup manual reroll routing.

## v1.100.9

- Confirmed manual reroll resume after a cleared popup when Auto resume produces image change plus readable roll-like OCR, without accepting stale text alone.
- Disabled slow multi-source OCR fallback in manual reroll resume verification to reduce startup reroll delay.
- Hardened the Windows batch launcher so it prefers a local venv or `py -3`, checks dependencies, and offers to install missing requirements before launch.
- Added diagnostics/tests for Powers BAD reroll context, popup-cleared resume confirmation, stale resume rejection, and fast verify settings.

## v1.100.8

- Saved a sanitized local Powers settings backup without webhook or player-identifying fields.
- Required coherent, stable Powers BAD confirmation before entering manual reroll so weak or changing OCR does not click confirmation.
- Added Powers BAD confirmation, settings backup, and parser stability regressions.

## v1.100.7

- Hardened startup and watchdog recovery so weak stale OCR and ambiguous Auto checkbox reads no longer fake-confirm rolling or trigger blind clicks.
- Rejected glued stat fragments such as `CritDamageI` and `CritChanceII` as generic non-target traits while preserving real filler traits.
- Added parser/watchdog regressions plus a headless pytest fallback for backend-only controller imports.

## v1.100.6

- Fixed a watchdog crash when an ambiguous Auto checkbox recheck became weak-enabled before the recovery click.
- Rejected broad sky/background checkbox crops as unknown so off-panel world screenshots no longer look like enabled Auto accents.
- Added an off-panel watchdog guard that skips recovery clicks and records `roll_panel_not_visible_or_unreadable` when reroll UI evidence is missing.

## v1.100.5

- Classified the grey unchecked Auto checkbox frame as disabled so Specs safe-filler startup can use the existing bounded Auto enable path.
- Kept ambiguous/blank checkbox crops unknown and preserved enabled-accent detection, manual-reroll policy, parser/scoring, shard logic, and Power routing.
- Added regressions for grayscale unchecked crops, enabled accents, blank crops, and Specs safe-filler disabled-Auto startup recovery.

## v1.100.4

- Fixed Tools-page action alignment by moving preview, validation, capture, webhook, and diagnostics controls into scrollable action groups.
- Retouched the dashboard theme into a darker monochrome palette with grayscale status contrast instead of colored slate/gold accents.
- Added UI regressions for Tools action-group spacing, scrollability, signal preservation, and monochrome theme colors.

## v1.100.3

- Reused a single stats-region capture inside each rolling verification poll for OCR, image-change checks, and candidate parsing.
- Added startup/recovery verification budget logs plus cache/route snapshots to diagnostics and Live Proof Packs.
- Added compact Macro Health and Tools diagnostics readouts, with clearer hidden-window OCR preview status transitions.

## v1.100.2

- Blocked Specs safe-filler startup from blind Auto toggles or manual reroll fallback when the current roll is not BAD/DISABLED.
- Let weak current-spec refresh evidence on Specs safe fillers continue into the main loop without a startup click, leaving later stalls to the watchdog.
- Added regressions for Specs safe-filler no-click/no-manual routing while keeping Power safe-filler and real bad-mythical reroll behavior unchanged.

## v1.100.1

- Preserved terminal stop reasons so high-value, kept-roll, macro-stop, and empty-shard stops survive final session summaries and Live Proof Packs.
- Added compact Auto checkbox ambiguity counters and latest classifier details to diagnostics and proof exports without changing recovery click behavior.
- Clarified partial-target confirmation drift logs and cleaned Live Proof Pack Markdown encoding for ellipsis text.

## v1.100

- Retouched the operator dashboard with clearer Specs/Powers mode badges, semantic status tones, and tighter card spacing.
- Reorganized Tools actions into Capture, Preview OCR, Validation, and Webhook groups while preserving existing signals and hidden-window preview behavior.
- Added a visible OCR preview notice and UI regressions for page wiring, version metadata, mode state, and Tools signals.

## v1.99.4

- Allowed Specs startup safe-filler recovery to fall through to manual reroll when Auto resume remains unresolved after bounded verification.
- Kept Power safe-filler startup recovery conservative so unresolved Auto state still blocks manual reroll instead of consuming Power shards.
- Added backend regressions for the Specs/Powers safe-filler startup split.

## v1.99.3

- Restored cautious manual-reroll popup confirmation so missed popup OCR presses fallback Yes before any Auto resume attempt.
- Hardened manual-reroll popup probing with psm6 confirmation and modal-text diagnostics when stats OCR sees the reroll prompt after popup OCR misses it.
- Added lightweight timing breadcrumbs for popup confirmation, Auto resume, recovery verification, deferred startup tasks, and OCR previews in debug/proof artifacts.

## v1.99.2

- Temporarily hides the main window during Specs, Powers, Passive shard, and Power shard OCR preview captures so the UI does not cover the target region.
- Restores the previous normal, maximized, or fullscreen window state before showing preview results or errors.
- Added source regression coverage for the hidden-window OCR preview wrapper.

## v1.99.1

- Skipped the cautious fallback Yes click when manual reroll popup polling repeatedly proves no popup is present.
- Shortened manual-reroll Auto resume when the checkbox is unreadable by going straight to one bounded re-enable click and rolling verification.
- Updated backend and replay regressions for the faster no-popup transition while preserving guarded recovery safety paths.

## v1.99

- Added Live Proof Pack exports with readable Markdown and structured JSON reports for long-session validation.
- Added a Tools action for manual proof exports and automatic session-stop proof generation without changing OCR, rolling, recovery, or watchdog behavior.
- Included target summaries, recent operator events, recent logs, decision-chain data, session counters, history rows, and Passive/Power shard summaries in proof bundles.

## v1.98.10

- Added Power shard state to decision-chain and diagnostic snapshot data so debug bundles now preserve both shard subsystems side by side.
- Included configured Power shard regions, thresholds, empty-stop settings, screenshots, and OCR attempts in diagnostic summaries and artifacts.
- Split Tools shard previews into explicit Passive and Power shard OCR actions with regression coverage for the new wiring.

## v1.98.9

- Added the missing Power shard threshold and alert cooldown controls to the Settings page so the full existing Power shard settings block can be edited, saved, and restored on startup.
- Completed the Power shard Settings UI collect/load/lock loop so region, alerts, interval, thresholds, cooldown, and stop-on-empty all round-trip through the normal config path.
- Added regression coverage for Settings-page Power shard round-trips and controller startup hydration from saved Power shard settings.

## v1.98.8

- Added shared compact verification profiles for startup, manual-reroll resume, bounded auto re-enable, and watchdog paths so routed recovery branches stop re-deriving heavyweight verify settings.
- Tightened `stats_changed(...)` fast-path behavior with fast post-popup checks and compact single-sample exits for already-bounded branches, reducing redundant OCR/popup work without lowering safety thresholds.
- Skipped duplicate startup double-check passes after decisive non-confirming compact startup and guarded-recovery results, keeping the final routing logic intact while shrinking startup latency.

## v1.98.7

- Added a disconnect/maintenance OCR sentinel so the unexpected no-roll watchdog skips recovery instead of toggling Auto on blocked client screens.
- Hardened recovery classification and route snapshots so disconnect/maintenance screens record a truthful blocked outcome in replay/backend tests.
- Made passive shard reporting reuse the last trusted value on transient OCR misses and throttle repeated skip spam.

## v1.98.6

- added committed startup/recovery replay fixtures for recent Powers startup, manual reroll, and watchdog scenarios so real mixed OCR/checkbox/popup traces are covered in tests
- added stable startup and recovery route snapshots for backend assertions, keeping replay tests focused on machine-meaningful outcomes instead of brittle log phrasing
- locked the recent startup blind-toggle and bounded auto-resume regressions behind a dedicated replay-focused backend suite without changing UI, shard, or webhook behavior

## v1.98.5

- replaced the compact Powers startup blind-toggle shortcut with a compact checkbox decision path so trusted NON_TARGET filler no longer unticks Auto when it was already enabled
- routed unreadable compact startup checkbox states into bounded guarded recovery instead of jumping straight to `Guarded Startup Enable`
- stopped the compact disabled-click path from repeating the same startup Auto click when the final startup check still reads disabled

## v1.98.4

- made trusted startup NON_TARGET Power filler use a truly compact Initial Auto Start preflight and jump straight to the guarded startup enable path when that compact preflight still shows not-rolling
- removed the redundant extra manual-reroll Auto uncertain-validation step before bounded recovery, keeping the same guarded re-enable safety contract while shortening bad-Power transitions
- moved forced shard priming off the startup critical path and routed startup/recovery popup checks through the fast popup probe so startup reaches active rolling sooner

## v1.98.3

- restored the bounded manual-reroll Auto recovery path so ambiguous Powers auto-resume now escalates into one guarded re-enable attempt instead of stopping at `uncertain`
- trusted strong startup-fast supported Power probes to skip the redundant slower full current-roll validation when the fast parse already has actionable BAD/DISABLED/HIGH_VALUE/GOD evidence
- added a fast-first popup probe for startup delay and manual reroll popup checks, plus richer ambiguous Auto checkbox debug samples for future log diagnosis

## v1.98.2

- consolidated recovery verification into a shared internal outcome contract with stable fields for confirmation, classification, rejection reason, sample text, unreadable state, and signal metadata
- routed startup/manual-reroll/watchdog support checks through the same normalized recovery outcome instead of partially reinterpreting raw state and details in each path
- extended backend regression coverage for readable weak OCR, unreadable-with-change classification, and popup/banner-assisted recovery confirmation while preserving existing safety behavior

## v1.98.1

- normalized failed recovery verification so readable trait-only and same-roll OCR now land on stable `not_rolling` classifications instead of drifting between unreadable/static labels
- added explicit recovery rejection reasons such as `trait_only_sample`, `no_material_change`, and `unreadable_context` to runtime logs, decision-chain details, and debug artifacts
- tightened backend regression coverage around recovery classification while keeping startup/manual-reroll safety behavior unchanged

## v1.98.0

- sped up bounded startup and manual-reroll auto-resume verification by trimming the fast-path waits and skipping the duplicate post-reroll verify when manual reroll already produced fresh strong confirmation
- added a separate Power shard subsystem with its own OCR region, alerts, empty-stop logic, session tracking, controller signal, Settings controls, and Main/session display
- added Power-specific Discord and Debug preview messaging for kept Power rolls, including passive details when parsed, while keeping Specs webhook behavior unchanged

## v1.97.3

- fixed post-manual-reroll auto resume so an ambiguous checkbox read now performs one bounded validation recheck before giving up
- preserved the safety contract by only re-enabling Auto when that validation confirms the checkbox is actually disabled
- updated backend regression coverage for manual reroll auto-resume recheck behavior and the improved startup fallback path it unblocks

## v1.97.2

- made the shared manual reroll flow domain-aware so Powers bad-roll recovery logs and failure reasons no longer read like Specs-only mythical flow
- kept the live reroll path on the active Powers layout and added regression coverage proving reroll, confirm, and auto-resume clicks use the loaded Powers coordinates
- preserved unsupported/filler Powers as NON_TARGET auto-continue behavior while tightening backend coverage around Powers bad-reroll diagnostics

## v1.97.1

- fixed manual reroll auto-resume so ambiguous or unknown Auto state no longer reports a false recovery success
- normalized controller settings on every save so invalid or reset config files round-trip cleanly between disk and in-memory state
- updated backend regression coverage for startup fast-probe behavior, bounded recovery paths, temp config storage, and shared version metadata

## v1.97.0

- reworked the Powers tab so setup reads more like Specs, with a clearer profile/setup introduction and the same practical section order
- moved `Preview OCR` into Runtime Layout so the visible normal setup flow is Preview OCR region plus the three click points
- kept advanced Powers detection regions hidden behind the existing toggle while tightening the normal-vs-advanced setup layout and preserving all existing Powers save/load/apply wiring

## v1.96.11

- fixed the shared Confirm and Apply flow so Specs applies show Specs target summaries and Powers applies show Powers target summaries instead of always rendering the Specs-only view
- made the post-apply `Desired targets applied` log use the same mode-aware summary selection as the confirmation popup
- added regression coverage for page-driven apply summary mode selection while keeping settings merge/apply behavior and Specs/Powers separation unchanged

## v1.96.10

- added passive threshold rows to the Powers slider cards for Cursebrand, Colossus, and Subjugator
- extended Powers rule targets so passive thresholds save/load through existing `powers_rules` with backwards-compatible legacy rule backfill
- included configured passive thresholds in Powers evaluation while keeping HP optional, unsupported powers skipped, and Specs behavior unchanged

## v1.96.9

- promoted Powers passive metadata and parsed passive details to first-class data-model/parser fields instead of leaving them nested in helper-only structures
- preserved structured passive fields through Powers candidate classification so debug/result paths can read passive family, value, duration, notes, and parsed stats directly
- added regression coverage for compact mythical Power passive strings, movement-slow wording, HP optional behavior, unsupported fillers, and unchanged Specs classification

## v1.96.8

- added structured passive metadata for Cursebrand, Colossus, and Subjugator while keeping the authoritative mythical stat ranges and HP optional flags intact
- hardened Powers parsing for compact inline roll strings, including CritChance/CritDamage, Boss DMG/DMG, glued labels, punctuation, and spacing variants
- surfaced parsed passive family/value/duration in existing Powers summaries and debug decision data without changing Specs behavior, settings shape, or mode routing

## v1.96.7 - Start-button consistency and hover polish
- made Start Specs and Start Powers share the same neutral action styling in idle state
- added shared hover/pressed glow-style button feedback across utility, primary, danger, chip, start, and collapsible controls
- kept the active running mode subtly indicated without changing Specs/Powers wiring or settings layout

## v1.96.6 - UI polish and declutter pass
- tightened shared card, pill, table, and threshold-row spacing while preserving the existing Kon. theme
- reduced redundant helper text across Main, Specs, Powers, Settings, Debug, and Tools
- kept Specs/Powers setup, thresholds, click points, advanced Powers regions, and subsystem tests functionally separate

## v1.96.5 - UI hierarchy cleanup for global vs mode-specific setup
- moved Specs click points out of global Settings and into the Specs tab Runtime Layout
- simplified normal Powers setup to Preview OCR region + Powers click points
- moved advanced/internal Powers detection regions behind an Advanced section while preserving separate config values
- kept Specs and Powers runtime settings/config blocks separate under the hood

## v1.96.4 - Specs/Powers parallel-mode UI structure pass
- Rename the sidebar Targets tab to Specs and align user-facing page wording so Specs and Powers read like parallel first-class modes.
- Rebuild Main > Operator Control around explicit Start Specs / Start Powers actions, a single shared Stop action, and a clearer Active Mode indicator while keeping mode-specific startup/settings separation intact.
- Restructure the Specs tab to mirror Powers with Spec Profile, Active Specs, Desired Roll Thresholds, and a lower Runtime Layout section, while keeping Specs OCR/runtime settings fully separate from Powers.
- Split Tools into Shared / General, Specs subsystem tests, and Powers subsystem tests so OCR preview, popup detection, and roll-classification tests can be launched explicitly per mode without changing engine behavior.

## v1.96.3 - Powers tab init-order crash fix
- Fix the PowersPage construction crash where shared OCR/click widgets were referenced before they were created.
- Add a dedicated `_init_controls()` pass so shared line edits, action buttons, chip containers, and power-card containers exist before any section builder uses them.
- Preserve the existing Specs/Powers UI consistency work and keep the fix scoped to Powers tab construction order only.

## v1.96.2 - Specs/Powers UI consistency refinement
- Remove the duplicate Idle badge inside Main > Operator Control so the global header status pill stays primary and the left-side control area now emphasizes Active Mode instead.
- Restructure the Powers tab to match Specs more closely with a polished Power Profile, Active Powers summary, Desired Roll Thresholds section, and a lower Runtime Layout section for OCR regions/click points.
- Unify Powers action labels and utility button treatment with Specs, including Confirm and Apply, Preview OCR, Pick buttons, enabled-power chips, and shared collapsible card styling.
- Rename temporary foundation/dev wording in the Powers tab to product-facing labels while preserving separate Specs vs Powers settings/layout storage and runtime behavior.

## v1.96 - Powers foundation (mythical-only phase 1)
- Add a separate Powers foundation path without rewriting the protected Specs engine: separate settings, separate parser/evaluator, and a separate Powers UI tab while preserving the shared rolling/recovery loop.
- Add supported mythical power definitions for Cursebrand, Colossus, and Subjugator, including extensible stat metadata, aliases, passive text placeholders, and required-vs-optional stat flags.
- Add separate Powers layout settings (`powers_layout`) for OCR region, popup region, protected region, and Auto/Reroll/Confirm click points so Powers does not reuse Specs coordinates.
- Add `roll_domain` switching between `specs` and `powers`; when Powers is active the controller loads the active runtime layout from the isolated Powers settings while leaving Specs settings untouched.
- Add a dedicated Powers parser/evaluator foundation that treats unsupported powers as non-target filler and keeps HP optional so missing/low HP does not block valid keeps, god-roll checks, or near-miss checks in phase 1.

## v1.95 patch 2 - Watchdog dead-screen weak-enabled fast recovery
- Kept `APP_VERSION` at `v1.95` because this patch only targets watchdog auto-check/re-enable latency and still needs live runtime proof before a true engine version bump.
- Added a dead-screen watchdog fast path for `stage=suspicion` when suspicion already exited as a non-improving dead phase, popup/banner are already known clear, and the Auto checkbox leans `weak_enabled`.
- In that dead weak-enabled watchdog case, the bot now skips the redundant weak-enabled compact verify and final checkbox recheck, then proceeds directly to one controlled Auto re-enable click followed by resumed-rolling verification.
- Passed popup/banner clear context from stale-suspicion handoff into watchdog recovery so the suspicion-to-recovery transition does not repeat the same popup/banner guard checks.
- Preserved the existing compact weak-enabled verify path for noisy/uncertain watchdog cases where the UI is not clearly stalled.

## v1.95 patch 1 - Watchdog weak-enabled compact autoroll recheck
- Treat watchdog checkbox reads through an effective state layer so `weak_enabled` no longer falls straight into the heaviest ambiguous-confirm path.
- Add a compact watchdog weak-enabled verify before any forced Auto re-enable click, and only escalate to the click/verify chain if that compact check fails.
- Keep startup/manual-reroll logic unchanged while tightening watchdog suspicion-stage click/verify timings and preserving the full ambiguous guard only for truly ambiguous states.

## v1.95 - Faster manual reroll auto-resume with weak-enabled checkbox lean
- Add a manual-reroll-specific weak-enabled checkbox lean so repeated samples like base=enabled, wide=enabled, tight=unknown no longer collapse into the full slow uncertain path.
- Add a compact manual reroll resume verify path that tries one short rolling-behavior confirm after a positively detected and cleared popup before escalating into forced auto re-enable recovery.
- Tighten manual-reroll-only guard and verify timings, skip redundant popup pre/post checks once the popup was positively cleared, and preserve the heavier fallback chain only when the compact path does not confirm resumed rolling.

## v1.94 - Stable rollback update + faster transition/watchdog pass
- Update `STABLE_BASELINE.md` so the preserved rollback build is the verified v1.93 stable engine instead of the old v1.51 baseline.
- Speed up bad-mythical/manual-reroll transition timing with tighter post-click settle, popup polling, and auto-resume verify delays while preserving popup-clear safety and bounded verification.
- Speed up the unexpected no-roll watchdog by tightening the early suspicion threshold and using bounded fast verify profiles for both suspicion-stage and full recovery-stage auto re-enable checks instead of falling back to the slower default 7-poll verify.

## v1.93 - Watchdog auto re-enable recovery fix
- Fix the unexpected no-roll watchdog so ambiguous checkbox recovery no longer trusts weak OCR-only trait/current-spec refresh as proof that rolling resumed.
- When the watchdog sees a stale screen and the Auto checkbox is still unreadable after a weak guard, do one final checkbox re-read and send one bounded Auto re-enable click unless Auto is clearly enabled.
- Preserve popup/banner/image-change-backed watchdog confirms and add regression coverage for watchdog ambiguous-checkbox recovery.

## v1.92 - Startup auto guarded-click recovery fix
- Reject weak OCR-only startup rolling confirmations (such as trait/current-spec refresh without popup, banner, or image-change support) so unreadable Auto state can still reopen the guarded startup enable path.
- Preserve the safer non-startup auto-enable behavior from v1.90/v1.91 while restoring one bounded startup seed click when startup verification remains weak.
- Added regression coverage for startup trait-only false confirmations that previously suppressed the guarded startup Auto click.

## v1.91 - Manual reroll auto-resume fix + start minimize
- fixed the real manual-reroll auto-resume failure where ambiguous Auto checkbox reads could skip the re-enable click based on weak OCR-only trait-change evidence with no visual activity proof
- tightened the immediate manual-reroll auto-resume guard so only popup/banner/image-change backed activity can suppress the Auto re-enable click on ambiguous checkbox states
- when manual reroll auto-resume still has an ambiguous checkbox after weak guard evidence, perform one final checkbox recheck and then send one controlled Auto re-enable click instead of stalling with Auto off
- minimize the Kon. window immediately after Start is pressed so focus returns to the game screen more reliably

## v1.90 - Auto untick safety fix
- fixed a real recovery-path bug in `ensure_auto_enabled()` where non-startup ambiguous Auto reads could enter the cautious enable path and reference an undefined `diagnostic_auto` variable after sending a checkbox click
- changed non-startup ambiguous Auto handling to validate the checkbox one more time before any enable click, instead of sending a speculative toggle first
- only send an Auto enable click after that follow-up read confirms a visually disabled checkbox, which prevents accidental off-toggles during normal autoroll recovery

## v1.89 - Main page scroll + Current Roll layout repair
- made the Main page vertically scrollable so lower sections no longer get crushed at realistic window sizes
- increased Current Roll / Current Detection / Session metric block height and padding to stop clipping and cramped rows
- rebalanced Recent Events and history panel sizing without changing live update behavior

## v1.88
- Main page layout repair pass for Kon. / K. Console focused on fixing Recent Events overlap, restoring history-table visibility, and stabilizing live metric card sizing.
- Rebuilt the Main page Recent Events area into separate feed/history regions with safer stretch allocation, bounded feed height, and cleaner operator-feed rendering.
- Increased table-panel resilience and metric-block minimum sizing so Current Roll / Current Detection / Session content no longer clips as easily under real runtime data.

## v1.87
- UI/logging polish pass for Kon. / K. Console focused on operator events, structured runtime logs, and clearer debug inspection without changing bot logic.
- Main page: replaced the plain Recent Events scratchpad with a compact operator feed that shows timestamps, categories, clearer summaries, and a quick path into Debug.
- Logging: runtime log entries now store structured metadata such as category, subsystem, event type, event code, and operator-visibility flags while preserving legacy log-file compatibility.
- Debug: upgraded Runtime Log rendering and aligned the Discord preview with the current plain-text webhook format for easier future debugging.

## v1.86
- UI-only resilience pass for the Kon. / K. Console build, focused on live runtime content and premium composition under load.
- Main page: replaced fragile inline live-data rows with wrapped metric blocks for Current Roll, Current Detection, and Session so long runtime values stay readable.
- Operator Control and Recent Events: separated dense summaries into clearer panels, added structured history sub-panels, and improved near-miss composition without touching bot logic.
- Targets and Debug: refined threshold-row composition and split lower debug surfaces into a cleaner two-panel layout for better hierarchy.

## v1.85
- UI-only premium polish pass for the Kon. / K. Console build.
- Refined typography hierarchy in the header and status strip to better separate title, subtitle, labels, and values.
- Unified button sizing and utility-button styling for quieter, more consistent controls across Main, Targets, Settings, Debug, and Tools.
- Tightened spacing and card padding across the shell and page layouts to reduce empty space without changing structure.
- Improved form alignment in Targets and Settings, added a quieter summary treatment for active-target blocks, and masked the webhook URL until edit for safer presentation.
- Refined Debug and Tools page density with cleaner card emphasis and more intentional grouping.

## v1.84
- Targets UI: replaced the harsh default collapsible-header look with integrated graphite / gunmetal section headers for a cleaner dark-silver appearance.
- Main UI: realigned the Current Roll and Current Detection label/value rows into a more consistent two-column layout for cleaner scanning.
- Layout polish: tightened collapsible section spacing and preserved live bindings/behavior while reducing visual disconnect in the Targets and Main cards.

## v1.83
- UI polish: shifted the Kon. / K. Console theme from warm gold accents to a cooler graphite / gunmetal / dark silver palette for a cleaner, more premium look.
- UI polish: reduced visual heaviness with subtler borders, tidier spacing, lighter panel chrome, and more restrained selected/hover states.
- Sidebar: made the Kon. logo smaller and rebalanced its placement so the top-left branding feels cleaner without touching engine or startup behavior.

## v1.82
- Rebranded visible app/window/about/Discord preview text from Aelrith Forge to Kon. and updated the console-style UI label to K. Console.
- Replaced the visible AF sidebar mark with the provided K. logo asset while keeping the existing asset path for safer loading.
- Kept internal module/package names, config keys, JSON filenames, and compatibility-sensitive technical identifiers unchanged for stability.

## v1.81
- Moved OCR debug event logs under output/ocr and settings backups under config/backups to keep runtime output separate from config and reduce folder clutter.
- Kept runtime logs in output/logs and preserved existing filenames, legacy migration behavior, and debug cleanup compatibility.

## v1.80
- Startup: removed the broken guarded-seed branch reference that stalled Initial Auto Start after weak marker-only evidence was rejected.
- Startup: weak marker-refresh confirmation now explicitly reopens the guarded startup path instead of silently poisoning later routing.
- Logging: added clearer post-rejection startup route logs so bounded guarded clicks are easier to diagnose.

## v1.79
- Checkbox detection: hardened Auto checkbox classification so wide/accent-only green signal no longer counts as authoritative enabled state without stronger inner-checkbox support.
- Startup: weak enabled reads are now treated as ambiguous, with clearer confidence/evidence logging and a safer guarded-seed recovery path.
- Recovery: manual auto-resume no longer trusts weak enabled reads as a reason to skip re-enable behavior.

## v1.78
- Startup: demoted marginal preflight "rolling" state after weak marker-only confirmation rejection so guarded seed-click logic is no longer suppressed.
- Startup: weak current-spec refresh evidence now falls back to a true non-rolling re-observe path instead of leaving startup stuck between fake enabled and fake rolling.
- Logging: clarified when marginal preflight evidence cannot suppress the guarded startup seed path.

## v1.77
- Startup: treat weak/untrusted enabled checkbox reads as insufficient to suppress recovery.
- Startup: allow one guarded startup seed click on safe filler when verify still shows not rolling and popup is absent.
- Startup: reduce false "already enabled" suppression caused by weak checkbox accent reads.

## v1.76
- Fixed startup false-idle path where a weak enabled Auto checkbox read could block immediate recovery even though no real rolling proof existed.
- Safe NON_TARGET startup now falls back to manual reroll sooner when Auto looks enabled but behavior evidence is still weak.
- Rejected weak target OCR before mythical/manual classification so garbage or partial non-rollables stop triggering full transition handling.

## v1.75
- Fixed startup false-positive rolling confirmation caused by marker-only current-spec refresh during Initial Auto Start preflight.
- Startup now requires stronger evidence than a lone `current_spec_marker_changed` signal before skipping the autoroll click.

## v1.72
- fixed root watchdog failure path where ambiguous Auto checkbox reads could still trigger a recovery click and false failure

## v1.7
- Separated persistent config from generated runtime/debug output using a cleaner `config/` + `output/` layout, while keeping legacy file loading compatible.
- Redirected runtime logs, OCR debug logs, captures, OCR crops, diagnostic snapshots, and history JSON to grouped output folders for easier debugging and less root-folder clutter.
- Cleaned up Discord plain-text formatting, muted near-miss pings, and kept live-status updates non-pinging for easier scanning.
- Made watchdog stale suspicion more conservative on flat NON_TARGET filler states and avoided speculative suspicion-stage checkbox clicks when the auto state is still ambiguous.
- Added one final diagnostic auto-checkbox confirmation read on uncertain startup/recovery paths and trimmed manual reroll auto-resume delay slightly without changing popup safety.

## v1.6.16
- Further tightened safe NON_TARGET startup front-half timing by shortening the startup probe, reusing popup-clear state into the bridge probe, and using a more compact compact-preflight handoff.

## v1.6.15 - Startup First-Attempt Reliability + Watchdog Tuning
- Safe NON_TARGET startup preflight now uses a lighter fail-fast path on compact preflight runs, avoiding expensive multi-source checks on flat screens.
- Guarded startup recovery now performs one compact retry-preflight before giving up, improving first-attempt reliability on safe NON_TARGET filler states.
- Added startup reliability logs for first-attempt success/failure reasons.
- Watchdog stale suspicion threshold and suspicion-stage recovery timing were tightened conservatively for faster but still bounded reaction.
- Suspicion-stage watchdog verify now uses a compact fast-verify path.

## v1.6.14
- Startup: compressed remaining front-half proof for safe NON_TARGET filler states by shortening the early startup delay probe further and reusing popup-clear knowledge when handing off from the bridge probe to compact preflight.
- Startup: compact NON_TARGET preflight now skips redundant popup re-check work and uses a tighter poll delay for faster time-to-first-roll without weakening confirmation rules.
- Watchdog: added an early stale-suspicion stage before full recovery so clearly flat, popup-free NON_TARGET stale states can trigger recovery sooner without a reckless global timeout cut.
- Logging: added richer startup/watchdog responsiveness logs, including reused popup-clear state and stale-suspicion timing/exit details.

## v1.6.13
- Compressed normal NON_TARGET startup front-half latency further by shortening the initial startup delay probe and adding a compact preflight path after weak bridge-probe fallback.
- Compact preflight now uses a single fast psm=6 pass with shorter poll delay when startup is already on a popup-free NON_TARGET filler screen and the bridge probe failed weakly/non-improving.
- Added preflight log fields for compact_non_target_preflight and bridge_fallback_reason to make remaining front-half delay sources easier to inspect.

## v1.6.12
- Startup speed: made dead verification phases fail faster during startup by disabling expensive multi-source recovery checks in startup quick-verify paths and abandoning weak, non-improving phases sooner.
- Startup speed: conditionally skip the duplicate double-check phase when startup auto-verify already established a flat, non-improving non-rolling state.
- Logging: added explicit startup timing for skipped double checks and dead-phase fail-fast exits to make lingering verify time easier to spot.

## v1.6.11
- Reduced wasted NON_TARGET startup bridge-probe time by making the bridge probe fail fast when it provides weak/non-improving evidence, then falling through to the faster preflight path sooner.
- Fixed displayed version metadata so the app title/version now matches the actual patch version.
- Added targeted futureproof startup logs for bridge-probe usefulness, exit reasons, preflight bypass/fallback, and startup logic version tracking.

## v1.6.10
- Startup speed: added a fast NON_TARGET bridge probe so strong filler startup evidence can skip duplicate Initial Auto Start preflight work.
- Startup timing: normal NON_TARGET filler runs can now early-trust rolling when a quick follow-up behavior probe confirms it.
- Logging: added startup bridge-probe timing/support logs for safer front-half startup dedup.

## v1.6.9

- Reduced normal NON_TARGET filler startup latency by shortening the blocking startup delay with an early probe and by adding a startup-fast NON_TARGET current-spec probe before the slower full validation path.
- Optimized startup preflight for safe NON_TARGET filler states by biasing the verify order toward faster current-spec marker confirmation and logging when the fast non-target path is used.
- Added startup timing logs for conditional startup-delay shortening and fast current-spec probe decisions to make front-half startup latency easier to debug.

## v1.6.8

- Reduced bad-current-spec startup latency by tightening manual reroll popup/settle timing in startup-specific flows.
- Avoided duplicate post-reroll startup verification when `manual_reroll_flow()` has already behavior-confirmed rolling.
- Added timing log for skipped duplicate startup reroll verification to make time-to-first-roll debugging clearer.

## v1.6.7
- Startup latency optimization: defer non-critical live status creation and passive shard reporting until after startup has already confirmed rolling, prioritizing time-to-first-roll without weakening startup safety.
- Added startup timing logs for deferred non-critical work so latency impact is easier to trace in future runs.

## v1.6.6
- Fixed startup fallback routing so safe NON_TARGET filler startup states prefer a bounded auto-resume attempt before any manual reroll fallback.
- Added targeted startup route logging: fallback_route, route_reason, decision_confidence, supports, failure_type, and current_spec_class in startup summaries.

## v1.6.5

- Optimized startup and transition timing with conservative caps on startup verify delays, faster preflight poll pacing, and shorter guarded/auto-resume settle waits.
- Added startup timing logs so delay budgets and adaptive early-exit behavior are easier to inspect without weakening bounded recovery rules.
- Tightened popup and immediate auto-resume transition pacing to reduce dead time between safe checks while keeping verification intact.

## v1.6.4

- Hardened startup confirmation so an enabled Auto checkbox no longer counts as success by itself without supporting behavior evidence.
- Tightened startup preflight acceptance by downgrading marginal rolling detections into checkbox-path revalidation instead of immediate success.

## v1.6.3
- Harden startup rolling verification with image-change aware classification (`rolling`, `not_rolling`, `unreadable_but_changed`, `unreadable_static`).
- Improve startup verify logs with signal sources, material-change flags, OCR quality, and verification classification.
- Avoid early startup fast-fail when verification is unreadable but the stats region changed meaningfully.

## v1.6.2
- Added dedicated `logs/` and `json/` output folders so runtime logs, OCR debug logs, settings, history, and near-miss data no longer clutter the project root.
- Redirected runtime log rotation/cleanup and OCR debug log cleanup to the new `logs/` folder while preserving existing behavior.
- Redirected settings/history/near-miss JSON writes and backups to the new `json/` folder with automatic folder creation.

## v1.6

- Reworked startup autoroll into a clearer observe -> decide -> act -> verify flow for Initial Auto Start.
- Separated startup UI truth (auto checkbox) from behavior truth (rolling verification) and let behavior win when signals disagree.
- Added bounded guarded startup recovery: one fallback auto-enable click is allowed only after checkbox reads and verification both stay unreadable with no popup detected.
- Improved startup logs to show auto_state, rolling_state, popup_state, decision, action, and verification result more clearly.

## v1.59
- Targets UI now uses a single threshold slider per stat and automatically uses the stat cap as the max.
- Cleaned transparent container and collapsible styling to remove dark highlighted text boxes and improve alignment.

## v1.58.3
- Locked the Auto verify delay, Auto verify polls, and Auto verify poll delay settings to safe defaults in the UI and settings payload so accidental changes cannot break rolling.

## v1.58.2
- Startup resilience: if Initial Auto Start cannot confirm rolling from OCR but the final auto-checkbox check shows Auto enabled, AF now continues into the main loop and lets the watchdog verify live rolling instead of stopping immediately.
- Added final startup auto-state logging for easier diagnosis of startup verify failures.

## v1.58.1

- Improved Auto checkbox detection reliability with multi-sample reads, slightly wider checkbox crops, and clearer sample diagnostics to reduce ambiguous checkbox state reads.

## v1.58

- Updated the UI branding to use an AF-only sidebar mark, removed extra top-left creator/title clutter, and improved footer wrapping for long copyright text.
- Added proprietary copyright notices in the UI, README, and LICENSE.txt without changing engine behavior.

# Changelog

## v1.57.14

- Runs the partial target-mythical confirm window during startup fast current-spec checks as well as normal rolling checks.
- Requires manual reroll Auto-resume to confirm rolling activity before reporting flow completion.
- Routes failed bad-mythical manual rerolls into the normal recovery failure budget instead of letting the watchdog become the expected finisher.

## v1.57.13

- Added a short bounded confirm window for plausible partial target-mythical OCR reads before final fragment/junk rejection.
- Improved manual reroll Auto-resume safety by avoiding speculative uncertain-state toggles and failing clearly when resume is unconfirmed.
- Preserved strict OCR junk rejection, `NON_TARGET` filler handling, popup safety, and watchdog fallback behavior.

## v1.57.12

- Automatically deletes old rotated runtime backup logs matching `aelrith_forge_logs.*.bak.json` on controller startup.
- Leaves the active runtime log and unrelated archived/debug artifacts untouched, with compact cleanup logging.

## v1.57.11

- Cleared the unexpected no-roll watchdog stale-event signature and cooldown timestamp after verified recovery.
- Added regression coverage so a successful watchdog recovery cannot suppress a later genuine stall.

## v1.57.10

- Added an unexpected no-roll watchdog that detects stale rolling activity and makes one controlled Auto re-enable attempt.
- Verifies watchdog recovery with the existing strict activity confirmation before resuming, then routes failures through the normal recovery budget.
- Preserved startup-only fallback behavior, manual reroll safety, popup handling, `NON_TARGET` filler routing, and OCR rejection rules.

## v1.57.9

- Aligned Auto checkbox click and read geometry around the same final nudge-adjusted target.
- Added Auto checkbox state diagnostics with click coordinates, read region, classifier metrics, and diagnostic snapshot crops.
- Moved checkbox state detection into a testable image classifier with stronger enabled/disabled heuristics while preserving startup fallback safety.

## v1.57.8

- Allowed Initial Auto Start to send one controlled fallback Auto click when checkbox state remains unreadable after retry.
- Made startup success depend on normal rolling verification after the fallback click, without reintroducing rollback/toggle loops.
- Preserved the v1.57.7 `NON_TARGET` rollable-filler routing and existing known-enabled/known-disabled Auto behavior.

## v1.57.7

- Stopped treating `NON_TARGET` current specs as manual-reroll blockers during startup, recovery fallback, and the normal loop.
- Let legitimate rollable filler continue through normal Auto/start-or-recover handling instead of invoking popup confirmation or Auto-resume by itself.
- Preserved GOD/HIGH_VALUE stop behavior, BAD/DISABLED target rerolls, and strict OCR junk/fragment rejection.

## v1.57.6

- Separated keeper target traits from broader legitimate rollable non-target traits.
- Classified recognized/current-spec non-target rolls as `NON_TARGET` filler so startup, recovery, and loop paths can reroll them instead of treating them as blocked OCR.
- Preserved strict junk/fragment rejection and added regression coverage for target traits, non-target filler, startup/recovery rerolls, and future target expansion.

## v1.57.5

- Removed speculative Auto-checkbox clicks during Initial Auto Start when checkbox state remains unreadable after retry.
- Made startup fail safely with `failed_uncertain_auto_state` without sending enable or rollback clicks in the unknown-state path.
- Added regression tests proving repeated unreadable startup retries do not physically toggle the Auto checkbox.

## v1.57.4

- Made manual reroll auto-resume fail safely when Auto state remains uncertain, restored, or rolled back.
- Prevented manual reroll from logging completion unless Auto resume is confirmed through a safe result.
- Added regression tests for unsafe manual-reroll resume outcomes and startup current-spec reroll failure handling.

## v1.57.3

- Rolled back startup cautious Auto-checkbox clicks when post-click validation remains unreadable.
- Added explicit startup logging for unknown-state safety rollback paths and preserved `failed_uncertain_auto_state` summaries.
- Covered enabled, disabled, and still-unknown uncertain Auto validation outcomes with focused regression tests.

## v1.57.2

- Prevented mouse-wheel scrolling over unfocused numeric controls from silently changing thresholds or timing settings.
- Applied focus-gated wheel behavior to target min/max spin boxes, threshold sliders, and Settings/Targets numeric controls.
- Preserved normal page scrolling and kept engine behavior unchanged.

## v1.57.1

- Replaced the top subtitle with a cleaner Arcane Operator Console label and tightened the header hierarchy.
- Reformatted Main tab active targets into compact per-spec lines with the CURRENT SPEC OCR requirement separated for easier scanning.
- Lightly refined Targets and Settings section spacing without changing tab structure or engine behavior.

## v1.57

- Compactified the developer UI into a smaller side-console profile with a reduced default window size and sensible non-maximized proportions.
- Tightened header, sidebar, status strip, card, table, and row spacing while preserving the graphite/bronze arcane-console theme.
- Refined Main, Targets, Settings, Debug, and Tools pages for denser side-tool use without moving features or changing engine behavior.

## v1.56

- Polished the developer cockpit header, card framing, table spacing, status badges, and footer treatment for a cleaner dark fantasy control-panel feel.
- Increased Main page emphasis on Current Roll and Current Detection while improving Recent Events and table integration.
- Standardized plain-text Discord message templates for live status, god rolls, near misses, passive shard updates, macro attention alerts, popup stuck alerts, and webhook tests.
- Preserved Discord dedup behavior, screenshot attachment behavior, and all parser/recovery/startup/shard engine logic.

## v1.55

- Redesigned the developer UI into a five-tab fantasy cockpit layout: Main, Targets, Settings, Debug, and Tools.
- Rebuilt Main as an operator console with control, current roll, current detection, session health, startup/recovery/shard status, and recent events panels.
- Moved target thresholds into a dedicated Targets tab with clearer Min/Max threshold grouping and deliberate apply controls.
- Reorganized Debug and Tools so decision-chain diagnostics, runtime logs, snapshots, OCR previews, popup tests, classification tests, shard previews, and webhook tests are easier to scan and run.
- Updated the desktop theme toward a dark graphite, bronze, and muted violet internal-operator-console style without changing parser, recovery, shard, popup, or webhook logic.

## v1.54

- Added explicit startup outcome classification and one compact `[Startup Summary]` log for every startup path.
- Separated uncertain Auto enable attempts from ordinary clicks, including validation and restored uncertain-click reporting.
- Made startup failures explicit when rolling cannot be confirmed instead of continuing optimistically.
- Reduced repeated Rampage fragment-rejection churn with longer active suppression and less frequent grouped summaries.
- Preserved parser safety, fragment rejection correctness, popup handling, shard suspicious-zero protection, and strict recovery confirmation rules.

## v1.53

- Strengthened Initial Auto Start handling when Auto state is uncertain with retry detection, cautious enable validation, and restore-on-off protection.
- Shortened startup unreadable verification to fail after fewer junk samples and avoid redundant slow fallback layers in clearly bad startup contexts.
- Reduced Rampage fragment-rejection churn with longer dedup windows, near-identical fragment grouping, and grouped suppression summaries.
- Preserved parser safety, fragment rejection correctness, popup handling, shard suspicious-zero protection, and strict recovery confirmation rules.

## v1.52

- Added a fast startup current-spec gate that classifies the visible roll before Initial Auto Start.
- Startup now manually rerolls readable BAD/DISABLED mythicals immediately and skips redundant Initial Auto Start after a successful manual reroll.
- Preserved startup GOD/HIGH_VALUE stop behavior and falls back to Initial Auto Start when the current-spec read is not reliable.
- Fixed startup autoroll recovery when Auto checkbox state remains uncertain by retrying the state read and making a bounded cautious enable attempt.
- Kept strict rolling verification as the only success signal after uncertain Auto handling, so weak/static OCR still cannot fake recovery.
- Preserved accidental-untick protection by skipping the toggle whenever Auto appears enabled and only clicking directly when Auto appears off.
- Added tests for uncertain startup Auto handling, failed uncertain-enable validation, and already-enabled Auto protection.

## v1.51.7

- Tightened Auto checkbox recovery logs so uncertain Auto state is reported as a cautious fallback instead of an enable click.
- Removed leftover "after auto click" wording from startup/recovery popup handling now that Auto uses safe ensure-on behavior.
- Added recovery-path tests proving AF skips Auto toggles when Auto already appears enabled and never clicks on uncertain Auto state.
- Preserved parser safety, fragment rejection, popup handling, shard protections, and strict recovery confirmation logic.

## v1.51.6

- Replaced blind Auto checkbox toggles in startup/recovery with conservative `ensure_auto_enabled()` checks.
- Added visual Auto checkbox state detection so AF skips toggling when Auto already appears enabled and only clicks when it appears confidently off.
- Updated popup/manual reroll auto-resume paths to use the same safe Auto-enable helper instead of blindly clicking the toggle.
- Added logs for enabled/off/uncertain Auto states and preserved parser, popup, shard, and recovery confirmation safety.

## v1.51.5

- Fast-failed initial auto-start verification after repeated unreadable samples so bad startup contexts no longer burn the full recovery poll chain.
- Shortened initial auto-start verify delays/polls while keeping strict material-change, popup, and structured recovery confirmation rules intact.
- Added compact per-stage startup recovery timing logs for auto verify, double-check, manual fallback, and manual fallback verify.
- Tightened passive-shard empty-check gating so healthy trusted shard counts suppress stale suspicious-zero OCR triggers and skip unnecessary empty confirmation.
- Preserved parser safety, fragment rejection, shard suspicious-zero protection, popup safety, and fake-recovery protections.

## v1.51.4

- Replaced the raw startup delay with interruptible startup sleep and lowered the default startup wait from 3.0s to 2.0s.
- Shortened initial auto-start recovery by fast-failing unreadable auto verifies and capping startup attempts.
- Added startup and initial auto-start timing logs for baseline comparisons.
- Further reduced passive-shard empty-check churn by keeping not-confirmed logs behind the relevance gate.
- Preserved strict parser, fragment rejection, suspicious-zero, popup, and fake-recovery protections.

## v1.51.3

- Gated passive-shard empty confirmation so healthy trusted shard counts skip noisy not-confirmed checks.
- Added low/suspicious shard evidence logs for empty-check triggers while preserving strong empty-stop confirmation.
- Coalesced repeated identical Rampage fragment rejection logs without weakening fragment rejection.
- Kept parser acceptance, shard safety, recovery truthfulness, popup logic, and UI behavior unchanged.

## v1.51.2

- Added interruptible sleeps and stop checks inside recovery verification, popup clearing, manual reroll, and loop delays.
- Made `bot.stop()` wait briefly for the worker thread to exit after requesting stop.
- Reduced unreadable stuck recovery latency by fast-failing the duplicated verify/manual fallback chain when fallback classification is unclassified and auto verify is unreadable.
- Added compact logs for manual-stop aborts and preserved strict parser/recovery/shard safety rules.

## v1.51.1

- Reduced conservative recovery timing defaults while preserving strict material-change confirmation rules.
- Trimmed popup/manual reroll dead time and skipped redundant popup re-checks after verified clears.
- Reduced duplicate popup OCR during recovery midpoint checks and added compact recovery/popup timing logs.
- Kept parser acceptance, fragment rejection, shard empty safety, and trait-only recovery rejection unchanged.

## v1.51

- Marked `v1.51 Stable Baseline` as the rollback-safe checkpoint before future tuning, optimization, shard, debug, or UI polish changes.
- Clarified passive-shard Discord reporting so live-status updates are logged and failed live-status updates fall back to standalone shard messages.
- Fixed passive-shard K-value parsing so plain values like `201K` remain `201000` instead of being inferred as `20.1K`.
- Made passive-shard empty-stop detection reject suspicious bare-zero OCR reads such as `0PassiveShards`.
- Preserved the previous valid shard count when zero-like shard OCR lacks strong empty evidence.
- Required strong zero evidence before confirming empty shards so real empty reads can still stop safely.
- Added diagnostic snapshot bundles with screenshots, OCR candidates, classification state, popup/recovery/shard state, active targets, and recent log context.
- Added manual debug tools for capturing a report, saving a screenshot, testing popup detection, and testing current-roll classification from the Logs page.
- Added a compact Last Decision Chain view plus structured OCR candidate/rejection details for faster parser and recovery diagnosis.
- Added optional automatic diagnostic snapshots for macro stops, popup-stuck alerts, and repeated recovery failures with retention settings.

## v1.4.10

- Rejected fragmentary Rampage OCR reads so lone Damage/Crit Damage snippets cannot become usable current-roll parses.
- Strengthened Rampage Damage/Crit Damage separation with stricter ordered-field usability and heavier collision penalties.
- Tightened OCR candidate coherence scoring and merge trust so clean fragments lose to structurally complete Rampage reads.
- Expanded startup cleanup to remove legacy OCR debug logs and generated debug/preview screenshots in addition to OCR crops.

## v1.4.9

- Fixed Rampage parsing so normal Damage and Crit Damage stay separated when both appear in one OCR line.
- Improved OCR candidate selection with structural coherence scoring that prefers internally consistent parses over raw OCR quality alone.
- Added an optional startup cleanup setting that rotates the runtime log and clears generated OCR debug logs/crops before live test runs.

## v1.4.8

- Reduced the default stuck timeout from 10s to 7s so recovery begins sooner after true rolling inactivity.
- Tightened recovery confirmation so trait-only or same-current-roll OCR no longer counts as successful recovery.
- Added recovery logs for stuck timeout threshold, confirmation reason, trait-only samples, and material OCR differences.

## v1.4.7

- Improved Rampage Crit Damage parsing for mangled OCR labels such as `CritDanuge`, `GritDamage`, and `CiitDaitage`.
- Tightened stat-number association so glued trailing stats like `CritChance3.2%,CritDanuge7.2%` parse both Crit Rate and Crit Damage.
- Downgraded nonfatal noisy candidate numbers to parse warnings when a plausible stat value was already recovered.

## v1.4.6

- Softened CURRENT SPEC gating so strong trait/stat OCR blocks can be classified when the marker text is missing.
- Added dedicated CURRENT SPEC marker OCR, more tolerant marker matching, and clearer marker/trait/stat gate logging.
- Allowed safe partial structured reads, such as Rampage with one trailing stat missing, to evaluate as BAD/HIGH_VALUE instead of forcing recovery churn.

## v1.4.5

- Added a live Discord run status message that is edited in place when supported, with lower-noise snapshot fallback.
- Added high-signal Discord alerts for god rolls, near misses, macro stops, repeated recovery failures, and stuck reroll popups.
- Added optional failure screenshots for popup-stuck and macro-stop alerts.
- Added lightweight webhook dedup/spam control and moved routine passive shard updates into the live status path.

## v1.4.4

- Rejected garbage OCR as recovery proof and added a classification-first current-roll fallback that manually rerolls visible bad specs before retrying stuck recovery.
- Added desired-target confirmation before apply plus a compact active-target summary in the main UI.
- Improved recovery responsiveness with shorter verified popup retry waits, faster manual popup polling, and fewer redundant popup OCR checks.

## v1.4.3

- Hardened reroll confirmation popup detection and clearing with fuzzy popup OCR, verified Yes-click retries, and safer manual recovery logging.
- Improved passive shard OCR/reporting reliability with padded shard-region OCR variants, clearer parse failure logs, and shared live/preview OCR attempts.

## v1.4.2

- Made recovery confirmation tolerate repeated junk STATS_REGION OCR after a completed button flow and added popup/banner, trait marker, and multi-source OCR activity signals.
- Added a passive shard preview action with raw/processed images, OCR text, cleaned text, and parsed shard count.

## v1.4.1

- Added the current app version to backend debug and capture artifact filenames, including OCR crop images, OCR crop metadata, OCR debug logs, and god roll captures.

## v1.4.0

- Added the default Codex maintenance workflow to `AGENTS.md`, covering version bumps, changelog entries, debug artifact naming, hardcoded-version cleanup, and post-change audits.

## v1.3.0

- 

## v1.2.1 - 2026-04-15

- Added single-source app version metadata in `aelrith_forge/version.py`.
- Wired the app title, Qt application version, startup log, and packaging name to the shared version metadata.
- Added `tools/bump_version.py` for lightweight semantic version bumps.
- Documented the version bump workflow in `AGENTS.md`.
