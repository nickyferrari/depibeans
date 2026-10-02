// Plan events: identity, boundaries, overlap rules and selection tracking.
// A plan is { events: [...], protocols: [...], studio: {...} }. Events carry
// delay_ms (whole ms), relative, kind 'set' | 'capture', and command/value or protocol.

export const isLight = event => event.kind === 'set' && event.command === 'intensity';

// The first and final light settings define the run boundaries; their time is fixed.
export const isAnchored = (event, endMs) =>
  isLight(event) && (event.delay_ms === 0 || event.delay_ms === endMs || !!event.studio_terminal);

// Everything that identifies an event except its position in the list.
export function eventSignature(event) {
  const { sequence, ...rest } = event;
  return JSON.stringify(rest);
}

// What the script shows of an event; equal keys mean "the same line".
export const eventKey = event =>
  [event.relative, event.delay_ms, event.kind, event.command ?? '', event.protocol ?? '', event.value ?? ''].join('|');

// Two events occupy the same slot when nothing could order them: same time base,
// same millisecond, and both measurements or both the same light channel.
export const sameSlot = (a, b) =>
  a.relative === b.relative && a.delay_ms === b.delay_ms && a.kind === b.kind && (a.kind === 'capture' || a.command === b.command);

// First of `rows` that lands on an event outside `rows`, or null.
export function findCollision(plan, rows) {
  const mine = new Set(rows);
  for (const row of rows) if (plan.events.some(event => !mine.has(event) && sameSlot(event, row))) return row;
  return null;
}

// True when any two events anywhere in the plan share a slot.
export function hasOverlap(plan) {
  const seen = new Set();
  for (const event of plan.events) {
    const slot = JSON.stringify([event.relative, event.delay_ms, event.kind, event.kind === 'capture' ? '' : event.command || '']);
    if (seen.has(slot)) return true;
    seen.add(slot);
  }
  return false;
}

// A copy that is an ordinary event: no list position, not the run's final
// setting, not a member of a repeat.
export function plainCopy(event) {
  const copy = structuredClone(event);
  delete copy.sequence;
  delete copy.studio_terminal;
  delete copy.repeat;
  return copy;
}

// Selection is kept as indices into plan.events. When the draft changes outside
// the editor (a host button, the JSON box, a re-sort) the same events are found
// again by signature; among identical events the n-th stays the n-th.
export function remapSelection(previousSignatures, chosen, signatures) {
  const next = new Set();
  for (const index of chosen) {
    const signature = previousSignatures[index];
    if (signature === undefined) continue;
    let nth = 0;
    for (let k = 0; k < index; k++) if (previousSignatures[k] === signature) nth++;
    for (let k = 0; k < signatures.length; k++) {
      if (signatures[k] === signature && !next.has(k) && nth-- <= 0) { next.add(k); break; }
    }
  }
  return next;
}
