# Response to source review — prototype v0.2.0

The independent review tested the initial 17-test package. Subsequent changes
were implemented locally and verified with expanded tests; no new review request
or source transmission is required for this checkpoint.

## Fixed

1. Commands now use `(chamber, source, id)` as the key. Manual IDs must be canonical
   UUIDs; scheduler commands occupy a separate internal source namespace. A manual
   command with the same UUID as a schedule cannot poison that schedule.
2. Schedule IDs are scoped to their chamber. Duplicate/deleted-ID reuse produces
   `Rejected`, not an uncaught SQLite integrity exception.
3. Each due occurrence has its own transaction. A savepoint rolls back a failed
   simulator occurrence without reverting another chamber's committed event.
   Journal/database errors still propagate; this is not a physical I/O outbox.
4. Manual calls accept a bounded TTL. The engine assigns server expiry on first
   acceptance and retains it on retry. TTL/expiry is excluded from the semantic
   request fingerprint; a retry cannot extend the original expiry.
5. Every schedule paused by a manual command gets an audit event with the command
   ID. The result returns `paused_schedule_ids`.
6. Trusted local provisioning requires `granted_by` and records previous/new
   membership. Loss of write access pauses that subject's active schedules with
   audit records, without changing simulated output.
7. Invalid settings, numeric values, TTLs and IDs use `Rejected` at the engine
   boundary. Malformed legacy calibration input consistently raises `ValueError`.
   Numbers too large to convert to a supported finite float are rejected.
8. BROADCAST is named explicitly. Raw zone/all-zone/calibration packets require
   `allow_broadcast=True` for address zero. The calibrated A1 intensity command
   retains the deliberately documented legacy broadcast behavior.
9. A standalone Java harness executes the original App.java start/byte/stop
   waveform methods against an in-memory recorder. No hardware library is imported.
   The Python test compares the entire 114-pulse mask-and-duration sequence.
10. Native initialization/ABI findings are documented: inspected ChrisBlaster
    DllMain performs no board operations; CBgetVersion's bit encoding was checked
    in source. The current JVM and loaded ChrisBlaster DLL were verified x64;
    both JNI and plain native exports exist. Python read version 1.2.4 successfully.
    Loading a DLL still initializes its dependencies; this single version probe
    must not be generalized into permission to load arbitrary vendor libraries.
11. Calibration JSON retains integer versus floating-point intensity types.
    The fitter imports math normally.

## Tests

31 focused tests include cross-chamber ID reuse, scheduler namespace poisoning,
per-occurrence failure isolation after a simulated write, explicit broadcast,
full Java waveform comparison, permission/pause audit, revision race, expiry,
changed-TTL retry, deletion, invalid numbers and legacy data round-trip.

See docs/evidence for Windows results. The tests do not establish actual device
output, camera operation, unattended restart recovery or production readiness.

## Still intentionally not implemented

Physical journal/outbox and kill-mid-I/O recovery; recurring/DST scheduling;
WordPress authentication; cloud API; fleet discovery/telemetry; complete camera
or environmental adapters. Those need implementation and relevant hardware/fleet
validation, not dummy tests pretending the simulator covers them.

Prototype v1 databases are not silently altered. Opening one with this version
fails with an explicit message to retain it for history and use a fresh simulator
database. Production migrations remain part of the backend implementation.

Replay after permission revocation is rejected before cached results are returned
through the write interface. SQLite journals must reside on a local filesystem.
