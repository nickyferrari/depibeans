// The script: the draft's events as text, edited in step with the graph.
//
//   duration 400 s
//   <time> light <level>              main light, whole number 0–500
//   <time> measure <protocol>         a protocol already in the plan
//   <time> set <FR|UVA|UVB> <value>   other channels
//   ... # note                        kept as the event's label
//   +<time> ...                       after the previous line
//   abs <time> ...                    calendar-based event
//   every <interval> from <time> to <time> <action>       expands into plain events
//   repeat <count> every <period> [from <time>] ... end   stays a block
//
// Parsing never touches the plan. A script that does not parse or validate leaves
// the last valid draft exactly as it was.
import { CHANNEL_MAX, DAY_MS, GRID_MS, LIGHT_MAX, MAX_EVENTS, UNIT_MS } from './constants.js';
import { durationText, exactTime, parseSpan, periodText, timeLabel } from './time.js';
import { eventKey, eventSignature, isLight } from './plan.js';
import { blockOf, blocksOf, isSkipped, normalizeBlock } from './repeats.js';

const TIME = '(?:\\d+d\\s+)?\\d+:\\d{1,2}:\\d{1,2}(?:\\.\\d+)?|\\d+d|\\d+(?:\\.\\d+)?';
const EVERY = new RegExp(`^every\\s+(${TIME})\\s+from\\s+(${TIME})\\s+to\\s+(${TIME})\\s+(.+)$`, 'i');
const EVENT = new RegExp(`^(abs\\s+)?(\\+)?(${TIME})\\s+(.+)$`, 'i');
const REPEAT = new RegExp(`^repeat\\s+(\\d+)\\s+every\\s+(${TIME})(?:\\s+from\\s+(${TIME}))?\\s*:?$`, 'i');
const DURATION = /^duration\s+(\d+(?:\.\d+)?)\s*(s|min|h|d)$/i;

// An error that belongs to one line of the script (zero-based).
export function scriptError(line, message) {
  const error = Error(message);
  error.line = line;
  return error;
}

const actionText = item => isLight(item) ? 'light ' + item.value : item.kind === 'set' ? `set ${item.command} ${item.value}` : 'measure ' + item.protocol;
const noteText = item => item.label ? '  # ' + String(item.label).replace(/\s+/g, ' ') : '';

// Plan -> text. Also returns, per line, the indices of the events that line stands
// for: one for a plain line, every instance for a line inside a repeat.
export function composeScript(plan, { totalMs, long }) {
  const blocks = blocksOf(plan).filter(block => plan.events.some(event => event.repeat?.id === block.id));
  const plain = plan.events.map((event, index) => ({ event, index })).filter(({ event }) => !blocks.includes(blockOf(plan, event)));
  const times = plain.map(({ event }) => (event.relative ? '' : 'abs ') + exactTime(event.delay_ms, long));
  const width = Math.max(8, ...times.map(text => text.length)) + 2;
  const lines = ['duration ' + durationText(totalMs)];
  const lineEvents = [[]];
  plain.forEach(({ event, index }, n) => {
    lines.push(times[n].padEnd(width) + actionText(event) + noteText(event));
    lineEvents.push([index]);
  });
  for (const block of blocks) {
    lines.push('');
    lineEvents.push([]);
    lines.push(`repeat ${block.count} every ${periodText(block.period_ms, long)} from ${exactTime(block.start_ms, long)}`);
    lineEvents.push([]);
    const offsets = block.lines.map(line => exactTime(line.offset_ms, long));
    const offsetWidth = Math.max(8, ...offsets.map(text => text.length)) + 2;
    block.lines.forEach((line, k) => {
      lines.push('  ' + offsets[k].padEnd(offsetWidth) + actionText(line) + noteText(line));
      lineEvents.push(plan.events.map((event, index) => event.repeat && event.repeat.id === block.id && event.repeat.k === k ? index : -1).filter(index => index >= 0));
    });
    lines.push('end');
    lineEvents.push([]);
  }
  return { text: lines.join('\n'), lineEvents };
}

