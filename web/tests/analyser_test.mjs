// Headless checks for the parts of the web build that can be tested without a
// browser: band mapping, the analyser's smoothing and gate, pan, and physics.
//
//   node tests/analyser_test.mjs
//
// Any failure exits non-zero.

import { BandAnalyser, FFT, makeBandMap, hanning } from '../dsp.js';
import { createBalls, collide, hueRamp } from '../physics.js';
import { DEFAULTS } from '../config.js';

let failures = 0;
function check(name, ok, detail = '') {
  const tag = ok ? 'ok  ' : 'FAIL';
  console.log(`${tag} ${name}${detail ? '  ' + detail : ''}`);
  if (!ok) failures++;
}

const SR = 44100;
const N = DEFAULTS.FFT_SIZE;

function sine(freq, amp, len = N, phase = 0) {
  const a = new Float32Array(len);
  for (let i = 0; i < len; i++) a[i] = amp * Math.sin((2 * Math.PI * freq * i) / SR + phase);
  return a;
}

// The FFT itself: a 1000 Hz bin should dominate, and total energy should scale
// with amplitude squared.
{
  const fft = new FFT(N);
  const w = hanning(N);
  const block = sine(1000, 1).map((v, i) => v * w[i]);
  const mag = Float64Array.from(fft.magnitude(block));
  let peak = 0;
  for (let i = 1; i < mag.length; i++) if (mag[i] > mag[peak]) peak = i;
  const peakHz = (peak * SR) / N;
  check('fft peaks at the tone', Math.abs(peakHz - 1000) < 44, `${peakHz.toFixed(1)} Hz`);

  // magnitude() returns an internal buffer that the next call overwrites, so
  // the first result has to be copied before the second call.
  const quiet = Float64Array.from(fft.magnitude(sine(1000, 0.5).map((v, i) => v * w[i])));
  check('fft is linear in amplitude', Math.abs(quiet[peak] / mag[peak] - 0.5) < 0.02,
    `ratio ${(quiet[peak] / mag[peak]).toFixed(3)}`);
}

// Band mapping. The lowest bands are narrower than one FFT bin at this size, so
// a handful of them own no bin at all and read zero; the desktop build has the
// same hole, and the parity check confirms the maps are identical.
{
  const map = makeBandMap(DEFAULTS.NUM_ITEMS, DEFAULTS.FREQ_MIN, DEFAULTS.FREQ_MAX, N, SR);
  const empty = [...map.counts].filter((c) => c === 0).length;
  const binHz = SR / N;
  // Independent scan: a band has a bin if any k * binHz lies inside it. Band 0
  // is special because the DC bin at 0 Hz is clipped into it.
  let mismatches = 0;
  for (let i = 0; i < DEFAULTS.NUM_ITEMS; i++) {
    const lo = map.edges[i];
    const hi = map.edges[i + 1];
    let has = i === 0;
    for (let k = 1; k <= N / 2 && !has; k++) {
      const f = k * binHz;
      if (f >= lo && f < hi) has = true;
    }
    if (has !== map.counts[i] > 0) mismatches++;
  }
  check('band map matches an independent bin scan', mismatches === 0,
    `${empty} empty bands, ${binHz.toFixed(1)} Hz per bin`);
  check('the top band owns bins', map.counts[DEFAULTS.NUM_ITEMS - 1] > 0,
    `${map.counts[DEFAULTS.NUM_ITEMS - 1]} bins`);

  for (const hz of [60, 220, 1000, 4000, 12000]) {
    const an = new BandAnalyser({ ...DEFAULTS }, SR);
    const left = sine(hz, 0.5);
    const right = sine(hz, 0.5);
    let out;
    for (let i = 0; i < 8; i++) out = an.analyse(left, right, 1, false);
    // Raw band means, not the normalized output: the per-band normalizer drives
    // every live band toward 1, which makes the normalized picture useless for
    // asking which band a tone landed in.
    let peak = 0;
    for (let i = 0; i < an.meanL.length; i++) if (an.meanL[i] > an.meanL[peak]) peak = i;
    const lo = map.edges[peak];
    const hi = map.edges[peak + 1];
    check(`tone ${hz} Hz lands in its band`, hz >= lo && hz < hi,
      `band ${peak} (${lo.toFixed(0)}..${hi.toFixed(0)} Hz)`);
  }
}

