// Drawing. Turns a draft and a view into SVG; holds no editor state and changes no plan.
import { DAY_MS, LIGHT_MAX } from './constants.js';
import { signedSeconds, tickLabel, timeLabel } from './time.js';
import { isLight } from './plan.js';

const TICK_STEPS = [100, 200, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000, 600000, 900000, 1800000,
  3600000, 7200000, 10800000, 21600000, 43200000, DAY_MS, 2 * DAY_MS, 5 * DAY_MS, 10 * DAY_MS, 30 * DAY_MS, 60 * DAY_MS];
const LEVEL_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2500, 5000, 10000, 20000];

// The SVG uses one unit per CSS pixel, so text and points keep their size at any width.
export function measureChart(chart) {
  const box = chart.getBoundingClientRect();
  const W = Math.max(480, Math.round(box.width) || 1000);
  const H = Math.max(240, Math.round(box.height) || 300);
  chart.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const left = 52, right = W - 18, top = 18, axis = H - 26, laneH = 30, lane = axis - laneH, bottom = lane - 14;
  return { W, H, left, right, top, bottom, lane, laneH, axis, width: right - left };
}

export const tickStep = (spanMs, widthPx) => {
  const want = spanMs / Math.max(2, widthPx / 96);
  return TICK_STEPS.find(step => step >= want) || TICK_STEPS.at(-1);
};

export const lightCeiling = (plan, configured) =>
  Math.max(1, Number(configured) || LIGHT_MAX, ...plan.events.filter(isLight).map(event => Number(event.value)));

// Position of an event in chart pixels; shared by drawing and box selection.
export function eventPosition(event, geometry, view, yMax) {
  return {
    x: geometry.left + (event.delay_ms - view.start) / view.span * geometry.width,
    y: isLight(event) ? geometry.bottom - Number(event.value) / yMax * (geometry.bottom - geometry.top) : geometry.lane + geometry.laneH / 2,
  };
}

// model: { plan, view:{start,span}, endMs, long, yMax, geometry, eligible(event),
//          selection:Set<event>, cursor:number|null, box:{x,y,w,h}|null }
export function drawChart(chart, svg, model) {
  const { plan, view, endMs, long, yMax, geometry: g, selection } = model;
  const x = ms => g.left + (ms - view.start) / view.span * g.width;
  const y = level => g.bottom - Number(level) / yMax * (g.bottom - g.top);
  const inView = ms => ms >= view.start && ms <= view.start + view.span;
  const indexOf = new Map(plan.events.map((event, index) => [event, index]));

  chart.replaceChildren();
  const clip = svg(svg(chart, 'defs'), 'clipPath', { id: 'ge-plot' });
  svg(clip, 'rect', { x: g.left, y: 0, width: g.width, height: g.H });

  const step = tickStep(view.span, g.width);
  for (let ms = Math.ceil(view.start / step) * step; ms <= view.start + view.span + 1e-6; ms += step) {
    const at = x(ms);
    svg(chart, 'line', { x1: at, x2: at, y1: g.top, y2: g.axis, class: 'ge-grid' });
    svg(chart, 'text', { x: at, y: g.axis + 17, 'text-anchor': at > g.right - 30 ? 'end' : at < g.left + 30 ? 'start' : 'middle', class: 'ge-tick' }, tickLabel(ms, step, long));
  }
  const levelStep = LEVEL_STEPS.find(candidate => yMax / candidate <= 5) || LEVEL_STEPS.at(-1);
  for (let level = 0; level <= yMax; level += levelStep) {
    svg(chart, 'line', { x1: g.left, x2: g.right, y1: y(level), y2: y(level), class: 'ge-grid' });
    svg(chart, 'text', { x: g.left - 8, y: y(level) + 4, 'text-anchor': 'end', class: 'ge-tick' }, String(level));
  }
  svg(chart, 'line', { x1: g.left, x2: g.right, y1: g.lane + g.laneH / 2, y2: g.lane + g.laneH / 2, class: 'ge-lane' });
  svg(chart, 'line', { x1: g.left, x2: g.right, y1: g.axis, y2: g.axis, class: 'ge-axis' });
  if (inView(endMs)) svg(chart, 'line', { x1: x(endMs), x2: x(endMs), y1: g.top, y2: g.axis, class: 'ge-end' });

  // The light trace is a step function: the level holds until the next setting.
  const rows = plan.events.filter(model.eligible);
  const lights = rows.filter(isLight).sort((a, b) => a.delay_ms - b.delay_ms);
  let level = 0;
  for (const event of lights) if (event.delay_ms <= view.start) level = event.value;
  let path = `M${g.left} ${y(level)}`;
  for (const event of lights) if (event.delay_ms > view.start && event.delay_ms <= view.start + view.span) path += ` H${x(event.delay_ms)} V${y(event.value)}`;
  path += ` H${Math.min(g.right, x(endMs))}`;
  svg(chart, 'path', { d: path, class: 'ge-trace', 'clip-path': 'url(#ge-plot)' });

  for (const event of rows) {
    if (!inView(event.delay_ms)) continue;
    const capture = event.kind === 'capture', on = selection.has(event), cx = x(event.delay_ms);
    const node = capture
      ? svg(chart, 'rect', { x: cx - 5, y: g.lane + 3, width: 10, height: g.laneH - 6, rx: 2 })
      : svg(chart, 'circle', { cx, cy: y(event.value), r: on ? 6 : 5 });
    node.setAttribute('class', 'ge-point ' + (capture ? 'ge-capture' : 'ge-light') + (on ? ' ge-on' : ''));
    node.dataset.event = indexOf.get(event);
    svg(node, 'title').textContent = (capture ? event.protocol : event.value) + ' · ' + timeLabel(event.delay_ms, long);
  }

  if (model.cursor !== null && inView(model.cursor)) {
    const cx = x(model.cursor);
    svg(chart, 'line', { x1: cx, x2: cx, y1: g.top, y2: g.axis, class: 'ge-cursor' });
    svg(chart, 'path', { d: `M${cx - 4} ${g.top - 7}h8l-4 6z`, class: 'ge-cursor-head' });
  }
  if (model.box) svg(chart, 'rect', { x: model.box.x, y: model.box.y, width: model.box.w, height: model.box.h, class: 'ge-box' });
}

// The one-line readout above the chart: the gesture in progress, or the selection.
export function readoutText(selection, gesture, long) {
  if (gesture?.type === 'move' && gesture.moved) {
    const parts = [];
    if (gesture.dt) parts.push('Δt ' + signedSeconds(gesture.dt));
    if (gesture.dv) parts.push('Δ level ' + (gesture.dv > 0 ? '+' : '−') + Math.abs(gesture.dv));
    if (gesture.copying) parts.push('copy');
    return parts.join(' · ');
  }
  if (selection.size === 1) {
    const event = [...selection][0];
    return (event.kind === 'capture' ? event.protocol : 'level ' + event.value) + ' · ' + timeLabel(event.delay_ms, long);
  }
  if (selection.size > 1) {
    const times = [...selection].map(event => event.delay_ms);
    return `${selection.size} selected · ${timeLabel(Math.min(...times), long)} – ${timeLabel(Math.max(...times), long)}`;
  }
  return '';
}
