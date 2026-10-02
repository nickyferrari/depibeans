# Response to independent architecture review — September 11, 2026

The review was design-only; the reviewer explicitly did not inspect Python code.
Treat its findings as design recommendations, not source-level validation.

## Accepted

- Fleet topology and the actual roster are the next information gate. Model
  never-seen, unsupported and decommissioned chambers explicitly.
- Verify custom WordPress plugin installation and outbound HTTPS before depending
  on the proxy design. If hosting forbids this, propose a separately hosted portal
  linked from WordPress; do not silently change the account/login experience.
- ABI proof before hardware ownership: native library/export shape, actual JVM
  bitness, Python bitness, SDK generation and single-owner behavior.
- First release: one Python coordinator deployment, one Uvicorn worker, scheduler
  task in that process, same Python package in agent mode. Keep hardware owners
  separate from the API process. Keep PostgreSQL work claiming; no broker.
- Still enforce a scheduler leader/lease and database occurrence uniqueness:
  rolling deploys or an accidentally started second process can overlap even when
  the documented worker count is one. Split the scheduler when needed, not now.
- Prefer existing compatible Python for the ABI spike. Do not upgrade the PC's
  working interpreter or drivers during discovery. Pin production Python after
  fleet OS/SDK checks; choosing the newest release is not a reliability argument.
- WordPress gateway authenticates each user and preserves client command IDs.
  Use maintained signing/verification libraries and scoped keys. Do not expose a
  generic proxy. The device-agent endpoint requires its own authentication;
  restricting every Python endpoint to the WordPress IP would block the agents.
- Put a physical-attempt journal in SQLite WAL with synchronous=FULL, intent
  recorded before dispatch, uncertain outcomes quarantined by physical resource.
- Calibrations, pulses and acquisitions need explicit non-replay/reconciliation
  rules. Distinguish cancellation, termination and undo.
- Stable occurrence IDs include schedule ID, plan version and resolved occurrence
  instant/fold; bounded recurrence horizon, no late replay. Recompilation and plan
  edits must supersede old future occurrences without duplicating an in-flight run.
- Revoking an owner pauses future schedules, records an admin-visible event and
  does not itself change hardware. No email delivery claimed until implemented.
- Validate an interactive task versus Session-0 service for the actual Windows
  drivers. Do not enable autologin or change desktop login settings by assumption.
- Add command race/expiry-boundary tests now. Add physical crash/DST tests when
  those implementations exist; simulation must not stand in for them.

## Corrections / limits

1. **Absolute setpoints are not automatically safe to replay.** A legacy setter
   may toggle a choke, reset a protocol or create a transient. Retry only after
   capability-specific validation, unchanged intent/revision, freshness and
   expiry checks. Otherwise preserve the uncertain outcome and reconcile.
2. **Health is multidimensional.** Host heartbeat, process presence, native
   communication, sensor quality and experiment state each have their own source
   and timestamp. They are not a universal progression: an experiment can run
   without a particular sensor, and an online PC does not prove a controller.
3. **Scope is the user's decision.** Do not silently redefine the requested full
   Python controller as a read-only product. Accurate 24-chamber visibility is
   the explicit Friday milestone; validated control remains the intended product.
   A read-only-first delivery is an implementation sequence, not abandonment of
   actuation, calibration or scheduling.
4. **No disruptive rollback rehearsal yet.** Document and prepare it now. Execute
   it with an on-site observer and a defined equipment state after backup proof;
   starting Java can zero lights, so rehearsal itself is an equipment operation.
5. Claims in the review about personnel availability/departure dates are not
   independently verified. Confirm the actual handover owner and dates.
6. Preserve copyright and licensing provenance. Public release needs permission
   for inherited code; original Python work can have an appropriate license once
   project ownership is settled. Do not publish the private backup.

## Implementation impact now

This pass adds an explicit synchronous=FULL setting and concurrency/expiry-boundary
coverage to the Python simulator. It does not enable physical hardware writes.
The backup receipt, Windows tests, native version probe and driver inventory are
recorded separately under docs/evidence and backups when completed.

See ARCHITECTURE-REVIEW.md for the original proposal. This response supersedes its
separate-scheduler and Python-3.13-first proposals for the first release.
