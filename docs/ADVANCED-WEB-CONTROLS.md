# DEPI 1: advanced controls release

Deployed September 15, 2026 at 9:56 PM America/Detroit to the existing Linux controller and https://relay.example.com/.

## What is now available

### Live → Camera settings

- Live exposure (10–1,000,000 µs), gain (0–33), reset to preview defaults, and actual camera setting readback.
- Preview settings persist across service restarts. The live camera restores its original acquisition settings when it closes. Scientific snapshot settings remain separate.
- Acquisition protocol editor: loops, frames per loop, measuring-light selection, saturation flash, auxiliary fast switch, exposure, interval, actinic shutter, camera group, camera IDs, analysis label, and additional legacy fields.
- Save/load/export/import camera protocols; compile pulse timing before acquisition.
- Acquisition remains restricted to what the deployed profile accepts. The existing fixed snapshot is accepted; editing a field does not approve a new hardware protocol.
- Live frames are decoded before replacing the visible image. Repeated copies of the same frame do not replace it. A transient failed request no longer hides a still-fresh frame; stale frames are still hidden.
- An open, visible Live screen can renew an expired live session. Leaving Live stops requesting frames, allowing the existing idle cleanup. Live viewing saves no image files.

### Experiments

- All 57 installed plans retained; all 57 passed the editor's structural/timing compilation checks.
- New, edit-as-copy for installed plans, duplicate, JSON import/export, versioned saving, and archive for custom plans.
- Step builder supports light changes, waits, clock times, captures, and repeat counts. The complete JSON editor preserves protocol and section details.
- Open an experiment's camera protocol directly in Camera settings.
- Validate plans, simulate, schedule a start, cancel a queued start, and pause after an event.
- Scheduled starts retain an immutable copy of the selected plan. Later edits do not change a queued experiment. Missed starts and starts blocked by another operation require rescheduling; they are not silently replayed.
- Run records show event outcomes and timestamps, downloadable JSON containing the original plan, attempts, results, and saved-image metadata. Older run records can be loaded.
- Paused simulations can resume their remaining events. Discarding a stopped run preserves its completed and uncertain attempts and saved images.

### System and Photos

- Export camera/controller configuration.
- Import/export legacy calibration points and calculate/download an offline quadratic fit.
- Existing original TIFF downloads and photo filters retained.
- Data remains on the Linux controller. No Kramer upload destination was invented or enabled.

## What is not complete

This release is **not yet a full, physically validated replacement** for the recovered legacy application.

| Remaining area | Current boundary | Completion evidence needed |
|---|---|---|
| FR, UVA, UVB and full light/zone control | Preview only under the current profile; main lighting remains 0–155 | Measured output, approved limits and rail/zone mapping |
| Research acquisition and experiment execution | Profile remains `commissioned: false`; only previously verified manual functions can operate hardware | Camera/FPGA pulse timing against the reference controller, complete experiment acquisition and original TIFF comparison |
| Hardware pause/restart recovery | Pause and record review exist; automatic replay and generic hardware resume remain blocked | Verified restoration of light and camera state without replaying uncertain actions |
| Calibration application | Points and fits can be managed offline; no coefficients are sent to hardware | Measured calibration and verified hardware write/readback procedure |
| Kramer transfer, retry/re-upload | Not configured | Actual hostname, transfer protocol, destination, account setup and expected dataset format. The recovered FileSync template has blank Host and Port fields. |
| Scientific analysis and alerts | Analysis labels are preserved; run reports are available | Lab-approved analysis definitions, expected results and alert recipients/workflows. No scientific analysis or email delivery is claimed. |
| Legacy arbitrary JavaScript workflows | Structured plans and Python backend support the mapped event/protocol model | Inventory/port any scripts that depend on behavior beyond those events. Uploaded code is not executed by the portal. |
| Other cameras/environmental hardware | This deployment targets the configured AVT camera and Nexys2 chamber | Actual working configurations and acceptance for other chambers/devices |

## Verification and deployment

- 26 existing controller/live-view/portal/operation tests passed against the staged modules.
- 9 workspace tests passed: version conflicts, archive preservation, actor-isolated uploads, malformed plan rejection, schedule snapshot/one-time dispatch, missed/restarted schedule handling, non-actuating preview settings, preservation of uncertain attempts, and offline fitting.
- JavaScript syntax and Python compilation passed.
- Local browser exercised preview settings, protocol saving/validation, experiment creation and version saving, simulation, and per-event reports with hardware disabled.
- Public portal readback after deployment showed a running live stream, no camera error, 250 µs exposure, gain 12, 1936 × 1456 Mono12, and `recording: false`.
- Existing saved-photo reference and installed experiment count were unchanged. No lighting commands or research acquisitions were issued for these checks.
- Deployed source and canonical local source hashes matched for all six updated files.
- Rollback source backup: `/home/chamber/DepiBeans/backups/advanced-20260915-215656`.

The next acceptance work is instrumented hardware comparison and confirmation of the Kramer data contract. Those require evidence beyond a successful web deployment.
