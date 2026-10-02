// Unit tests for the editor's pure modules. Run: node --test tests/js
import test from 'node:test';
import assert from 'node:assert/strict';
import { exactTime, parseTime, parseSpan, tickLabel, durationText, periodText } from '../../depibeans/ui/src/editor/time.js';
import { findCollision, hasOverlap, remapSelection, eventSignature, isAnchored, plainCopy } from '../../depibeans/ui/src/editor/plan.js';
import { createHistory } from '../../depibeans/ui/src/editor/history.js';
import { blocksOf, changeAllInstances, detachInstances, expandBlock, repeatDeltas, skipInstances } from '../../depibeans/ui/src/editor/repeats.js';
import { checkParsedScript, composeScript, eventsFromScript, parseScript, scriptMatchesPlan } from '../../depibeans/ui/src/editor/script.js';
import { adoptProtocol, makeClip, pasteRows, presetRows, repeatTemplate } from '../../depibeans/ui/src/editor/presets.js';

const light = (ms, value, extra = {}) => ({ kind: 'set', command: 'intensity', value: String(value), delay_ms: ms, relative: true, ...extra });
const capture = (ms, protocol, extra = {}) => ({ kind: 'capture', protocol, delay_ms: ms, relative: true, ...extra });
const protocol = (id, frames = '10') => ({ id, measurement_type: id, fields: { FramesPerLoop: frames } });
const basePlan = () => ({
  protocols: [protocol('dark-reference'), protocol('light-adapted')],
  events: [light(0, 0), capture(75430, 'dark-reference'), light(100250, 500), capture(200000, 'light-adapted'), light(400000, 0)],
  studio: { duration_ms: 400000 },
});
const roundTrip = (plan, totalMs = 400000) => {
  const long = totalMs >= 600000;
  const { text } = composeScript(plan, { totalMs, long });
  const parsed = parseScript(text, plan, { long });
  checkParsedScript(parsed, parsed.duration ?? totalMs, long);
  return { text, parsed, ...eventsFromScript(plan, parsed) };
};

test('times keep millisecond precision in both notations', () => {
  assert.equal(exactTime(100250, false), '100.25');
  assert.equal(parseTime('100.25', false), 100250);
  assert.equal(exactTime(93784500, true), '1d 02:03:04.5');
  assert.equal(parseTime('1d 02:03:04.5', true), 93784500);
  assert.equal(parseSpan('2d', true), 172800000);
  assert.equal(durationText(400000), '400 s');
  assert.equal(durationText(432000000), '5 d');
  assert.equal(periodText(86400000, true), '1d');
  assert.equal(tickLabel(1500, 500, false), '1.5 s');
  assert.throws(() => parseTime('soon', false), /seconds/);
});

test('history is multi-level, skips no-op states, and a new edit clears redo', () => {
  const history = createHistory();
  history.checkpoint('a'); history.checkpoint('b'); history.checkpoint('b');
  assert.equal(history.depth, 2);
  assert.equal(history.undo('c'), 'b');
  assert.equal(history.undo('b'), 'a');
  assert.equal(history.undo('a'), undefined);
  assert.equal(history.redo('a'), 'b');
  assert.equal(history.redo('b'), 'c');
  history.undo('c'); history.checkpoint('b'); assert.equal(history.canRedo, false);
  history.clear(); assert.equal(history.canUndo, false);
});

test('selection follows the same events through a re-sort, including identical twins', () => {
  const before = [light(0, 0), capture(10, 'p'), capture(10, 'p'), light(20, 5)].map(eventSignature);
  const after = [light(0, 0), light(5, 9), capture(10, 'p'), capture(10, 'p'), light(20, 5)].map(eventSignature);
  assert.deepEqual([...remapSelection(before, new Set([2, 3]), after)].sort(), [3, 4]);
  assert.deepEqual([...remapSelection(before, new Set([1]), after)], [2]);
});

