# Verified connection recovery and current chamber health

A healthy current run no longer inherits amber status from earlier `needs_review` results or the broad commissioning flag when verified controls are enabled. Historical results and the system commissioning information remain visible. Current errors, low disk, and an unconfirmed stop without a newer light command remain attention conditions. Green describes current reported operational health, not scientific acceptance or full commissioning.

FPGA recovery occurs only on initial device connection under the existing exclusive device ownership lock. A zero status triggers one documented ChrisBlaster PING (0x09), requires a 0x09 register readback, then performs the existing clock validation. Ready connections do not ping. Running, error, and other unknown statuses are rejected. Mid-session faults are never automatically cleared or retried. No output command is part of this handshake.

Evidence on DEPI 1 on September 22: the unchanged September 15 USB driver read status zero; GET_CLOCK returned 50,000,000 Hz; PING returned/read back 0x09. Subsequent bounded main-light commands completed and the operator confirmed visible light. This establishes a recovery procedure, not the reason the board entered zero status.

Live preview temporarily applies and verifies Mono12 while it owns the camera, retaining ROI and binning. It restores the original format and other settings on exit or failure. Restoration failure remains an explicit maintenance error. Scientific captures and uncertain experiment retries are unchanged.

## Release boundary

Deploy only app.js and fleet.js to Walker hosting while the active experiment runs. Do not restart or replace the running controller. Python recovery requires a later maintenance release: verify no active run, pending event, live view, or queued schedule; stop the controller; deploy the immutable pushed revision through the release helper; start and verify it. Preserve the release receipt and rollback backups. This change does not mark commissioning complete or rewrite historical results.
