// Fizzualizer, web build: the render loop, input, and the settings panel.
//
// The per-frame constants in config.js were written for REFERENCE_FPS, so every
// frame computes scale = dt * REFERENCE_FPS and passes it down. That is what
// keeps the motion feeling the same at 60Hz, 120Hz and in a throttled tab.

import { DEFAULTS, SLIDERS, loadConfig, saveConfig, resetConfig } from './config.js';
import { BandAnalyser } from './dsp.js';
import { createBalls, collide, hueRamp } from './physics.js';
import { BallRenderer } from './renderer.js';
import { AudioInput } from './audio.js';

const canvas = document.getElementById('view');
const statusEl = document.getElementById('status');
const panel = document.getElementById('panel');
const hint = document.getElementById('hint');

const cfg = loadConfig();
const renderer = new BallRenderer(canvas);
const audio = new AudioInput(cfg);

// Every spatial constant in config.js is pixel-sized for a 1920x1080 window,
// which is what the desktop build always has. A browser window is often
// narrower, and the row is (NUM_ITEMS - 1) * SPACING_X wide before ball radii,
// so at 1280 wide the outer balls sat off-screen. One scale factor for the
// whole layout keeps the picture recognisable at any size: the settings stay in
// reference pixels and this is the only place that converts.
const REFERENCE_WIDTH = 1920;
const REFERENCE_HEIGHT = 1080;

function viewConfig(width, height) {
  const s = Math.min(Math.max(Math.min(width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT), 0.15), 1.6);
  return {
    ...cfg,
    MAX_BALL_SIZE: cfg.MAX_BALL_SIZE * s,
    MIN_BALL_SIZE: cfg.MIN_BALL_SIZE * s,
    MAX_COLLIDER_SIZE: cfg.MAX_COLLIDER_SIZE * s,
    SPACING_X: cfg.SPACING_X * s,
    SPACING_Y: cfg.SPACING_Y * s,
    STEREO_SHIFT: cfg.STEREO_SHIFT * s,
    VIEW_SCALE: s,
  };
}

let view = viewConfig(window.innerWidth, window.innerHeight);

let analyser = null;
let balls = null;
let hues = hueRamp(cfg);
let bands = new Float32Array(cfg.NUM_ITEMS);
let pan = new Float32Array(cfg.NUM_ITEMS);
let lastFrame = 0;
let lastText = '';
let gate = 1;

function layout() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  renderer.resize(w, h, dpr);
  view = viewConfig(w, h);
  balls = createBalls(view, w, h);
}

function setStatus(text) {
  if (text === lastText) return;
  lastText = text;
  statusEl.textContent = text;
  statusEl.title = text;
}

function ensureAnalyser() {
  // The analyser needs the context's real sample rate, and the context only
  // exists after a gesture, so it is built on first use rather than at load.
  audio.ensureContext();
  if (!analyser) analyser = new BandAnalyser(cfg, audio.ctx.sampleRate);
  return analyser;
}

function frame(now) {
  requestAnimationFrame(frame);
  const t = now / 1000;
  const dt = Math.min(Math.max(t - lastFrame, 1e-4), 0.1);
  lastFrame = t;
  const scale = dt * cfg.REFERENCE_FPS;

  if (audio.kind !== 'none' && analyser) {
    const { left, right, mono } = audio.read();
    const out = analyser.analyse(left, right, scale, mono);
    bands = out.bands;
    pan = out.pan;
    gate = out.gate;
  } else {
    // Nothing playing: hold the picture still rather than freezing the physics.
    bands.fill(0);
    pan.fill(0);
  }

  // Stereo moves the rest height, so the spring follows elastically instead of
  // teleporting the ball.
  for (let i = 0; i < balls.length; i++) {
    balls[i].oy = balls[i].baseY + pan[i] * view.STEREO_SHIFT;
  }

  const mid = cfg.NUM_ITEMS >> 1;
  collide(view, balls, bands, mid, -1, scale);
  collide(view, balls, bands, mid, 1, scale);

  renderer.draw(cfg.NUM_ITEMS, view, balls, bands, hues);

  if (audio.kind === 'none') {
    setStatus('no audio');
  } else {
    const pct = Math.round(gate * 100);
    setStatus(`${audio.label} · gate ${pct}%`);
  }
}

// ---------------------------------------------------------------- settings

function sliderRow(spec) {
  const wrap = document.createElement('div');
  wrap.className = 'row';
  const id = `sl-${spec.key}`;
  const label = document.createElement('label');
  label.htmlFor = id;
  label.textContent = spec.label;
  const out = document.createElement('output');
  const input = document.createElement('input');
  input.type = 'range';
  input.id = id;
  input.min = spec.min;
  input.max = spec.max;
  input.step = spec.step;
  input.value = cfg[spec.key];
  out.textContent = cfg[spec.key];

  input.addEventListener('input', () => {
    const v = parseFloat(input.value);
    cfg[spec.key] = v;
    out.textContent = spec.step < 0.01 ? v.toFixed(3) : v;
    afterChange(spec.key);
  });
  input.addEventListener('change', () => saveConfig(cfg));

  wrap.append(label, out, input);
  return wrap;
}

