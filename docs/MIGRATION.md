# Delivery plan and architecture

Target: Friday, September 18, 2026, 4 p.m. America/Detroit.
Milestone: authenticated Walker website portal displaying all 24 real chambers
with accurate per-chamber health. Enable each control only after its Python
adapter is verified against the corresponding hardware. Do not call a populated
simulator a connected fleet or promise complete physical parity from source alone.

## Architecture

Researcher browser → Walker website account/session → authorized portal API →
Python fleet coordinator → Python controller adapters → existing native/device
interfaces → chamber hardware. Device reports travel back through the same
logical chain, with observation and receipt times kept separately.

WordPress provides the existing website entry point and user identity. Keep
chamber execution, scheduling, and hardware access in Python. The website server
must validate identity and chamber permissions before requests reach Python;
never trust an actor/email supplied by browser JSON. A small WordPress integration
plugin may be PHP because WordPress runs PHP; that does not make the controller a
PHP application. Site admin access alone does not establish DNS/hosting rights.

The preferred fleet connection is an authenticated outbound HTTPS channel from
the fleet PC to the coordinator, with bounded requests and reconnect backoff.
Do not expose a Windows desktop, unauthenticated device API, maintenance shell,
or raw controller ports to the public internet. Select actual hosting after
checking Walker's hosting capabilities and the existing fleet topology.

Whether there is one PC handling 24 chambers, several PCs, or 24 distinct
controllers is not yet verified. Inventory before choosing agent placement.

## Required source-to-Python work

| Area | Current evidence | Python status / acceptance |
|---|---|---|
| Lighting commands | Calibratron + SmartlightController | Python driver and desktop installed; broadcast on/off and desktop lighting physically confirmed; individual rail mapping remains |
| Calibration | Legacy JSON and polynomial fitter | JSON + quadratic fit implemented; measured data comparison and EEPROM write/recovery pending |
| FPGA | ChrisBlaster C++ / Digilent SDK | Native Python adapter, ownership checks and protocol upload implemented; real waveform execution verified; recovery scenarios still need commissioning |
| Temperature/humidity | Bigfoot source variants | Determine working implementation/protocol and configured physical limits on fleet PC |
| CO2 | MK9000 API/source | Determine connected controller and support before exposing controls |
| Camera acquisition | Hitachi/AVT/CS/ETADA/Vimba paths | Identify actual cameras/SDK/architecture and reproduce acquisition/trigger behavior |
| Experiment protocols | PhenoScript + camera protocols | Parse supported experiment semantics into a bounded Python plan; do not execute arbitrary user code |
| Scheduling | Legacy events and new command design | One-time simulator scheduler implemented; recurring local-time schedules and durable physical outbox pending |
| Health | PC/process/USB inventory | Live observation pipeline and per-chamber stale/fault states pending fleet access |
| Accounts | Walker WordPress access reported | Production identity exchange, memberships and revocation pending authenticated inspection |
| Open source | Inherited MSU/vendor notices | Preserve provenance; confirm redistribution rights before any public repository |

## Physical-control contract

Exactly one process owns each FPGA/camera/actuator. No parallel port opening by
Java and Python. Migration begins in observation mode. Commission a single
capability on the testbed before enabling it in the portal; retain the original
launcher and configuration for rollback.

Commands carry ID, actor, chamber, requested settings, expected revision,
creation/expiry times, and execution result. A retry must not cause a second
physical action. A durable outbox records physical attempts before dispatch;
uncertain outcomes require state reconciliation, not blind replay. Never wrap
physical device I/O in a database transaction and assume rollback undoes it.

Show requested, controller-reported, and independently measured state separately.
A Windows heartbeat is not a sensor reading. Stale values retain their timestamp
and lose their healthy status. Missing capability remains unavailable rather than
silently simulated. Never use a green READY badge for an unvalidated adapter.

Schedules contain absolute settings, not toggles. Start with one device owner
and explicit event ordering; cancellation does not undo applied outputs. Manual
commands pause affected schedules. A missed event is recorded and not replayed
late. Record clock/timezone health and daylight-saving behavior. Physical
schedules must not activate until the command path and recovery are validated.

## Sequence toward Friday

1. Finish verified source/runtime/configuration backup and Python tests on testbed.
2. Connect the existing fleet computer read-only; capture working launchers,
   deployed versions, chamber IDs, routes, SDKs, limits, calibrations and current jobs.
3. Connect real read-only chamber health to authenticated portal accounts; verify
   exactly 24 expected entries and explain offline/missing chambers explicitly.
4. Commission Python lighting and one representative chamber's remaining adapters
   with an on-site observer; compare original behavior and measured outputs.
5. Enable validated controls, then schedules, per chamber. Verify restart,
   disconnection, expired commands, permission revocation and rollback.
6. Deliver operator runbook and handover. Report remaining parity gaps explicitly.

Camera timing and pulse generation stay on the FPGA/device timing engine;
Python compiles and uploads the plan. Browser timers and Python sleep loops are
not replacements for hardware timing.