function parseAction(rest, line, protocols) {
  let label;
  const hash = rest.indexOf('#');
  if (hash >= 0) { label = rest.slice(hash + 1).trim(); rest = rest.slice(0, hash); }
  rest = rest.trim();
  let match;
  if ((match = rest.match(/^light\s+(\S+)$/i)) || (match = rest.match(/^set\s+intensity\s+(\S+)$/i))) {
    const level = Number(match[1]);
    if (!Number.isInteger(level) || level < 0 || level > LIGHT_MAX) throw scriptError(line, `Light level is a whole number 0–${LIGHT_MAX}.`);
    return { kind: 'set', command: 'intensity', value: String(level), label };
  }
  if ((match = rest.match(/^set\s+(FR|UVA|UVB)\s+(\S+)$/i))) {
    const value = Number(match[2]);
    if (!Number.isFinite(value) || value < 0 || value > CHANNEL_MAX) throw scriptError(line, `Channel value must be 0–${CHANNEL_MAX}.`);
    return { kind: 'set', command: match[1].toUpperCase(), value: String(value), label };
  }
  if ((match = rest.match(/^measure\s+(.+)$/i))) {
    const id = match[1].trim();
    if (!protocols.includes(id)) throw scriptError(line, `Unknown protocol "${id}". Available: ${protocols.join(', ') || 'none'}.`);
    return { kind: 'capture', protocol: id, label };
  }
  throw scriptError(line, 'Expected  light <level>,  measure <protocol>  or  set <channel> <value>.');
}

// Text -> { duration, items, blocks }. `items` are the events the text describes,
// each with the line it came from; repeat blocks are already expanded into items.
// `plan` supplies the protocol names and the existing blocks' skipped instances.
export function parseScript(source, plan, { long }) {
  const protocols = plan.protocols.map(protocol => protocol.id);
  const items = [];
  const blocks = [];
  let duration = null;
  let previous = 0;
  let open = null;
  const timeOf = (token, line) => { try { return parseSpan(token, long); } catch (error) { throw scriptError(line, error.message); } };

  source.split('\n').forEach((raw, line) => {
    const text = raw.trim();
    let match;
    if (!text) return;
    if (text.startsWith('#')) throw scriptError(line, 'Put a note after an event:  100 light 500  # note');
    if (/^end$/i.test(text)) {
      if (!open) throw scriptError(line, '"end" without a repeat.');
      if (!open.lines.length) throw scriptError(open.line, 'The repeat is empty.');
      blocks.push(open);
      open = null;
      return;
    }
    if ((match = text.match(REPEAT))) {
      if (open) throw scriptError(line, 'Finish the previous repeat with "end" first.');
      const count = Number(match[1]), period = timeOf(match[2], line), start = match[3] ? timeOf(match[3], line) : 0;
      if (count < 1 || count > 1000) throw scriptError(line, 'Repeat 1–1000 times.');
      if (period < GRID_MS) throw scriptError(line, 'The period is too short.');
      open = { line, count, period_ms: period, start_ms: start, lines: [] };
      previous = 0;
      return;
    }
    if (/^repeat\b/i.test(text)) throw scriptError(line, 'Write  repeat 5 every 1d from 0  then the events, then  end');
    if ((match = text.match(DURATION))) {
      if (open) throw scriptError(line, 'Set the duration outside the repeat.');
      duration = Math.round(Number(match[1]) * UNIT_MS[match[2].toLowerCase()]);
      if (duration < 1000 || duration > 366 * DAY_MS) throw scriptError(line, 'Duration must be 1 second to 366 days.');
      return;
    }
    if (/^duration\b/i.test(text)) throw scriptError(line, 'Write the duration as  duration 400 s  (s, min, h or d).');
    if ((match = text.match(EVERY))) {
      if (open) throw scriptError(line, 'Use plain lines inside a repeat.');
      const step = timeOf(match[1], line), from = timeOf(match[2], line), to = timeOf(match[3], line), action = parseAction(match[4], line, protocols);
      if (step < 1) throw scriptError(line, 'The interval must be greater than zero.');
      if (to < from) throw scriptError(line, '"to" must not be earlier than "from".');
      if ((to - from) / step > MAX_EVENTS) throw scriptError(line, 'More than 10,000 events. Use a longer interval.');
      for (let t = from; t <= to; t += step) items.push({ ...action, delay_ms: t, relative: true, line });
      previous = items.at(-1).delay_ms;
      return;
    }
    if (!(match = text.match(EVENT))) throw scriptError(line, 'Start each line with a time:  120.5 light 300');
    let time = timeOf(match[3], line);
    if (match[2]) time += previous;
    previous = time;
    if (open) {
      if (match[1]) throw scriptError(line, 'Repeats use elapsed time.');
      open.lines.push({ ...parseAction(match[4], line, protocols), offset_ms: time, line });
      return;
    }
    items.push({ ...parseAction(match[4], line, protocols), delay_ms: time, relative: !match[1], line });
  });
  if (open) throw scriptError(open.line, 'This repeat needs an "end" line.');

  // Blocks are identified by their order in the text. A block keeps its skipped
  // instances while it still has the same number of lines.
  const existing = blocksOf(plan);
  blocks.forEach((block, n) => {
    block.id = 'r' + (n + 1);
    const prior = existing[n];
    block.skip = prior && prior.lines.length === block.lines.length ? (prior.skip || []).filter(entry => entry[0] < block.count) : [];
    if (block.count * block.lines.length > MAX_EVENTS) throw scriptError(block.line, 'More than 10,000 events in this repeat.');
    for (let i = 0; i < block.count; i++) {
      block.lines.forEach((line, k) => {
        if (isSkipped(block, i, k)) return;
        items.push({ kind: line.kind, command: line.command, value: line.value, protocol: line.protocol, label: line.label,
          delay_ms: block.start_ms + i * block.period_ms + line.offset_ms, relative: true, line: line.line, repeat: { id: block.id, i, k } });
      });
    }
  });
  return { duration, items, blocks };
}

