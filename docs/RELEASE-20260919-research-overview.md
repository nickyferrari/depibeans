# Research overview web release

Fleet defaults to an ordered responsive overview, with a table view and filters for known location, status, and recorded run owner (including Mine). Sorting covers chamber, location, status, owner and last Fv/Fm. The existing sync canvas, names and colors remain available. The current registered inventory is still the existing three systems; this release does not register additional controllers or invent building/owner metadata.

DEPI 1 shows live state and event progress, next measurement or scheduled start, recorded run initiator when available in recent accepted actions, and the dated last Fv/Fm. Unavailable information is labelled. DEPI 2 remains setup/offline. The mixer uses existing read-only status RPCs; connectivity is not treated as evidence that an experiment is idle or running.

The chamber page exposes Fv/Fm, NPQ and PhiII histories for the selected measured run, with an elapsed-time axis and keyboard-accessible points that open the existing provenance/image detail. Fv/Fm has a contextual approximate 0.8 reference, not a diagnostic acceptance band. Existing scientific calculations are unchanged. The latest averaged image identifies its own experiment and timestamp independently of the selected trend run.

Start now retains the existing mandatory review. Schedule expands to show its input and submit control. Secondary experiment actions move to Experiment options. Graph tools appear on focus/hover and remain visible on touch. Tab titles show chamber, state and estimated remaining time when a relative plan provides it, otherwise event completion percentage.

Validation: JavaScript syntax, build consistency and diff whitespace only. Interactive and regression tests intentionally not run at the user's request. Deployment uses the versioned release tool with preimage hashes and rollback receipts. Files: app.js, style.css, fleet.js, fleet.css. No controller restart, hardware commands, database changes, calibration changes or scientific reprocessing.
