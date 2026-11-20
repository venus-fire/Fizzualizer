// Fizzualizer settings for the web build.
//
// Mirrors config.py for the knobs the browser port actually reads. The web
// build keeps its own copy on purpose: config.py is Python that the desktop
// app execs, and it also carries desktop-only knobs (window size, FPS, MPRIS
// volume steps) that have no meaning here. When a shared knob changes, change
// it in both files and say so in the commit.
//
// Defaults below are the shipped values from config.py.

export const DEFAULTS = {
  // Audio analysis
  FFT_SIZE: 2048,
  SAMPLE_RATE: 44100,
  SENSITIVITY: 30,
  ATTACK: 0.5,
  DECAY: 0.97,
  FREQ_MIN: 10,
  FREQ_MAX: 15000,
  NUM_ITEMS: 45,
  PEAK_DECAY: 0.993,

  // Common normalizer
  GLOBAL_FLOOR: 0.53,
  GLOBAL_RANGE_DB: 12.0,
  GLOBAL_REF_FALL: 0.2,
  GLOBAL_ATTACK: 0.35,
  GLOBAL_RELEASE: 0.06,

  // Balls
  MIN_BALL_SIZE: 0,
  MAX_BALL_SIZE: 230,
  MAX_COLLIDER_SIZE: 390,
  SPACING_X: 30,
  SPACING_Y: 6,
  SPRING_BACK: 0.255,
  COLLIDE_PUSH: 0.14,
  STEREO_SHIFT: 120,
  PAN_SMOOTH: 0.01,

  // Colour
  HUE_START: 240,
  HUE_END: 350,
  SAT_ZERO: 0.75,
  SAT_MIN: 0.69,
  SAT_MAX: 1,
  VAL_ZERO: 0.75,
  VAL_MIN: 0.52,
  VAL_MAX: 1,

  // The rate the per-frame constants were written for. The loop scales them by
  // real frame time, so the frame rate does not change how the motion feels.
  REFERENCE_FPS: 43,
};

// Sliders, in panel order. Every entry is a key in DEFAULTS plus a range.
export const SLIDERS = [
  { key: 'SENSITIVITY', label: 'Sensitivity', min: 0, max: 100, step: 1 },
  { key: 'ATTACK', label: 'Attack', min: 0.01, max: 1, step: 0.01 },
  { key: 'DECAY', label: 'Decay', min: 0.5, max: 0.999, step: 0.001 },
  { key: 'PEAK_DECAY', label: 'Peak decay', min: 0.95, max: 0.999, step: 0.001 },
  { key: 'GLOBAL_FLOOR', label: 'Gate floor', min: 0, max: 1, step: 0.01 },
  { key: 'GLOBAL_RANGE_DB', label: 'Gate range dB', min: 1, max: 40, step: 0.5 },
  { key: 'MAX_BALL_SIZE', label: 'Ball size', min: 20, max: 600, step: 1 },
  { key: 'MAX_COLLIDER_SIZE', label: 'Collider', min: 20, max: 900, step: 1 },
  { key: 'SPACING_X', label: 'Spacing X', min: 4, max: 120, step: 1 },
  { key: 'SPACING_Y', label: 'Spacing Y', min: 0, max: 40, step: 1 },
  { key: 'STEREO_SHIFT', label: 'Stereo shift', min: 0, max: 400, step: 1 },
  { key: 'SPRING_BACK', label: 'Spring back', min: 0.01, max: 1, step: 0.01 },
  { key: 'COLLIDE_PUSH', label: 'Collide push', min: 0.01, max: 1, step: 0.01 },
];

const STORE_KEY = 'fizzualizer.web.config.v1';

// Overrides are stored as a sparse set, so a later change to a default here
// still reaches anyone who only ever moved one slider.
export function loadConfig() {
  const live = { ...DEFAULTS };
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');
    for (const k of Object.keys(DEFAULTS)) {
      if (typeof saved[k] === 'number' && Number.isFinite(saved[k])) live[k] = saved[k];
    }
  } catch (e) {
    // Corrupt or blocked storage is not worth failing a launch over.
  }
  return live;
}

export function saveConfig(live) {
  const sparse = {};
  for (const k of Object.keys(DEFAULTS)) {
    if (live[k] !== DEFAULTS[k]) sparse[k] = live[k];
  }
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(sparse));
  } catch (e) {}
}

export function resetConfig(live) {
  Object.assign(live, DEFAULTS);
  try {
    localStorage.removeItem(STORE_KEY);
  } catch (e) {}
  return live;
}
