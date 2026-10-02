// Time text. Plans store whole milliseconds; nothing here rounds a stored time.
// `long` selects clock notation (h:mm:ss, optional "2d " prefix) for plans of
// ten minutes or more; shorter plans read in seconds.
import { DAY_MS, LONG_PLAN_MS, UNIT_MS } from './constants.js';

export const isLongPlan = totalMs => totalMs >= LONG_PLAN_MS;

// Fixed decimals without trailing zeros: trimNumber(1.50, 3) -> "1.5".
export const trimNumber = (value, decimals) => String(Number(value.toFixed(decimals)));

const pad2 = value => String(value).padStart(2, '0');

// Exact time, to the millisecond, as the script and inspector show it.
export function exactTime(ms, long) {
  if (!long) return trimNumber(ms / 1000, 3);
  const days = Math.floor(ms / DAY_MS);
  const hours = Math.floor(ms % DAY_MS / 3600000);
  const minutes = Math.floor(ms % 3600000 / 60000);
  const [whole, part] = trimNumber(ms % 60000 / 1000, 3).split('.');
  return (days ? days + 'd ' : '') + pad2(hours) + ':' + pad2(minutes) + ':' + whole.padStart(2, '0') + (part ? '.' + part : '');
}

// Exact time with its unit, for messages and tooltips.
export const timeLabel = (ms, long) => long ? exactTime(ms, long) : exactTime(ms, long) + ' s';

// Axis tick text at a given tick spacing.
export function tickLabel(ms, stepMs, long) {
  if (!long) return trimNumber(ms / 1000, stepMs < 1000 ? 1 : 0) + ' s';
  if (stepMs >= DAY_MS) return 'day ' + (Math.floor(ms / DAY_MS) + 1);
  const days = Math.floor(ms / DAY_MS);
  let out = (days ? days + 'd ' : '') + pad2(Math.floor(ms % DAY_MS / 3600000)) + ':' + pad2(Math.floor(ms % 3600000 / 60000));
  if (stepMs < 60000) {
    const seconds = ms % 60000 / 1000;
    out += ':' + (stepMs < 1000 ? seconds.toFixed(1).padStart(4, '0') : pad2(Math.floor(seconds)));
  }
  return out;
}

// "12.5", "12.5 s", "0:02:05.5" or "1d 06:00:00" -> whole milliseconds.
export function parseTime(raw, long) {
  const value = String(raw).trim().replace(/\s*s$/, '');
  if (/^\d+(\.\d+)?$/.test(value)) return Math.round(Number(value) * 1000);
  const match = value.match(/^(?:(\d+)d\s*)?(\d+):(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/);
  if (!match) throw Error(long ? 'Enter time as h:mm:ss or seconds.' : 'Enter time in seconds.');
  return Math.round(((Number(match[1] || 0) * 24 + Number(match[2])) * 3600 + Number(match[3]) * 60 + Number(match[4])) * 1000);
}

// A time or a whole number of days ("5d"), used for periods and intervals.
export function parseSpan(token, long) {
  const days = String(token).match(/^(\d+)d$/i);
  return days ? Number(days[1]) * DAY_MS : parseTime(token, long);
}

export const signedSeconds = ms => (ms < 0 ? '−' : '+') + trimNumber(Math.abs(ms) / 1000, 3) + ' s';

// "duration" line: the largest unit that divides the duration exactly.
export function durationText(ms) {
  for (const unit of ['d', 'h', 'min']) if (ms % UNIT_MS[unit] === 0) return ms / UNIT_MS[unit] + ' ' + unit;
  return trimNumber(ms / 1000, 3) + ' s';
}

// Repeat period: whole days as "2d", otherwise an exact time.
export const periodText = (ms, long) => ms % DAY_MS === 0 ? ms / DAY_MS + 'd' : exactTime(ms, long);