function afterChange(key) {
  if (key === 'SPACING_X' || key === 'SPACING_Y') {
    layout();
  }
}

const audioKeys = ['SENSITIVITY', 'ATTACK', 'DECAY', 'PEAK_DECAY', 'GLOBAL_FLOOR', 'GLOBAL_RANGE_DB'];
const boxes = {
  audio: document.getElementById('sliders-audio'),
  motion: document.getElementById('sliders-motion'),
};
for (const spec of SLIDERS) {
  boxes[audioKeys.includes(spec.key) ? 'audio' : 'motion'].append(sliderRow(spec));
}

function refreshSliders() {
  for (const spec of SLIDERS) {
    const input = document.getElementById(`sl-${spec.key}`);
    if (input) {
      input.value = cfg[spec.key];
      input.previousElementSibling.textContent = cfg[spec.key];
    }
  }
}

// ---------------------------------------------------------------- input

function togglePanel(force) {
  const open = force === undefined ? !panel.classList.contains('open') : force;
  panel.classList.toggle('open', open);
  document.getElementById('btn-settings').classList.toggle('on', open);
}

document.getElementById('btn-settings').addEventListener('click', () => togglePanel());
document.getElementById('btn-close').addEventListener('click', () => togglePanel(false));
document.getElementById('btn-reset').addEventListener("click", () => {
  resetConfig(cfg);
  refreshSliders();
  layout();
  hues = hueRamp(cfg);
});

const fileInput = document.getElementById('file');
document.getElementById('btn-file').addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
  const f = fileInput.files && fileInput.files[0];
  if (!f) return;
  await startFile(f);
  fileInput.value = '';
});

async function startFile(file) {
  try {
    ensureAnalyser();
    setStatus(`loading ${file.name}`);
    await audio.playFile(file);
    hint.classList.add('gone');
  } catch (e) {
    setStatus(`could not play that file: ${e.message}`);
  }
}

document.getElementById('btn-share').addEventListener('click', async () => {
  try {
    ensureAnalyser();
    await audio.captureDisplay();
    hint.classList.add('gone');
  } catch (e) {
    setStatus(e.message || 'screen share was cancelled');
  }
});

document.getElementById('btn-mic').addEventListener('click', async () => {
  try {
    ensureAnalyser();
    await audio.captureMic();
    hint.classList.add('gone');
  } catch (e) {
    setStatus(e.message || 'microphone was not available');
  }
});

document.getElementById('btn-full').addEventListener('click', toggleFullscreen);

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen().catch(() => {});
}

window.addEventListener('keydown', (e) => {
  if (e.target instanceof HTMLInputElement) return;
  if (e.key === 'f' || e.key === 'F') {
    // F and F11 both toggle fullscreen on the desktop build; the browser owns
    // F11, so only F is bound here.
    toggleFullscreen();
  } else if (e.key === 'h' || e.key === 'H') {
    togglePanel();
  } else if (e.key === 'Escape') {
    togglePanel(false);
  }
});

const dropEl = document.getElementById('drop');
let dragDepth = 0;
window.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropEl.classList.add('active');
});
window.addEventListener('dragleave', () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) dropEl.classList.remove('active');
});
window.addEventListener('drop', async (e) => {
  e.preventDefault();
  dropEl.classList.remove('active');
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (f) await startFile(f);
});

window.addEventListener('resize', () => {
  layout();
});

// A frame is only drawn once something is playing, but the canvas should not be
// a blank rectangle before that: draw the resting row immediately.
layout();
renderer.draw(cfg.NUM_ITEMS, view, balls, bands, hues);
requestAnimationFrame(frame);

// Hooks for the test harness. They are the only global the page creates.
window.__fizz = {
  cfg,
  audio,
  get balls() { return balls; },
  get bands() { return Array.from(bands); },
  get pan() { return Array.from(pan); },
  get gate() { return gate; },
  get state() { return { kind: audio.kind, label: audio.label, ctx: audio.ctx && audio.ctx.state, width: renderer.width, height: renderer.height }; },
  startTestTone: (freq, amp) => {
    ensureAnalyser();
    return audio.startTestTone(freq, amp);
  },
  startBuffer: async (arrayBuffer) => {
    ensureAnalyser();
    const buffer = await audio.ctx.decodeAudioData(arrayBuffer);
    const src = audio.ctx.createBufferSource();
    audio.teardown();
    src.buffer = buffer;
    src.loop = true;
    src.connect(audio.bus);
    audio.track = audio.ctx.createGain();
    src.connect(audio.track);
    audio.track.connect(audio.ctx.destination);
    audio.source = src;
    audio.mono = buffer.numberOfChannels === 1;
    audio.kind = 'file';
    audio.label = 'test buffer';
    src.start();
    await audio.resume();
    return audio.label;
  },
  defaults: DEFAULTS,
};
