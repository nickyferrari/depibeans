# Modular experiment editor — web release

Web assets only: `depibeans/ui/dist/app.js` and `depibeans/ui/dist/style.css` on the DEPI 1 Linux release. No Python, no relay (`hosting/public/index.php` is unchanged), no profiles, no runtime data. No service restart is needed or performed; the portal reads these files per request.

## What changes for users

- Same editor behaviour, built from readable modules (`depibeans/ui/src/editor`).
- Graph and script first. The daily light-profile generator and the day-range fields are one collapsed section below the script. "+ Light" and "+ Measurement" sit in the editor toolbar.
- The duration field and the inspector's exact-value fields apply when committed (Enter or leaving the field); their separate Apply buttons are gone. An invalid value is refused with a message and the draft is untouched. "Apply light profile" remains explicit because it replaces events. Save remains apart from Review & start.
- Fixes: repeated preset insertion no longer accumulates numbered protocol copies; an unchanged script no longer causes a rewrite and undo step; a mouse drag on a repeated event always asks Change all / Only this (only arrow-key runs reuse the answer); keyboard shortcuts work immediately after answering.

## Verified before release (hardware-blocked preview only)

12 Node unit tests; `tests.test_ui_build` (dist equals what the sources build); 77 browser fixture checks; 23 real-input checks with browser-generated mouse, keyboard and touch events, including save and reopen of repeat blocks, undo across graph and script edits, invalid edits leaving the draft byte-identical, and switching experiments. No request to a hardware route occurs. None of this exercises a chamber.

## Deploy

```sh
python3 tools/build_ui.py --check
python3 tools/release/deploy.py deploy --ref <commit> --config .runtime/targets-web.json
```

`targets-web.json` lists only the two files above for the Linux target, with `expected` set to the hashes installed by release 9ff9ac8 (app.js `9952efef…`, style.css `54d4ef78…`), so the tool refuses if anything changed on the box since.

## Rollback

```sh
python3 tools/release/deploy.py rollback --receipt .runtime/releases/<release>.json
```

Restores the exact previous bytes of both files and verifies them. Users need a hard refresh either way.

## Not covered

Scientific calculations and segmentation are unchanged by this release. See `docs/FLUORESCENCE-METRIC-PROVENANCE.md` for what the tiles measure; changing them is a separate, reviewed Python maintenance release.
