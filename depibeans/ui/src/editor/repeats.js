// Repeat blocks. A block is stored with the draft in plan.studio.repeats:
//   { id, count, period_ms, start_ms, lines: [{ offset_ms, kind, ... }], skip: [[i, k], ...] }
// Every generated event is a real, executable event tagged repeat: { id, i, k }
// (block, iteration, line). `skip` lists instances that were deleted or detached,
// so regenerating the block does not bring them back.
import { LIGHT_MAX } from './constants.js';
import { isLight } from './plan.js';

const clampNumber = (value, low, high) => Math.max(low, Math.min(high, value));

export const blocksOf = plan => Array.isArray(plan.studio?.repeats) ? plan.studio.repeats : [];

export const blockOf = (plan, event) => event.repeat ? blocksOf(plan).find(block => block.id === event.repeat.id) || null : null;

export const isSkipped = (block, i, k) => (block.skip || []).some(entry => entry[0] === i && entry[1] === k);

// One canonical shape for a stored block, so two descriptions of the same repeat
// compare equal whatever order their fields were written in.
export function normalizeBlock(block) {
  const lines = block.lines.map(line => {
    const out = { offset_ms: line.offset_ms, kind: line.kind };
    for (const field of ['command', 'value', 'protocol', 'label']) if (line[field] !== undefined && line[field] !== '') out[field] = line[field];
    return out;
  });
  return { id: block.id, count: block.count, period_ms: block.period_ms, start_ms: block.start_ms, lines, skip: (block.skip || []).map(entry => [entry[0], entry[1]]) };
}

export function makeInstance(block, i, k) {
  const line = block.lines[k];
  const event = { kind: line.kind, delay_ms: block.start_ms + i * block.period_ms + line.offset_ms, relative: true };
  if (line.kind === 'set') { event.command = line.command; event.value = line.value; }
  else event.protocol = line.protocol;
  if (line.label) event.label = line.label;
  event.repeat = { id: block.id, i, k };
  return event;
}

// Replaces every instance of `block` in the plan. Returns the new instances.
export function expandBlock(plan, block) {
  plan.events = plan.events.filter(event => event.repeat?.id !== block.id);
  const made = [];
  for (let i = 0; i < block.count; i++)
    for (let k = 0; k < block.lines.length; k++)
      if (!isSkipped(block, i, k)) made.push(makeInstance(block, i, k));
  plan.events.push(...made);
  return made;
}

// Identifies a selection of repeat instances, so one answer to "Change all / Only
// this" can carry across a run of keyboard nudges on the same events.
export const repeatSelectionKey = rows =>
  rows.filter(event => event.repeat).map(event => [event.repeat.id, event.repeat.i, event.repeat.k].join(':')).sort().join();

// What changed on each edited repeat instance, relative to the saved draft.
export function repeatDeltas(basePlan, editedPlan, rows) {
  const deltas = [];
  for (const event of rows) {
    if (!blockOf(editedPlan, event)) continue;
    const { id, i, k } = event.repeat;
    const was = basePlan.events.find(old => old.repeat && old.repeat.id === id && old.repeat.i === i && old.repeat.k === k);
    if (!was) continue;
    deltas.push({ id, i, k, dt: event.delay_ms - was.delay_ms, dv: isLight(event) ? Number(event.value) - Number(was.value) : 0 });
  }
  return deltas;
}

// "Only this": the edited instances leave their block and become ordinary events.
export function detachInstances(plan, rows) {
  for (const event of rows) {
    const block = blockOf(plan, event);
    if (!block) continue;
    (block.skip = block.skip || []).push([event.repeat.i, event.repeat.k]);
    delete event.repeat;
  }
  return rows;
}

// Deleting an instance removes it from that iteration only.
export function skipInstances(plan, rows) {
  for (const event of rows) {
    const block = blockOf(plan, event);
    if (block) (block.skip = block.skip || []).push([event.repeat.i, event.repeat.k]);
  }
}

// "Change all": the change moves to the block's line and every instance is rebuilt.
// Returns the events to keep selected. Throws if any instance leaves the experiment.
export function changeAllInstances(plan, rows, deltas, endMs) {
  const touched = new Map();
  const keep = rows.filter(event => !blockOf(plan, event));
  const wanted = [];
  for (const delta of deltas) {
    const block = blocksOf(plan).find(candidate => candidate.id === delta.id);
    if (!block) continue;
    wanted.push(delta);
    const mark = delta.id + ':' + delta.k;
    if (touched.has(mark)) continue;       // one line, one change, however many instances were dragged
    touched.set(mark, block);
    const line = block.lines[delta.k];
    line.offset_ms += delta.dt;
    if (line.kind === 'set' && line.command === 'intensity' && delta.dv) line.value = String(clampNumber(+line.value + delta.dv, 0, LIGHT_MAX));
  }
  for (const block of new Set(touched.values())) {
    const made = expandBlock(plan, block);
    if (made.some(event => event.delay_ms < 0 || event.delay_ms > endMs)) throw Error('That moves part of the repeat outside the experiment.');
    for (const delta of wanted) {
      if (delta.id !== block.id) continue;
      const again = made.find(event => event.repeat.i === delta.i && event.repeat.k === delta.k);
      if (again) keep.push(again);
    }
  }
  return keep;
}
