# Result clarity web release

Web assets only: `depibeans/ui/dist/app.js`, `style.css` (Linux) and `hosting/private/fleet.js` (relay). No Python, no controller restart, no API writes. **Stored measurements and every calculation are unchanged**; this release changes words, labels, one removed chart and the export's columns.

- **One scope vocabulary.** Tiles, the detail dialog and the CSV use the same words for which pixels a number averages: `whole_frame` (F₀, Fm, Fm′, Fs, Background) and `signal_mask` (Fv, Fv/Fm, NPQ, ΦII). The dialog column that said "Whole image" for plant-pixel values now states the real scope.
- **Traceable CSV.** Adds run id, chamber, run completion and per-measurement UTC timestamps, scope, statistic (mean of pixels vs mean of per-pixel ratios), the dark-reference capture paired with each NPQ/ΦII, commanded intensity in controller units, trigger lateness, quality notes, and segmentation algorithm/status. File name carries run id and date.
- **One results presentation.** "Results over time" and its "≈0.8 healthy" band are removed. The quenching profile is the single time view; it now also plots F₀ and the dark-reference Fv/Fm, and its axes say "Whole frame" and "Plant pixels".
- **Dates.** Age is counted in calendar days (a two-day-old result no longer says "yesterday"); the run picker shows each run's date; the panel is titled "Fluorescence".
- **Regions, not leaves.** Automatic regions are named "Region", with algorithm version and status, a statement that they are not verified leaves and are not tracked between runs, three decimals, and fragments under 2 % of the largest region left out of the table (still exported).
- **Chamber status.** Fleet and the chamber strip no longer say "Ready" for "reachable and idle". They say Running, Busy, In use · live view, Scheduled · time, or Idle, and append "not commissioned" when the controller reports it.
- **Start review.** States duration in human units, start and estimated end with timezone, counts of light changes and measurements with first/last times, repeat blocks, that intensity is commanded controller units, and that the draft is saved as a new version first. The button reads "Review & start" again.

Not verified by this release: light output, saturation adequacy, optical timing, segmentation against real leaves. Those are chamber checks.

Checks: JS syntax, build consistency, 12 unit tests, 23 real-input browser checks; 76 of 77 fixture checks before the label fix (the one failure was the start-button label, corrected here and not re-run at the user's request). Rendered locally with copies of three real runs. Rollback: the release receipt.