test('overlap rules: same slot only for same channel or two measurements', () => {
  const plan = basePlan();
  const moved = capture(200000, 'dark-reference');
  plan.events.push(moved);
  assert.equal(findCollision(plan, [moved]), moved);
  assert.equal(hasOverlap(plan), true);
  const other = { ...light(100250, 3), command: 'FR' };
  const clean = basePlan(); clean.events.push(other);
  assert.equal(findCollision(clean, [other]), null);
  assert.equal(isAnchored(clean.events[0], 400000), true);
  assert.equal(isAnchored(clean.events[2], 400000), false);
  assert.equal('repeat' in plainCopy({ ...light(1, 1), repeat: { id: 'r1', i: 0, k: 0 }, sequence: 3 }), false);
});

test('script round trip reproduces the plan exactly and keeps hidden fields', () => {
  const plan = basePlan();
  plan.events[1].label = 'Dark F0 / Fm';
  plan.events[2].vendor_field = { keep: true };
  const { events, blocks } = roundTrip(plan);
  assert.equal(scriptMatchesPlan(plan, events, blocks), true);
  assert.equal(events[2], plan.events[2], 'an unchanged line keeps its event object');
  assert.deepEqual(events[2].vendor_field, { keep: true });
});

test('an invalid script is rejected with its line and never produces events', () => {
  const plan = basePlan();
  const parse = text => { const parsed = parseScript(text, plan, { long: false }); checkParsedScript(parsed, parsed.duration ?? 400000, false); return parsed; };
  for (const [text, line, message] of [
    ['duration 400 s\n0 light 0\n100 light 500.5', 2, /whole number/],
    ['0 light 0\n10 measure nothing', 1, /Unknown protocol "nothing".*dark-reference/],
    ['0 light 0\n500 light 1', 1, /after the end/],
    ['0 light 0\n10 light 5\n10 light 6', 2, /Same time as line 2/],
    ['# just a note', 0, /after an event/],
    ['repeat 3 every 10 from 0\n  1 light 5', 0, /needs an "end"/],
    ['end', 0, /without a repeat/],
    ['duration 400 s', 0, /at least one event/],
  ]) assert.throws(() => parse(text), error => error.line === line && message.test(error.message), text);
});

test('"+", "abs", "every" and other channels parse as documented', () => {
  const plan = basePlan();
  const { items } = parseScript('0 light 0\n+10 light 5\n+2.5 measure light-adapted # note\nabs 60 set FR 12\nevery 5 from 100 to 110 set UVA 3', plan, { long: false });
  assert.deepEqual(items.map(item => item.delay_ms), [0, 10000, 12500, 60000, 100000, 105000, 110000]);
  assert.equal(items[2].label, 'note');
  assert.equal(items[3].relative, false);
  assert.equal(items[4].command, 'UVA');
});

test('repeat blocks persist through save and reopen (JSON) and through the script', () => {
  const plan = basePlan();
  const text = 'duration 400 s\n0 light 0\n400 light 0\n\nrepeat 3 every 100 from 50\n  10 light 200\n  20 measure light-adapted\nend';
  const parsed = parseScript(text, plan, { long: false });
  const { events, blocks } = eventsFromScript(plan, parsed);
  plan.events = events; plan.studio.repeats = blocks;
  assert.equal(plan.events.filter(event => event.repeat).length, 6);
  const reopened = JSON.parse(JSON.stringify(plan));                       // what Save stores and Open returns
  assert.deepEqual(blocksOf(reopened), blocks, 'nothing is lost in JSON');
  const again = roundTrip(reopened);
  assert.match(again.text, /repeat 3 every 100 from 50\n  10 +light 200\n  20 +measure light-adapted\nend/);
  assert.equal(scriptMatchesPlan(reopened, again.events, again.blocks), true);
});

const repeatingPlan = () => {
  const plan = basePlan();
  plan.studio.repeats = [{ id: 'r1', count: 3, period_ms: 100000, start_ms: 50000, lines: [{ offset_ms: 10000, kind: 'set', command: 'intensity', value: '200' }], skip: [] }];
  expandBlock(plan, plan.studio.repeats[0]);
  return plan;
};

