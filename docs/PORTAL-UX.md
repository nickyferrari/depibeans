# Proposed portal experience

This is a design specification, not a deployed UI.

Entry point: Walker website → Lab control. Authenticate using the approved
WordPress identity integration, then show only assigned chambers.

## Fleet overview

Display the verified 24-chamber roster. A missing/offline chamber stays visible to
its authorized users instead of disappearing from the grid. Each compact card:

- Chamber name and stable ID.
- Status: online, stale, offline, fault, or setup required.
- Latest temperature/humidity/light measurements that actually exist, with units.
- Active experiment, next scheduled event, and last observation time.
- One clear Open button. No actuation from accidental card taps.

Allow filtering to assigned, active experiment, or needs attention. Do not add
invented demo chambers to the production roster or green simulated readings.

## Chamber page

Overview: latest measurements, freshness, experiment, recent changes.
Controls: explicit setpoints, current reported state, allowed ranges and units.
Schedules: New schedule, Pause/Resume, Edit, Delete, next event and recent runs.
Experiments: supported protocol selection, parameters, preview, start/stop state.
Calibration: commissioned-admin workflow, measurements, fit, original coefficients,
review/upload receipt and recovery. Preserve legacy import/export.
History: actor, request, execution result, sensor evidence, experiment artifacts.

Use capability-driven sections. If a chamber has no gas mixer or humidity actuator,
never show a working-looking control for it. Show the actual reason when a feature
is unavailable. Permissions and capability checks also run on the server.

For settings, use Set / Apply rather than ambiguous toggles. For schedules,
selected days have both a checkmark and color; paused and active have text labels.
Pausing schedules must not look like switching equipment off. Show next execution
in lab time, including the date. Failed/uncertain/partial runs remain visible.

On mobile, stack card headings and action rows, allow buttons to wrap, keep numeric
entry legible, and prevent horizontal page overflow. Use concise labels and an
accessible question-mark help popover for secondary explanations, operable by
hover, focus and touch. Do not hide material failed/uncertain outcomes in help text.

## Friday acceptance

A researcher can sign in, see only assigned real chambers, identify stale/offline
units, open a chamber and inspect actual recent observations. A validated control
shows its requested and reported result; an unvalidated capability cannot actuate.
The same account cannot bypass restrictions by requesting another chamber URL.
No simulator data is mixed into production. Production counts reconcile against
the actual fleet inventory captured from its control computer.
