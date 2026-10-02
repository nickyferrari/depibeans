// The experiment editor: a graph and a script over one draft.
//
// The draft itself belongs to the host application (the plan text box, validation,
// duration, saving). This controller edits it only through the `host` object it is
// given, so there is one write path, one history and one renderer:
//
//   host.read() / host.write(plan)      the draft, through the host's own validation
//   host.useCheckpoint / useRenderer    host actions share this history and renderer
//   host.aroundLoad                     opening another experiment resets the editor
//
// Nothing here sends a request or commands hardware.
import { GRID_MS, LIGHT_MAX, MIN_SPAN_MS } from './constants.js';
import { exactTime, isLongPlan, parseTime, timeLabel, trimNumber } from './time.js';
import { eventSignature, findCollision, hasOverlap, isAnchored, isLight, plainCopy, remapSelection } from './plan.js';
import { createHistory } from './history.js';
import { blockOf, changeAllInstances, detachInstances, repeatDeltas, repeatSelectionKey, skipInstances } from './repeats.js';
import { checkParsedScript, composeScript, eventsFromScript, parseScript, scriptMatchesPlan } from './script.js';
import { PRESET_CHOICES, PRESET_DEFAULTS, makeClip, pasteRows, presetRows, repeatTemplate } from './presets.js';
import { drawChart, eventPosition, lightCeiling, measureChart, readoutText } from './chart.js';
import { arrangeEditorPage } from './layout.js';

const SCRIPT_LINE_PX = 20;        // must match the script's CSS line height
const NUDGE_RUN_MS = 1200;        // key presses closer than this are one undo step
const SCRIPT_RUN_MS = 2000;       // typing pauses shorter than this are one undo step
const REPEAT_ANSWER_MS = 6000;    // how long "Change all / Only this" carries to the next arrow-key nudge

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const snap = ms => Math.round(ms / GRID_MS) * GRID_MS;

