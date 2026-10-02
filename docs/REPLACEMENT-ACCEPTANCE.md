# DEPI 1 replacement: current status and acceptance

Updated September 15, 2026, 10:10 PM America/Detroit.

## Published

- Larger **Fleet** heading on the landing page.
- Large arrow-only back button inside the chamber; accessible name and hover text are “Back to Fleet.”
- DEPI tab icon, touch icon and page metadata. Sign-in/invitation pages use DEPI branding. The domain remains relay.example.com.
- Camera preview exposure/gain settings and actual camera readback.
- Editable acquisition protocols, including all fields used by the recovered waveform compiler.
- Experiment creation, duplication, import/export, versioned saving, version history and loading previous versions into the editor.
- Step builder, repeat counts, saved schedules, simulations, event-boundary pause, progress and run records.
- Recovery drafts containing only unattempted events. Completed events are omitted. Omitting uncertain events requires an explicit review choice. Original journal entries are retained. Recovery timing is rebased to the first remaining event; starting light/camera state must be specified and reviewed.
- Complete run downloads: original TIFF files, acquisition metadata (including failed captures when present), run report, event CSV and SHA-256 checksums. Parts contain at most 16 MiB of source files and are generated only on request. Export does not write another copy of the images to disk.
- Original saved-image gallery, deliberate snapshot capture, offline calibration tools and configuration exports.

## Deployment evidence

The latest deployment finished at 10:08 PM. Source backup:
`/home/chamber/DepiBeans/backups/continuation-20260915-220847`.

The deployed source and canonical local files matched. The pre-deployment saved-photo reference and preview settings were preserved. The chamber remained idle, and no lighting commands or scientific acquisitions were issued during this release.

35 existing controller/portal/live-view/workspace checks and 6 new recovery/export/version/icon checks passed. Local browser verification covered the larger heading, arrow navigation, recovery draft generation, two saved revisions, loading an older revision, and export links.

A read-only export of an existing completed Linux run produced a 5,642,650-byte ZIP with five entries. Its original-file checksums matched, and its JSON report and CSV were present. Public live view resumed with `recording: false`. Public page inspection confirmed the DEPI icon links and no FIN brand text in the page body.

## What prevents full replacement sign-off

### 1. Scientific hardware acceptance

The active profile still permits previously verified manual main lighting, fixed scientific snapshot and live preview. It does not authorize full research experiments or physical FR/UVA/UVB control.

Needed at the chamber:

| Check | Evidence to record |
|---|---|
| Establish the Windows reference and preserve rollback | Controller/configuration identifiers, original data backup and reference plan hashes |
| Main/FR/UVA/UVB and rail/zone mapping | Actual output measurements, units and operating limits for each configured channel |
| Pulse timing and camera integration | Measured measuring/saturation/auxiliary/shutter/trigger timing against the reference, plus corresponding camera frames |
| Complete experiment | Expected versus actual event order/timestamps, frame counts, image values, metadata and scientific analysis outputs |
| Interrupted operation/recovery | Camera/USB/network failure behavior, retained partial data, and restoration of known light/camera state without repeating uncertain actions |
| Restart and unattended operation | Observed physical output after process/power restart, schedule behavior, and operator review procedure |

Software waveform generation has existing documented reference comparisons. Those comparisons do not substitute for measured physical pulses or a complete scientific run.

The recovered AVT Java source sets camera exposure from the first protocol loop and uses Timed exposure with LevelHigh triggering. The Python adapter follows that behavior. Do not “fix” it to per-loop camera exposure without a deliberate scientific change and reference measurements.

### 2. Kramer server integration

The recovered FileSync and Emailer templates contain blank Host fields. There is no verified server destination, transfer account or active notification configuration to reuse.

Required handoff from the lab/IT:

- Server hostname, transfer protocol and destination folder.
- Approved account configuration on the controller; secrets should be entered directly into the deployment configuration, not a chat message.
- Accepted dataset format and association with chamber/experiment/sample identifiers.
- Required scientific reports and alert recipients, if these were provided by the server.

Until that contract is available, downloads retain the original files and complete local run context. No automatic upload, email delivery or server-side scientific analysis is claimed.

## Completion definition

A full replacement sign-off needs both the deployed operator workflows and the physical/data-system acceptance above. The current software is substantially expanded and deployed; the external acceptance is still open. Do not change `commissioned` to true merely to make the Start button available.