// The gate: a loud passage followed by silence must pull the bands down toward
// GLOBAL_FLOOR rather than leaving them pinned at full.
{
  const an = new BandAnalyser({ ...DEFAULTS }, SR);
  const loud = sine(440, 0.6);
  for (let i = 0; i < 40; i++) an.analyse(loud, loud, 1, false);
  const loudMean = an.smoothed.reduce((a, b) => a + b, 0) / an.smoothed.length;

  const silence = new Float32Array(N);
  for (let i = 0; i < 400; i++) an.analyse(silence, silence, 1, false);
  const quietMean = an.smoothed.reduce((a, b) => a + b, 0) / an.smoothed.length;
  check('silence closes the gate', an.gate < 0.05, `gate ${an.gate.toFixed(3)}`);
  check('silence drops the bands', quietMean < loudMean * 0.5,
    `loud ${loudMean.toFixed(3)} -> quiet ${quietMean.toFixed(3)}`);

  // The floor's job shows on a quiet passage that still has signal in it: with
  // the common normalizer off, the per-band one alone reads the hushed passage
  // nearly as busy as the loud one.
  const make = (floor) => {
    const hush = sine(440, 0.06);
    const a = new BandAnalyser({ ...DEFAULTS, GLOBAL_FLOOR: floor }, SR);
    for (let i = 0; i < 40; i++) a.analyse(loud, loud, 1, false);
    for (let i = 0; i < 60; i++) a.analyse(hush, hush, 1, false);
    return a.smoothed.reduce((x, y) => x + y, 0) / a.smoothed.length;
  };
  const gated = make(DEFAULTS.GLOBAL_FLOOR);
  const floorOnly = make(1.0);
  check('the gate damps a quiet passage', gated < floorOnly * 0.9,
    `gated ${gated.toFixed(3)} vs normalizer off ${floorOnly.toFixed(3)}`);
}

// Pan: band energy in one ear only moves the pan toward that side.
{
  const an = new BandAnalyser({ ...DEFAULTS }, SR);
  const left = sine(1000, 0.5);
  const zero = new Float32Array(N);
  let out;
  for (let i = 0; i < 200; i++) out = an.analyse(left, zero, 1, false);
  const idx = 25;
  check('left-only audio pans negative', out.pan[idx] < -0.2, `pan ${out.pan[idx].toFixed(2)} at band ${idx}`);

  const mono = new BandAnalyser({ ...DEFAULTS }, SR);
  for (let i = 0; i < 200; i++) out = mono.analyse(left, left, 1, true);
  const sum = out.pan.reduce((a, b) => a + Math.abs(b), 0);
  check('mono input never pans', sum < 1e-6, `sum |pan| ${sum.toExponential(2)}`);
}

// Frame-rate scaling: the same wall-clock time must produce the same amount of
// change whether it arrives as many small frames or few large ones.
{
  const fast = new BandAnalyser({ ...DEFAULTS }, SR);
  const slow = new BandAnalyser({ ...DEFAULTS }, SR);
  const block = sine(440, 0.4);
  for (let i = 0; i < 258; i++) fast.analyse(block, block, 1, true); // 258 frames at 1/43s
  for (let i = 0; i < 6; i++) slow.analyse(block, block, 43, true); // same 6 seconds in 6 frames
  const f = fast.smoothed[20];
  const s = slow.smoothed[20];
  check('constants survive a frame-rate change', Math.abs(f - s) < 0.12, `43fps ${f.toFixed(3)} vs 1fps ${s.toFixed(3)}`);
}

// Physics: overlapping balls separate, springs pull them back, and nothing goes
// NaN when every band is at full.
{
  const cfg = { ...DEFAULTS };
  const balls = createBalls(cfg, 1920, 1080);
  const bands = new Float32Array(cfg.NUM_ITEMS).fill(1);
  const startX = balls[20].x;
  for (let i = 0; i < 30; i++) {
    const mid = cfg.NUM_ITEMS >> 1;
    collide(cfg, balls, bands, mid, -1, 1);
    collide(cfg, balls, bands, mid, 1, 1);
  }
  const finite = balls.every((b) => Number.isFinite(b.x) && Number.isFinite(b.y));
  check('collision stays finite', finite);
  const spread = Math.max(...balls.map((b) => Math.abs(b.x - b.ox)));
  check('loud bands spread the row', spread > 20, `max offset ${spread.toFixed(1)} px from rest`);

  // Silent bands have a zero radius, so nothing should move at all.
  const quiet = createBalls(cfg, 1920, 1080);
  const zeros = new Float32Array(cfg.NUM_ITEMS);
  for (let i = 0; i < 30; i++) {
    const mid = cfg.NUM_ITEMS >> 1;
    collide(cfg, quiet, zeros, mid, -1, 1);
    collide(cfg, quiet, zeros, mid, 1, 1);
  }
  const moved = quiet.some((b) => b.x !== b.ox || b.y !== b.oy);
  check('silent balls sit still', !moved);
  check('row is centred', Math.abs((buttonsCentre(balls, cfg) - 1920 / 2)) < 40);
  void startX;
}

function buttonsCentre(balls, cfg) {
  const xs = balls.map((b) => b.ox);
  return (Math.min(...xs) + Math.max(...xs)) / 2;
}

// Hue ramp matches HUE_START..HUE_END across the items.
{
  const hues = hueRamp({ ...DEFAULTS });
  check('hue ramp spans the configured range',
    Math.abs(hues[0] - 240 / 360) < 1e-6 && Math.abs(hues[hues.length - 1] - (240 + 110 * (44 / 45)) / 360) < 1e-6,
    `${(hues[0] * 360).toFixed(0)} -> ${(hues[hues.length - 1] * 360).toFixed(1)} deg`);
}

console.log(failures === 0 ? '\nall checks passed' : `\n${failures} check(s) failed`);
process.exit(failures === 0 ? 0 : 1);
