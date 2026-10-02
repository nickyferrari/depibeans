# Reconciled Fleet release

Preserved the exact live Linux UI in commit 26db710, on branch preserve/live-quenching-20260919, before merging the pending Fleet work. This preserves the quenching charts, phase bands, image hover previews and commanded-light CSV export. Authorship of the live-only changes was not independently established.

The tracked Linux source comparison against 096ca63 differed only in app.js and style.css. Five hosting source files matched the tracked hosting baseline. Local snapshots remain under ignored .runtime/preserve-20260919.

Fleet now offers Cards, Rows and Sync canvas, with a remembered browser view preference. The pending overview filters and chamber summaries are included. Existing live quenching charts are retained alongside the selectable calculated-results trend.

No tests were run at the user's request. Deployment performs syntax validation and installed-file hash verification. Only web assets are published; no controller restart or hardware operation is included. Deployment receipts under .runtime/releases provide rollback.