// Rules that need the whole script: inside the experiment, one event per slot, not empty.
export function checkParsedScript(parsed, endMs, long) {
  const seen = new Map();
  for (const item of parsed.items) {
    if (item.delay_ms > endMs) throw scriptError(item.line, `Time is after the end of the experiment (${timeLabel(endMs, long)}).`);
    const slot = [item.relative, item.delay_ms, item.kind, item.command ?? ''].join('|');
    if (seen.has(slot)) throw scriptError(item.line, `Same time as line ${seen.get(slot) + 1}.`);
    seen.set(slot, item.line);
  }
  if (!parsed.items.length) throw scriptError(0, 'Keep at least one event.');
}

// Parsed items -> event objects for the plan. A line that did not change keeps its
// existing event object, so fields the script does not show (anything the controller
// or another tool stored on the event) survive a script edit. Sets item.event.
export function eventsFromScript(plan, parsed) {
  const pool = new Map();
  for (const event of plan.events) {
    const key = eventKey(event);
    if (!pool.has(key)) pool.set(key, []);
    pool.get(key).push(event);
  }
  const events = parsed.items.map(item => {
    let event = pool.get(eventKey(item))?.shift();
    if (!event) {
      event = { kind: item.kind, delay_ms: item.delay_ms, relative: item.relative };
      if (item.kind === 'set') { event.command = item.command; event.value = item.value; }
      else event.protocol = item.protocol;
    }
    if (item.label) event.label = item.label; else delete event.label;
    if (item.repeat) event.repeat = item.repeat; else delete event.repeat;
    item.event = event;
    return event;
  });
  const blocks = parsed.blocks.map(normalizeBlock);
  return { events, blocks };
}

// True when the script describes exactly the draft it was read from.
export function scriptMatchesPlan(plan, events, blocks) {
  return events.length === plan.events.length
    && JSON.stringify(blocks.map(normalizeBlock)) === JSON.stringify(blocksOf(plan).map(normalizeBlock))
    && events.map(eventSignature).sort().join() === plan.events.map(eventSignature).sort().join();
}
