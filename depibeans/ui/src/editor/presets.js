// Presets and the clipboard add ordinary events to the one shared draft. Both must
// keep measurement protocols straight: reuse a protocol the plan already has, and
// never silently point an event at a different protocol of the same name.
import { DAY_MS, GRID_MS, LIGHT_MAX } from './constants.js';
import { exactTime, periodText } from './time.js';
import { plainCopy, sameSlot } from './plan.js';

export const PRESET_DEFAULTS = {
  darkMinutes: 0, intensity: Math.min(LIGHT_MAX, 500), frames: 10, exposure: 50, interval: 100,
  lightMinutes: 5, count: 5, recoveryMinutes: 2, levels: '50,100,200,400', dwellMinutes: 2,
};

export const PRESET_CHOICES = [
  ['npq', 'NPQ induction and recovery'],
  ['response', 'Light response steps'],
  ['dark', 'Dark yield · F₀ / Fm'],
  ['repeat', 'Repeat block'],
];

// Returns the name under which `protocol` is available in the plan, adding it if
// needed. The same definition is never stored twice: an identical protocol is reused
// whatever its name. A different protocol under the same name gets a numbered name.
export function adoptProtocol(plan, protocol) {
  const definition = candidate => JSON.stringify({ ...candidate, id: null });
  const wanted = definition(protocol);
  const numbered = new RegExp('^' + protocol.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(-\\d+)?$');
  const same = plan.protocols.find(candidate => numbered.test(candidate.id) && definition(candidate) === wanted);
  if (same) return same.id;
  let id = protocol.id;
  for (let n = 2; plan.protocols.some(candidate => candidate.id === id); n++) id = protocol.id + '-' + n;
  plan.protocols.push({ ...structuredClone(protocol), id });
  return id;
}

// Events of a generated preset plan, shifted to start at `atMs`. An identical light
// setting already at that slot is left alone; anything else at an occupied slot is
// refused, so a preset never stacks a second measurement or a conflicting level.
// Adds the protocols the rows need to `plan`. Does not add the rows.
export function presetRows(plan, preset, atMs, relative) {
  const names = new Map();
  for (const protocol of preset.protocols) names.set(protocol.id, adoptProtocol(plan, protocol));
  const rows = [];
  for (const source of preset.events) {
    const event = structuredClone(source);
    delete event.sequence;
    if (event.protocol) event.protocol = names.get(event.protocol) || event.protocol;
    event.delay_ms += atMs;
    event.relative = relative;
    const occupied = plan.events.find(other => sameSlot(other, event));
    if (occupied) {
      if (event.kind === 'capture' || JSON.stringify(occupied.value) !== JSON.stringify(event.value)) throw Error('Preset overlaps an existing event. Choose another time.');
      continue;
    }
    rows.push(event);
  }
  if (!rows.length) throw Error('Those events are already in the plan at this time.');
  return rows;
}

// Starter text for a repeat block: daily on plans of a day or more, otherwise a
// quarter of the plan, switching the light at 25 % and 75 % of each period.
export function repeatTemplate(totalMs, atMs, long) {
  const period = totalMs >= DAY_MS ? DAY_MS : Math.max(1000, Math.floor(totalMs / 4 / 1000) * 1000);
  const count = Math.max(1, Math.floor((totalMs - atMs) / period));
  const at = fraction => exactTime(Math.round(period * fraction / GRID_MS) * GRID_MS, long);
  return `repeat ${count} every ${periodText(period, long)} from ${exactTime(atMs, long)}\n  ${at(.25)}  light 200\n  ${at(.75)}  light 0\nend`;
}

// Clipboard: the selected events relative to their first, with the protocols they use.
// `draft` identifies the draft they were copied from.
export function makeClip(plan, rows, draft) {
  const start = Math.min(...rows.map(event => event.delay_ms));
  const used = new Set(rows.map(event => event.protocol).filter(Boolean));
  return {
    draft,
    events: structuredClone(rows).map(event => ({ ...event, delay_ms: event.delay_ms - start })),
    protocols: structuredClone(plan.protocols.filter(protocol => used.has(protocol.id))),
    span: Math.max(...rows.map(event => event.delay_ms)) - start,
  };
}

// Pasted events placed at `atMs`. Within the draft they were copied from, a pasted
// measurement keeps its protocol reference. In another draft the protocol is added
// when missing, or added under a numbered name when that draft defines it differently.
export function pasteRows(plan, clip, atMs, relative, draft) {
  const names = new Map();
  const nameFor = id => {
    if (names.has(id)) return names.get(id);
    const source = clip.protocols.find(protocol => protocol.id === id);
    const present = plan.protocols.find(protocol => protocol.id === id);
    let use = id;
    if (!present) {
      if (!source) throw Error('Measurement protocol is unavailable.');
      plan.protocols.push(structuredClone(source));
    } else if (clip.draft !== draft && source && JSON.stringify(source) !== JSON.stringify(present)) {
      use = adoptProtocol(plan, source);
    }
    names.set(id, use);
    return use;
  };
  return clip.events.map(source => {
    const event = plainCopy(source);
    event.delay_ms = atMs + source.delay_ms;
    event.relative = relative;
    if (event.kind === 'capture') event.protocol = nameFor(event.protocol);
    return event;
  });
}