export function installEditor(host) {
  const { $, G, S, text, svg, xy } = host;
  const document = $('plan-editor').ownerDocument;
  const planBox = $('plan-editor');
  const MOD = /Mac|iP/.test(navigator.platform) ? '⌘' : 'Ctrl';

  const totalMs = () => host.totalMs();
  const long = () => isLongPlan(totalMs());
  const label = ms => timeLabel(ms, long());
  const relativeBasis = () => G('basis').value === 'relative';
  const eligible = event => event.relative === relativeBasis() && (isLight(event) || event.kind === 'capture');

  // ---- layout -----------------------------------------------------------------
  // The chart replaces the host's timeline element so its old listeners go with it.
  const oldChart = G('timeline');
  const chart = oldChart.cloneNode(false);
  oldChart.replaceWith(chart);
  const frame = document.createElement('div');
  frame.className = 'ge';
  chart.before(frame);
  const bar = document.createElement('div');
  bar.className = 'ge-bar';
  const readout = document.createElement('span');
  readout.className = 'ge-readout';
  bar.append(readout);
  const status = G('message');
  const inspect = G('selection');
  frame.append(bar, chart, inspect, status);
  inspect.classList.add('ge-inspector');
  status.classList.add('ge-status');
  chart.setAttribute('tabindex', '0');
  chart.setAttribute('aria-label', 'Experiment timeline. Drag points to edit. Drag empty space to select. Arrow keys nudge by 0.1 seconds or one light unit; Shift for 1 second or ten units. Command C, V, D, Z. Alt-drag duplicates.');

  // ---- state ------------------------------------------------------------------
  const history = createHistory();
  let chosen = new Set();          // indices into plan.events
  let ownSelected = null;          // what this editor last told the host was selected
  let knownText = null;            // draft text the selection indices refer to
  let knownSignatures = [];
  let restoring = false;           // an undo/redo is reloading the draft
  let draft = 0;                   // increases whenever another draft is opened
  let lastNudge = null;
  let scriptRun = 0;               // time of the last script edit in the current typing run
  let clip = null;
  let cursor = null;               // paste position, ms
  let gesture = null;
  let geometry = null;
  let view = { start: 0, span: 1 };
  let yMax = LIGHT_MAX;
  let note = '';

  const say = message => { note = message || ''; };
  // Every user action runs here: a failure becomes a message, never a half-applied edit.
  function act(fn) {
    try { fn(); }
    catch (error) {
      say(error.message);
      try { draw(); } catch (_) { status.textContent = error.message; }
    }
  }
  const picked = plan => [...chosen].map(index => plan.events[index]).filter(Boolean);

  // ---- history ----------------------------------------------------------------
  function checkpoint() {
    scriptRun = 0;
    lastNudge = null;
    return history.checkpoint(planBox.value);
  }
  host.useCheckpoint(checkpoint);

  function restore(saved) {
    scriptRun = 0;
    const keep = readView();
    restoring = true;
    try { host.reload(JSON.parse(saved)); } finally { restoring = false; }
    setView(keep.start, keep.span);
    chosen.clear();
    lastNudge = null;
    render();
  }
  function travel(direction, done) {
    const saved = history[direction](planBox.value);
    if (saved === undefined) return;
    restore(saved);
    text('plan-result', done + ' · draft not saved.');
    say('');
    draw();
  }
  const undo = () => travel('undo', 'Undo applied');
  const redo = () => travel('redo', 'Redo applied');

  // Opening, creating or importing an experiment is a new draft: nothing of the old
  // one may be undone into it or pasted onto it by index.
  host.aroundLoad(
    () => {
      if (restoring) return;
      scriptRun = 0; history.clear(); chosen.clear(); ownSelected = null; cursor = null; lastNudge = null; pendingRepeat = null; draft++; say('');
    },
    () => { if (!restoring) knownText = null; },
  );

  // ---- selection --------------------------------------------------------------
  function reconcile(plan) {
    const now = planBox.value;
    if (now === knownText) return;
    const signatures = plan.events.map(eventSignature);
    if (knownText !== null) {
      const next = remapSelection(knownSignatures, chosen, signatures);
      const hostIndex = host.selectedEvent.get();
      const valid = hostIndex !== null && !!plan.events[hostIndex];
      const hostPicked = valid && hostIndex !== ownSelected;        // e.g. "Add light change" selected its new point
      chosen = hostPicked || (valid && !next.size && chosen.size === 1) ? new Set([hostIndex]) : next;
    }
    knownText = now;
    knownSignatures = signatures;
  }
  function adopt(plan, rows) {
    chosen = new Set(rows.map(event => plan.events.indexOf(event)).filter(index => index >= 0));
    knownText = planBox.value;
    knownSignatures = plan.events.map(eventSignature);
  }

  // ---- committing a change ----------------------------------------------------
  // `timed` means event times changed, so slots must be checked. `keyRun` marks a
  // keyboard nudge, the only edit allowed to reuse the last repeat answer unasked.
  function commit(plan, rows, timed, keyRun = false) {
    if (rows.some(event => blockOf(plan, event))) { askRepeat(plan, rows, timed, keyRun); return false; }
    return commitNow(plan, rows, timed);
  }
  function commitNow(plan, rows, timed) {
    if (timed) {
      if (hasOverlap(plan)) throw Error('Overlapping events. Choose another time.');
      const hit = findCollision(plan, rows);
      if (hit) throw Error(`Overlaps an existing ${hit.kind === 'capture' ? 'measurement' : 'light setting'} at ${label(hit.delay_ms)}.`);
    }
    const added = checkpoint();
    try { host.write(plan); }
    catch (error) { if (added) history.dropLast(); throw error; }
    adopt(plan, rows);
    return true;
  }

  // ---- view -------------------------------------------------------------------
  // The visible window lives in the host's "View starts at" / "Visible span" fields (hours).
  const readView = () => ({ start: Number(G('start').value) * 3600000, span: Number(G('span').value) * 3600000 });
  function setView(start, span) {
    const all = totalMs();
    span = clamp(span, Math.min(MIN_SPAN_MS, all), all);
    start = clamp(start, 0, all - span);
    G('span').value = span / 3600000;
    G('start').value = start / 3600000;
  }
  function zoom(factor, about) {
    const now = readView();
    const pivot = about ?? now.start + now.span / 2;
    const span = clamp(now.span * factor, Math.min(MIN_SPAN_MS, totalMs()), totalMs());
    setView(pivot - (pivot - now.start) * span / now.span, span);
    render();
  }
  const fit = () => { setView(0, totalMs()); render(); };

  // ---- clipboard and editing --------------------------------------------------
  function copy() {
    const plan = host.read(), rows = picked(plan);
    if (!rows.length) throw Error('Nothing selected.');
    clip = makeClip(plan, rows, draft);
    say(`Copied ${rows.length}.`);
    paint();
  }
  function paste(at) {
    if (!clip) throw Error('Nothing copied.');
    const plan = host.read(), end = totalMs();
    at = snap(clamp(at ?? cursor ?? readView().start, 0, end));
    if (at + clip.span > end) throw Error(`Does not fit: needs ${trimNumber(clip.span / 1000, 3)} s before the end.`);
    const rows = pasteRows(plan, clip, at, relativeBasis(), draft);
    plan.events.push(...rows);
    commit(plan, rows, true);
    say(`Pasted ${rows.length} at ${label(at)}.`);
    render();
  }
  function duplicate() {
    const rows = picked(host.read());
    if (!rows.length) throw Error('Nothing selected.');
    copy();
    paste(Math.max(...rows.map(event => event.delay_ms)) + Math.max(GRID_MS, snap(clip.span * .1)));
  }
  function remove() {
    const plan = host.read(), end = totalMs();
    const rows = picked(plan).filter(event => !isAnchored(event, end));
    if (!rows.length) {
      if (chosen.size) throw Error('The first and final light settings cannot be deleted.');
      return;
    }
    skipInstances(plan, rows);
    const drop = new Set(rows);
    plan.events = plan.events.filter(event => !drop.has(event));
    commitNow(plan, []);
    say(`Deleted ${rows.length}.`);
    render();
  }
  function nudge(dt, dv) {
    const plan = host.read(), end = totalMs(), rows = picked(plan);
    if (!rows.length) return;
    const movable = rows.filter(event => !isAnchored(event, end)), lights = rows.filter(isLight);
    if (dt) {
      if (!movable.length) throw Error('The first and final light settings keep their time.');
      dt = clamp(dt, -Math.min(...movable.map(event => event.delay_ms)), end - Math.max(...movable.map(event => event.delay_ms)));
      movable.forEach(event => { event.delay_ms += dt; });
    }
    if (dv) {
      if (!lights.length) return;
      dv = clamp(dv, -Math.min(...lights.map(event => +event.value)), LIGHT_MAX - Math.max(...lights.map(event => +event.value)));
      lights.forEach(event => { event.value = String(+event.value + dv); });
    }
    if (!dt && !dv) return;
    const key = [...chosen].join();
    const sameRun = !rows.some(event => blockOf(plan, event)) && lastNudge && lastNudge.key === key && performance.now() - lastNudge.at < NUDGE_RUN_MS && history.canUndo;
    if (sameRun) {
      if (dt && findCollision(plan, rows)) throw Error('Overlaps an existing event.');
      host.write(plan);
      adopt(plan, rows);
    } else commit(plan, rows, !!dt, true);
    lastNudge = { key: [...chosen].join(), at: performance.now() };
    say('');
    render();
  }

  // ---- drawing ----------------------------------------------------------------
  function draw(plan) {
    plan = plan || gesture?.preview || host.read();
    view = readView();
    if (!(view.span > 0)) return;
    geometry = measureChart(chart);
    yMax = lightCeiling(plan, G('max').value);
    host.setViewState({ start: view.start, span: view.span, yMax });
    const selection = gesture?.rows ? new Set(gesture.rows) : new Set(picked(plan));
    drawChart(chart, svg, { plan, view, endMs: totalMs(), long: long(), yMax, geometry, eligible, selection, cursor, box: gesture?.type === 'box' ? gesture.box || null : null });
    readout.textContent = readoutText(selection, gesture, long());
    status.textContent = note || (selection.size || gesture ? '' : `Drag to move · drag empty space to select · Alt-drag copies · arrows nudge 0.1 s · ${MOD}-scroll zooms`);
    buttons.undo.disabled = !history.canUndo;
    buttons.redo.disabled = !history.canRedo;
    buttons.copy.disabled = buttons.duplicate.disabled = buttons.remove.disabled = !selection.size;
    buttons.paste.disabled = !clip;
    buttons.fit.disabled = view.start < 1 && Math.abs(view.span - totalMs()) < 1;
  }
  function paint(plan) { try { draw(plan); } catch (error) { status.textContent = error.message; } }

  // ---- inspector: exact values for the selection --------------------------------
  function inspector(plan) {
    const rows = picked(plan), one = rows.length === 1 ? rows[0] : null, time = G('time'), value = G('value');
    inspect.hidden = !rows.length;
    ownSelected = one ? plan.events.indexOf(one) : null;
    host.selectedEvent.set(ownSelected);
    if (!rows.length) return;
    time.type = 'text'; time.inputMode = 'decimal'; time.removeAttribute('min'); time.removeAttribute('step');
    value.min = 0; value.max = LIGHT_MAX; value.step = 1;
    time.parentElement.firstChild.textContent = one ? (long() ? 'Time (h:mm:ss)' : 'Time (s)') : 'Shift time (s)';
    value.parentElement.firstChild.textContent = one ? 'Light level' : 'Set light level';
    time.value = one ? exactTime(one.delay_ms, long()) : '0';
    time.dataset.original = time.value;
    time.disabled = !!one && isAnchored(one, totalMs());
    const lights = rows.filter(isLight);
    value.disabled = !lights.length;
    value.value = one ? (one.value ?? '') : (lights.length && lights.every(event => event.value === lights[0].value) ? lights[0].value : '');
    value.placeholder = one ? '' : 'unchanged';
    value.dataset.original = value.value;
    G('delete').textContent = 'Delete';
    const chooser = $('graph-event-protocol');
    if (chooser) {
      chooser.parentElement.hidden = !(one && one.kind === 'capture');
      chooser.parentElement.firstChild.textContent = 'Protocol';
      chooser.replaceChildren();
      plan.protocols.forEach(protocol => chooser.add(new Option(protocol.id, protocol.id)));
      chooser.value = one?.protocol || '';
    }
    if (one && one.kind === 'capture') {
      const index = plan.protocols.findIndex(protocol => protocol.id === one.protocol);
      if (index >= 0) host.setProtocolIndex(index);
    }
  }
  // Only a field the user actually changed is applied: changing the level never moves the time.
  function applyInspector() {
    const plan = host.read(), rows = picked(plan), end = totalMs();
    if (!rows.length) throw Error('Nothing selected.');
    const time = G('time'), value = G('value');
    const timeChanged = time.value !== time.dataset.original && !time.disabled;
    const valueChanged = value.value !== value.dataset.original && value.value !== '';
    if (!timeChanged && !valueChanged) return;
    if (timeChanged) {
      if (rows.length === 1) {
        const ms = parseTime(time.value, long());
        if (ms < 0 || ms > end) throw Error('Time must fall within the experiment duration.');
        rows[0].delay_ms = ms;
      } else {
        const seconds = Number(time.value);
        if (!Number.isFinite(seconds)) throw Error('Enter the shift in seconds.');
        const movable = rows.filter(event => !isAnchored(event, end)), dt = Math.round(seconds * 1000);
        if (movable.some(event => event.delay_ms + dt < 0 || event.delay_ms + dt > end)) throw Error('Shift moves an event outside the experiment.');
        movable.forEach(event => { event.delay_ms += dt; });
      }
    }
    if (valueChanged) {
      const level = Number(value.value);
      if (!Number.isInteger(level) || level < 0 || level > LIGHT_MAX) throw Error(`Light level is a whole number 0–${LIGHT_MAX}.`);
      rows.filter(isLight).forEach(event => { event.value = String(level); });
    }
    commit(plan, rows, true);
    say('');
    render();
  }

  // ---- the single renderer ------------------------------------------------------
  // Host actions call render() by name and arrive here.
  function render() {
    act(() => {
      const plan = host.read();
      reconcile(plan);
      inspector(plan);
      draw(plan);
      syncScript(plan);
      host.renderPulses(plan);
    });
  }
  const hostRender = host.useRenderer(render);

  // ---- pointer: mouse, pen and touch share these handlers -------------------------
  const timeAt = position => clamp(view.start + (position.x - geometry.left) / geometry.width * view.span, 0, totalMs());

  chart.addEventListener('pointerdown', event => act(() => {
    if (event.button !== 0 || !geometry) return;
    event.preventDefault();
    chart.focus({ preventScroll: true });
    say('');
    const position = xy(event, chart), hit = event.target.closest?.('[data-event]');
    if (hit) {
      const index = Number(hit.dataset.event);
      if (event.shiftKey) { chosen.has(index) ? chosen.delete(index) : chosen.add(index); render(); return; }
      const wasChosen = chosen.has(index);
      if (!wasChosen) chosen = new Set([index]);
      gesture = { type: 'move', base: host.read(), indices: [...chosen], hit: index, wasChosen, start: position, moved: false, dt: 0, dv: 0 };
    } else if (event.metaKey || position.y > geometry.axis) gesture = { type: 'pan', start: position, view: readView() };
    else gesture = { type: 'box', start: position, keep: new Set(event.shiftKey ? chosen : []), moved: false };
    try { chart.setPointerCapture(event.pointerId); } catch (_) { /* synthetic pointer */ }
    render();
  }));

  chart.addEventListener('pointermove', event => act(() => {
    const g = gesture;
    if (!g) return;
    const position = xy(event, chart), dx = position.x - g.start.x, dy = position.y - g.start.y;
    if (g.type === 'pan') { setView(g.view.start - dx / geometry.width * g.view.span, g.view.span); paint(); return; }
    if (!g.moved && Math.hypot(dx, dy) < 4) return;
    g.moved = true;
    if (g.type === 'box') {
      const x0 = Math.min(g.start.x, position.x), x1 = Math.max(g.start.x, position.x), y0 = Math.min(g.start.y, position.y), y1 = Math.max(g.start.y, position.y);
      g.box = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
      const plan = host.read();
      chosen = new Set(g.keep);
      plan.events.forEach((candidate, index) => {
        if (!eligible(candidate)) return;
        const at = eventPosition(candidate, geometry, view, yMax);
        if (at.x >= x0 && at.x <= x1 && at.y >= y0 && at.y <= y1 && at.x >= geometry.left && at.x <= geometry.right) chosen.add(index);
      });
      paint(plan);
      return;
    }
    // Move. The offset snaps to the grid; every event keeps its own sub-grid timing.
    const end = totalMs(), plan = structuredClone(g.base), source = g.indices.map(index => plan.events[index]);
    g.copying = event.altKey;
    let rows = source;
    if (g.copying) { rows = source.map(plainCopy); plan.events.push(...rows); }
    let dt = snap(dx / geometry.width * view.span), dv = Math.round(-dy / (geometry.bottom - geometry.top) * yMax);
    if (event.shiftKey) { if (Math.abs(dx) >= Math.abs(dy)) dv = 0; else dt = 0; }
    const movable = rows.filter(candidate => g.copying || !isAnchored(candidate, end)), lights = rows.filter(isLight);
    dt = movable.length ? clamp(dt, -Math.min(...movable.map(e => e.delay_ms)), end - Math.max(...movable.map(e => e.delay_ms))) : 0;
    dv = lights.length ? clamp(dv, -Math.min(...lights.map(e => +e.value)), LIGHT_MAX - Math.max(...lights.map(e => +e.value))) : 0;
    movable.forEach(e => { e.delay_ms += dt; });
    lights.forEach(e => { e.value = String(+e.value + dv); });
    Object.assign(g, { preview: plan, rows, dt, dv });
    paint(plan);      // nothing is written until the pointer is released
  }));

  function release(cancelled) {
    const g = gesture;
    gesture = null;
    if (!g) return;
    act(() => {
      if (g.type === 'move') {
        if (g.moved && !cancelled && (g.dt || g.dv)) {
          if (g.copying && !g.dt) throw Error('Drag sideways to place the copy.');
          commit(g.preview, g.rows, !!g.dt);
          if (g.copying) say(`Copied ${g.rows.length} to ${label(Math.min(...g.rows.map(e => e.delay_ms)))}.`);
        } else if (!g.moved && g.wasChosen && chosen.size > 1) chosen = new Set([g.hit]);
      } else if (g.type === 'box' && !g.moved && !cancelled) {
        chosen = new Set(g.keep);
        cursor = snap(timeAt(g.start));
      }
    });
    render();
  }
  chart.addEventListener('pointerup', () => release(false));
  chart.addEventListener('pointercancel', () => release(true));

  chart.addEventListener('wheel', event => {
    if (!geometry) return;
    const horizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY);
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      zoom(Math.exp(clamp(event.deltaY, -60, 60) * .01), timeAt(xy(event, chart)));
    } else if (horizontal || event.shiftKey) {
      event.preventDefault();
      const now = readView();
      setView(now.start + (horizontal ? event.deltaX : event.deltaY) / geometry.width * now.span, now.span);
      render();
    }   // a plain vertical wheel scrolls the page
  }, { passive: false });
  chart.addEventListener('dblclick', event => { if (!event.target.closest?.('[data-event]')) act(fit); });

  // ---- keyboard -----------------------------------------------------------------
  chart.addEventListener('keydown', event => {
    const key = event.key.toLowerCase(), mod = event.metaKey || event.ctrlKey;
    let fn = null;
    if (mod && key === 'z') fn = event.shiftKey ? redo : undo;
    else if (mod && key === 'y') fn = redo;
    else if (mod && key === 'c') fn = copy;
    else if (mod && key === 'x') fn = () => { copy(); remove(); };
    else if (mod && key === 'v') fn = () => paste();
    else if (mod && key === 'd') fn = duplicate;
    else if (mod && key === 'a') fn = () => { chosen = new Set(host.read().events.map((e, i) => eligible(e) ? i : -1).filter(i => i >= 0)); render(); };
    else if (mod) return;
    else if (key === 'delete' || key === 'backspace') fn = remove;
    else if (key === 'arrowleft' || key === 'arrowright') fn = () => nudge((key === 'arrowleft' ? -1 : 1) * (event.shiftKey ? 1000 : GRID_MS), 0);
    else if (key === 'arrowup' || key === 'arrowdown') fn = () => nudge(0, (key === 'arrowdown' ? -1 : 1) * (event.shiftKey ? 10 : 1));
    else if (key === 'escape') fn = () => {
      if (gesture) gesture = null;
      else if (chosen.size) chosen.clear();
      else if (frame.classList.contains('ge-expanded')) expand();
      say('');
      render();
    };
    else if (key === 'f') fn = fit;
    else if (key === '=' || key === '+') fn = () => zoom(1 / 1.5);
    else if (key === '-') fn = () => zoom(1.5);
    if (fn) { event.preventDefault(); act(fn); }
  });
  // Exact values apply when the field is committed (Enter or leaving it). An invalid
  // value is refused with a message and the draft is untouched.
  for (const field of [G('time'), G('value')]) {
    field.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); act(applyInspector); } });
    field.addEventListener('change', () => act(applyInspector));
  }

  // ---- toolbar ------------------------------------------------------------------
  const buttons = {};
  function tool(key, caption, title, fn, startsGroup) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ge-button';
    button.textContent = caption;
    button.title = title;
    if (startsGroup) button.dataset.group = 'start';
    button.onclick = () => { act(fn); chart.focus({ preventScroll: true }); };
    bar.append(button);
    buttons[key] = button;
  }
  function expand() {
    const on = frame.classList.toggle('ge-expanded');
    document.documentElement.classList.toggle('ge-lock', on);
    buttons.expand.textContent = on ? 'Collapse' : 'Expand';
    buttons.expand.title = on ? 'Return to the page (Esc)' : 'Use the full window';
    requestAnimationFrame(() => { paint(); chart.focus({ preventScroll: true }); });
  }
  tool('undo', 'Undo', `Undo (${MOD}Z)`, undo);
  tool('redo', 'Redo', `Redo (⇧${MOD}Z)`, redo);
  tool('copy', 'Copy', `Copy selection (${MOD}C)`, copy, true);
  tool('paste', 'Paste', `Paste at the cursor (${MOD}V)`, () => paste());
  tool('duplicate', 'Duplicate', `Duplicate after the selection (${MOD}D)`, duplicate);
  tool('remove', 'Delete', 'Delete selection (⌫)', remove);
  tool('out', '−', 'Zoom out (−)', () => zoom(1.5), true);
  tool('in', '+', 'Zoom in (+)', () => zoom(1 / 1.5));
  tool('fit', 'Fit', 'Show the whole experiment (F)', fit);
  tool('expand', 'Expand', 'Use the full window', expand, true);
  G('apply').onclick = () => act(applyInspector);
  G('apply').hidden = true;                  // the fields apply themselves; kept for scripts and tests
  G('delete').onclick = () => act(remove);

  // ---- repeat blocks: Change all / Only this --------------------------------------
  const ask = document.createElement('div');
  ask.className = 'ge-ask';
  ask.hidden = true;
  status.before(ask);
  let pendingRepeat = null;
  let repeatAnswer = null;

  function resolveRepeat(mode) {
    const job = pendingRepeat;
    pendingRepeat = null;
    ask.hidden = true;
    chart.focus({ preventScroll: true });      // keyboard shortcuts keep working after the answer
    if (!job || mode === 'cancel') { render(); return; }
    act(() => {
      if (job.baseText !== planBox.value) throw Error('The draft changed. Select the event again.');
      repeatAnswer = { key: job.key, mode, at: performance.now() };
      const rows = mode === 'one' ? detachInstances(job.plan, job.rows) : changeAllInstances(job.plan, job.rows, job.deltas, totalMs());
      commitNow(job.plan, rows, job.timed);
      say(mode === 'one' ? 'Changed this one only; it no longer follows the repeat.' : 'Changed every repeat.');
      render();
    });
  }
  // The edit is held, not written, until the question is answered.
  function askRepeat(plan, rows, timed, keyRun) {
    const key = repeatSelectionKey(rows);
    pendingRepeat = { plan, rows, timed, key, deltas: repeatDeltas(host.read(), plan, rows), baseText: planBox.value };
    if (keyRun && repeatAnswer && repeatAnswer.key === key && performance.now() - repeatAnswer.at < REPEAT_ANSWER_MS) { resolveRepeat(repeatAnswer.mode); return; }
    const block = blockOf(plan, rows.find(event => blockOf(plan, event)));
    ask.replaceChildren();
    const question = document.createElement('span');
    question.textContent = `Part of a repeat ×${block.count}.`;
    ask.append(question);
    for (const [mode, caption] of [['all', 'Change all'], ['one', 'Only this'], ['cancel', 'Cancel']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ge-button';
      button.textContent = caption;
      button.onclick = () => resolveRepeat(mode);
      ask.append(button);
    }
    ask.hidden = false;
    ask.querySelector('button').focus();
  }

  // ---- script panel ---------------------------------------------------------------
  const panel = document.createElement('div');
  panel.className = 'ge-script';
  const head = document.createElement('div');
  head.className = 'ge-script-head';
  const title = document.createElement('span');
  title.textContent = 'Script';
  const scriptState = document.createElement('span');
  scriptState.className = 'ge-script-state';
  const insert = document.createElement('select');
  insert.className = 'ge-insert';
  insert.setAttribute('aria-label', 'Insert a preset at the cursor');
  insert.add(new Option('Insert…', ''));
  for (const [value, caption] of PRESET_CHOICES) insert.add(new Option(caption, value));
  head.append(title, scriptState, insert);
  const body = document.createElement('div');
  body.className = 'ge-script-body';
  const gutter = document.createElement('div');
  gutter.className = 'ge-gutter';
  gutter.setAttribute('aria-hidden', 'true');
  const code = document.createElement('textarea');
  code.className = 'ge-code';
  code.rows = 10;
  code.spellcheck = false;
  for (const [name, value] of [['autocapitalize', 'off'], ['autocomplete', 'off'], ['wrap', 'off'], ['aria-label', 'Experiment script. One event per line: time, then light, measure or set. repeat blocks end with end.']]) code.setAttribute(name, value);
  body.append(gutter, code);
  panel.append(head, body);
  inspect.after(panel);

  let lineEvents = [];             // per script line, the indices of the events it stands for
  let mappedText = null;           // script text those indices were computed for
  let scriptPlanText = null;       // draft text the script currently represents
  let scriptProblem = null;        // { line, message } while the script is invalid
  let scriptTimer = null;
  let fromScript = false;          // a render caused by the script must not rewrite the script
  let gutterLines = 0;

  function paintScript() {
    const count = code.value.split('\n').length;
    if (count !== gutterLines) {
      gutter.replaceChildren();
      for (let i = 0; i < count; i++) { const number = document.createElement('div'); number.textContent = i + 1; gutter.append(number); }
      gutterLines = count;
    }
    const live = code.value === mappedText;
    [...gutter.children].forEach((number, i) => {
      number.className = scriptProblem && scriptProblem.line === i ? 'ge-ln-error' : live && (lineEvents[i] || []).some(index => chosen.has(index)) ? 'ge-ln-on' : '';
    });
    gutter.scrollTop = code.scrollTop;
    scriptState.textContent = scriptProblem ? `Line ${scriptProblem.line + 1}: ${scriptProblem.message}` : '';
    scriptState.classList.toggle('ge-script-error', !!scriptProblem);
    panel.classList.toggle('ge-script-invalid', !!scriptProblem);
  }
  function showScript(plan) {
    const composed = composeScript(plan, { totalMs: totalMs(), long: long() });
    code.value = mappedText = composed.text;
    lineEvents = composed.lineEvents;
    scriptPlanText = planBox.value;
    scriptProblem = null;
  }
  function syncScript(plan) {
    const focused = document.activeElement === code;
    if (fromScript) scriptPlanText = planBox.value;
    else if (planBox.value !== scriptPlanText || (!focused && !scriptProblem && code.value !== mappedText)) showScript(plan);
    paintScript();
    if (!focused && chosen.size && code.value === mappedText) {
      const line = lineEvents.findIndex(list => (list || []).some(index => chosen.has(index)));
      if (line >= 0) {
        const top = line * SCRIPT_LINE_PX;
        if (top < code.scrollTop || top > code.scrollTop + code.clientHeight - SCRIPT_LINE_PX * 2) code.scrollTop = Math.max(0, top - SCRIPT_LINE_PX * 2);
        gutter.scrollTop = code.scrollTop;
      }
    }
  }
  function caretLines() {
    const value = code.value;
    return [value.slice(0, code.selectionStart).split('\n').length - 1, value.slice(0, code.selectionEnd).split('\n').length - 1];
  }
  function showDuration(ms) {
    const shown = host.planTiming.display(ms);
    S('days').value = shown.value;
    $('duration-unit').value = shown.unit;
  }
  function renderFromScript() { fromScript = true; try { render(); } finally { fromScript = false; } }

  // Script -> draft. An invalid script is reported on its line and changes nothing.
  function applyScript() {
    clearTimeout(scriptTimer);
    scriptTimer = null;
    const source = code.value;
    let plan, parsed;
    try {
      plan = host.read();
      parsed = parseScript(source, plan, { long: long() });
      checkParsedScript(parsed, parsed.duration ?? totalMs(), long());
    } catch (error) {
      scriptProblem = { line: error.line ?? 0, message: error.message };
      paintScript();
      return;
    }
    const { events, blocks } = eventsFromScript(plan, parsed);
    const before = totalMs(), newDuration = parsed.duration !== null && parsed.duration !== before;
    if (newDuration || !scriptMatchesPlan(plan, events, blocks)) {
      const now = performance.now(), sameRun = scriptRun > 0 && now - scriptRun < SCRIPT_RUN_MS && history.canUndo;
      const added = sameRun ? false : checkpoint();
      scriptRun = now;
      try {
        if (newDuration) { showDuration(parsed.duration); plan.studio = { ...plan.studio, duration_ms: parsed.duration }; }
        plan.events = events;
        plan.studio = { ...plan.studio, repeats: blocks };
        if (!blocks.length) delete plan.studio.repeats;
        host.write(plan);
        if (newDuration) S('last').value = host.dayCount();
      } catch (error) {
        if (newDuration) showDuration(before);
        if (added) history.dropLast();
        scriptProblem = { line: 0, message: error.message };
        paintScript();
        return;
      }
    }
    scriptProblem = null;
    lineEvents = [];
    for (const item of parsed.items) {
      const index = plan.events.indexOf(item.event);
      if (index >= 0) (lineEvents[item.line] = lineEvents[item.line] || []).push(index);
    }
    mappedText = source;
    const [first, last] = caretLines(), rows = [];
    for (let line = first; line <= last; line++) for (const index of lineEvents[line] || []) rows.push(plan.events[index]);
    adopt(plan, rows);
    renderFromScript();
  }
  // The caret selects in the graph: a plain line selects its event, a repeat line every instance.
  function caretSelect() {
    if (scriptProblem || code.value !== mappedText) return;
    const [first, last] = caretLines(), next = new Set();
    for (let line = first; line <= last; line++) for (const index of lineEvents[line] || []) next.add(index);
    if (next.size === chosen.size && [...next].every(index => chosen.has(index))) return;
    chosen = next;
    renderFromScript();
  }
  // Presets write ordinary events and protocols into this draft, at the cursor.
  function insertPreset(type) {
    const at = snap(clamp(cursor ?? 0, 0, totalMs()));
    if (type === 'repeat') {
      code.value = code.value.replace(/\s+$/, '') + '\n\n' + repeatTemplate(totalMs(), at, long());
      code.focus();
      applyScript();
      return;
    }
    const plan = host.read(), end = totalMs();
    const preset = host.presets.preset({ type, ...PRESET_DEFAULTS });
    const rows = presetRows(plan, preset, at, relativeBasis());
    const needed = at + preset.studio.duration_ms;
    if (needed > end) { showDuration(needed); plan.studio = { ...plan.studio, duration_ms: needed }; }
    plan.events.push(...rows);
    try { commitNow(plan, rows, false); }
    catch (error) { showDuration(end); throw error; }
    S('last').value = host.dayCount();
    setView(0, totalMs());
    say(`Inserted ${rows.length} events at ${label(at)}. Edit them here or in the graph.`);
    render();
  }

  insert.onchange = () => { const type = insert.value; insert.value = ''; if (type) act(() => insertPreset(type)); };
  code.addEventListener('input', () => { paintScript(); clearTimeout(scriptTimer); scriptTimer = setTimeout(() => act(applyScript), 300); });
  code.addEventListener('scroll', () => { gutter.scrollTop = code.scrollTop; });
  for (const type of ['click', 'keyup', 'select']) {
    code.addEventListener(type, event => {
      if (type === 'keyup' && !/^(Arrow|Page)|^(Home|End)$/.test(event.key)) return;
      act(caretSelect);
    });
  }
  code.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); chart.focus({ preventScroll: true }); }
    else if (event.key === 'Tab') { event.preventDefault(); code.setRangeText('  ', code.selectionStart, code.selectionEnd, 'end'); }
  });
  code.addEventListener('blur', () => {
    if (scriptTimer) act(applyScript);
    scriptRun = 0;
    if (!scriptProblem) act(() => { showScript(host.read()); paintScript(); });
  });

  // ---- every host entry point uses this renderer ------------------------------------
  // The host finishes building its page after this editor installs; arrange once it has.
  queueMicrotask(() => { try { arrangeEditorPage({ $, G, frame, bar, readout }); paint(); } catch (error) { console.error('Editor layout unavailable', error); } });
  planBox.removeEventListener('input', hostRender);
  planBox.addEventListener('input', () => render());
  for (const id of ['max', 'span', 'start']) G(id).oninput = () => render();
  G('basis').onchange = () => { chosen.clear(); render(); };
  new ResizeObserver(() => { if (chart.getBoundingClientRect().width) paint(); }).observe(chart);
  render();
}