test('Change all moves the block line and rebuilds every instance', () => {
  const base = repeatingPlan(), edited = structuredClone(base);
  const row = edited.events.find(event => event.repeat?.i === 1);
  row.delay_ms += 5000; row.value = '250';
  const keep = changeAllInstances(edited, [row], repeatDeltas(base, edited, [row]), 400000);
  assert.deepEqual(edited.events.filter(event => event.repeat).map(event => [event.delay_ms, event.value]), [[65000, '250'], [165000, '250'], [265000, '250']]);
  assert.equal(edited.studio.repeats[0].lines[0].offset_ms, 15000);
  assert.deepEqual(keep.map(event => event.repeat.i), [1], 'the edited instance stays selected');
  const out = structuredClone(base), far = out.events.find(event => event.repeat?.i === 2);
  far.delay_ms += 200000;
  assert.throws(() => changeAllInstances(out, [far], repeatDeltas(base, out, [far]), 400000), /outside the experiment/);
});

test('Only this detaches one instance and the block never regenerates it', () => {
  const base = repeatingPlan(), edited = structuredClone(base);
  const row = edited.events.find(event => event.repeat?.i === 1);
  row.delay_ms += 5000;
  detachInstances(edited, [row]);
  assert.equal(row.repeat, undefined);
  assert.deepEqual(edited.studio.repeats[0].skip, [[1, 0]]);
  expandBlock(edited, edited.studio.repeats[0]);
  assert.deepEqual(edited.events.filter(event => event.repeat).map(event => event.repeat.i), [0, 2]);
  assert.ok(edited.events.includes(row), 'the detached event is still in the plan');
  const again = roundTrip(edited);
  assert.equal(scriptMatchesPlan(edited, again.events, again.blocks), true, 'skip survives a script round trip');
  const deleted = repeatingPlan(), gone = deleted.events.find(event => event.repeat?.i === 0);
  skipInstances(deleted, [gone]);
  assert.deepEqual(deleted.studio.repeats[0].skip, [[0, 0]]);
});

test('presets refuse collisions and never redirect an event to a different protocol', () => {
  const plan = basePlan();
  const preset = { protocols: [protocol('light-adapted', '25'), protocol('background')], events: [light(0, 0), capture(30000, 'background'), capture(60000, 'light-adapted')], studio: { duration_ms: 90000 } };
  const rows = presetRows(plan, preset, 10000, true);
  assert.deepEqual(rows.map(event => event.protocol), [undefined, 'background', 'light-adapted-2']);
  assert.equal(plan.protocols.find(item => item.id === 'light-adapted').fields.FramesPerLoop, '10', 'the existing protocol is untouched');
  assert.equal(adoptProtocol(plan, protocol('light-adapted', '25')), 'light-adapted-2', 'an identical protocol is reused, not duplicated');
  const clash = basePlan();
  assert.throws(() => presetRows(clash, { ...preset, events: [capture(65430, 'background')] }, 10000, true), /overlaps an existing event/);
  assert.throws(() => presetRows(clash, { ...preset, events: [light(0, 0)] }, 0, true), /already in the plan/);
});

test('paste reuses protocols inside a draft and isolates them across drafts', () => {
  const plan = basePlan(), clip = makeClip(plan, [plan.events[3]], 1);
  const same = pasteRows(plan, clip, 250000, true, 1);
  assert.equal(same[0].protocol, 'light-adapted');
  assert.equal(plan.protocols.length, 2);
  const other = basePlan(); other.protocols[1] = protocol('light-adapted', '99');
  assert.equal(pasteRows(other, clip, 250000, true, 2)[0].protocol, 'light-adapted-2');
  assert.match(repeatTemplate(432000000, 0, true), /^repeat 5 every 1d from 00:00:00\n  06:00:00  light 200\n  18:00:00  light 0\nend$/);
});
