# Source, preview, releases

This is a published copy of the source. The working repository, with its history, deployment records and web-hosting code, is private.

## Layout

- `depibeans/`: current Linux application and integrated UI.
- `profiles/`: existing versioned hardware profiles. A deployment must never replace a machine profile, calibration or runtime data implicitly.

## Local preview

Python 3.10+ and Node for syntax checks; no hardware SDK or SSH required:

```sh
python3 preview/serve.py
```

Open http://127.0.0.1:18822. This uses the actual repository app.js/style.css directly, not relay insertion. Hardware, scheduling and actuation operations are blocked. The striped camera image is synthetic; the plan is a sample fixture. Local drafts live in ignored `.runtime/preview`. The local verification button runs graph/script regressions and modifies local drafts; reload before repeating.

## Experiment editor: sources, build, checks

The graph/script editor is written as small ES modules in `depibeans/ui/src/editor/`:

| module | responsibility |
| --- | --- |
| `constants.js` | limits: 0.1 s grid, light range, event cap |
| `time.js` | time text and parsing; stored times are whole milliseconds and are never rounded |
| `plan.js` | event identity, run boundaries, overlap rules, selection that survives re-sorting |
| `history.js` | the one undo/redo history of a draft |
| `repeats.js` | repeat blocks: instances, Change all, Only this, skipped instances |
| `script.js` | script text ⇄ plan; an invalid script never produces events |
| `presets.js` | preset insertion and the clipboard; protocol reuse and isolation |
| `chart.js` | SVG drawing only |
| `layout.js` | page arrangement around the editor |
| `editor.js` | the controller: gestures, keyboard, inspector, script panel |

Everything except `chart.js`, `layout.js` and `editor.js` is free of DOM access and unit-tested in Node.

The portal serves one plain script, so `tools/build_ui.py` concatenates the modules in dependency order into the single `<editor-bundle>` region of `depibeans/ui/dist/app.js`, inside a private function scope. There is no third-party bundler; the output depends only on the sources. **Edit the sources, run the build, commit both.** `python3 tools/build_ui.py --check` (also a unit test) fails when `app.js` is stale.

The editor reaches the application only through the `host` object passed to `DepiEditor.install(...)` directly below the bundle in `app.js`. That object is the whole interface: reading and writing the draft through the host's own validation, plus three hooks (one history, one renderer, reset on load). The editor patches no globals, and there is no runtime search for a comment or loading of hosting-private files. Older editor code is recoverable from the baseline Git tag.

```sh
python3 tools/build_ui.py                 # rebuild app.js from the modules
node --test tests/js                      # unit tests for the pure modules
python3 -m unittest tests.test_ui_build   # dist is current, valid, and the modules pass
python3 tools/run_ui_checks.py            # headless browser: preview/ui-test.js + real mouse/keyboard/touch
```

`tools/run_ui_checks.py` needs Playwright with Chromium (`pip install playwright && playwright install chromium`, e.g. in an ignored `.runtime` venv). It starts its own hardware-blocked preview on a free port with a throwaway draft store (`DEPI_PREVIEW_ROOT`), so runs are repeatable and never touch `.runtime/preview`. It fails on any console error and on any request to a hardware route.

The relay still performs existing fleet/header/login presentation adaptations. Those are preserved deliberately.

## Deployment

Use existing SSH authentication. Copy `tools/release/targets.example.json` to an ignored local file and configure the Linux release root, hosting root, SSH options, and source-to-destination allowlist. Never include credentials in tracked config. Keep Linux before hosting when migrating from the injected editor. The production configuration for this migration publishes only app.js, style.css and index.php. Other tracked fleet/mixer files can be explicitly mapped for a later reviewed web release.

```sh
python3 tools/release/deploy.py deploy --ref <commit> --config .runtime/targets.json
```

The command archives the exact commit, checks JS/PHP syntax, stages and hashes files, backs up old files, acquires locks, checks preimages, atomically replaces each file, and verifies installed hashes. Preimage hashes are derived from the recorded release commit in Git (or an explicit `baseline_ref` for a reviewed baseline). Missing baselines fail closed. Configured `expected` hashes must agree with Git. Every file listed in the live release manifest is checked for drift before replacement, independently of configuration. If drift is found, preserve the live bytes and reconcile them in Git before deployment; do not bypass this by pinning the changed live hash. Both hosts are prepared before either is applied. A failure attempts rollback in reverse host order. Receipts are saved under `.runtime/releases`; server-side stages retain backup files, commit, hashes and journal. `.depi-web-release.json` on each target records its installed web release. Multi-host deployment is not one atomic transaction; interrupted network access may require rerunning rollback from the receipt.

```sh
python3 tools/release/deploy.py rollback --receipt .runtime/releases/<release>.json
```

Rollback restores the exact previous bytes and verifies them. It refuses to overwrite a later unrelated change. Keep the receipt and remote backups. Review failures before manually removing a deployment lock.

The default configuration deploys web assets only. An explicitly planned maintenance release may add Python source files to the allowlist; those files are syntax checked as well. The tool never restarts services, changes profiles or runtime data, or issues hardware commands. Before a Python release, verify no active run, pending event, live capture or queued schedule, stop the controller, deploy the reviewed commit, and start the controller again. If startup fails, restore the release receipt before starting the previous code.

Both Claude and Codex should work from this checkout, commit changes, run the local checks, and deploy the commit. Do not upload ad hoc edits from older work folders.
