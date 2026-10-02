// Limits shared by the graph, the script and the tests.
export const GRID_MS = 100;            // timeline editing step: 0.1 s
export const LIGHT_MAX = 500;          // main light, controller units (whole numbers)
export const CHANNEL_MAX = 65535;      // FR / UVA / UVB raw channel range
export const DAY_MS = 86400000;
export const MIN_SPAN_MS = 2000;       // closest zoom
export const HISTORY_LIMIT = 100;
export const MAX_EVENTS = 10000;       // controller limit per plan
export const LONG_PLAN_MS = 600000;    // from here on, times read as h:mm:ss
export const UNIT_MS = { s: 1000, min: 60000, h: 3600000, d: DAY_MS };
