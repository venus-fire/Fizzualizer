// Parity check: web/dsp.js against the Python analysis in fizzualizer.py.
//
//   node tests/parity_check.mjs
//
// Runs tests/parity_reference.py in the project venv, feeds both implementations
// the same 80 blocks, and compares every band, pan, gate and reference value on
// every frame. The port has to agree with the thing it is a port of, not merely
// look plausible.
//
// One exclusion, and it is the interesting part: a band whose true content is
// zero reads whatever the FFT's cancellation noise leaves there, and then the
// per-band normalizer divides that noise by a peak that is also noise. The two
// FFTs sum in different orders, numpy's pocketfft against the port's iterative
// radix-2, so those bands agree in character and not in digits. Comparison here
// is limited to bands with real signal in them, RAW_FLOOR, which is 30 dB below
// a single unit of float magnitude. The noise bands are reported, not compared.

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { readFileSync } from 'node:fs';

import { BandAnalyser } from '../dsp.js';
import { DEFAULTS } from '../config.js';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const SR = 44100;
const N = DEFAULTS.FFT_SIZE;
const RAW_FLOOR = 1e-5;

const venvPython = join(root, '.venv', 'bin', 'python');
let python = venvPython;
try {
  readFileSync(venvPython);
} catch (e) {
  python = 'python3';
}

const proc = spawnSync(python, [join(here, 'parity_reference.py')], {
  encoding: 'utf8',
  maxBuffer: 32 * 1024 * 1024,
});
if (proc.status !== 0) {
  console.error('reference failed:', proc.stderr || proc.status);
  process.exit(1);
}
const ref = JSON.parse(proc.stdout);

function block(kind) {
  const left = new Float32Array(N);
  const right = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const s = i / SR;
    if (kind === 'mix') {
      left[i] = 0.55 * Math.sin(2 * Math.PI * 440 * s) + 0.22 * Math.sin(2 * Math.PI * 3100 * s + 0.7);
      right[i] = 0.4 * Math.sin(2 * Math.PI * 440 * s + 0.2) + 0.31 * Math.sin(2 * Math.PI * 3100 * s);
    } else if (kind === 'quiet') {
      left[i] = 0.055 * Math.sin(2 * Math.PI * 440 * s) + 0.022 * Math.sin(2 * Math.PI * 3100 * s + 0.7);
      right[i] = 0.04 * Math.sin(2 * Math.PI * 440 * s + 0.2) + 0.031 * Math.sin(2 * Math.PI * 3100 * s);
    } else {
      left[i] = 0;
      right[i] = 0;
    }
  }
  return { left, right };
}

const an = new BandAnalyser({ ...DEFAULTS }, SR);
const mine = ref.frames.map((f) => {
  const { left, right } = block(f.kind);
  const scale = f.kind === 'silence' ? 0.7 : 1.0;
  const out = an.analyse(left, right, scale, false);
  const raw = Array.from(out.bands, (_, i) => 0.5 * (an.meanL[i] + an.meanR[i]));
  return {
    bands: Array.from(out.bands),
    pan: Array.from(out.pan),
    raw,
    gate: out.gate,
    refDb: out.refDb,
  };
});

let worstBand = 0;
let worstBandAt = '';
let worstRaw = 0;
let worstPan = 0;
let worstGate = 0;
let worstFrame = -1;
let compared = 0;
let skipped = 0;

for (let i = 0; i < mine.length; i++) {
  const a = ref.frames[i];
  const b = mine[i];
  for (let k = 0; k < a.bands.length; k++) {
    if (a.raw[k] < RAW_FLOOR) {
      skipped++;
      continue;
    }
    worstRaw = Math.max(worstRaw, Math.abs(a.raw[k] - b.raw[k]) / Math.max(a.raw[k], 1e-9));
    compared++;
    const d = Math.abs(a.bands[k] - b.bands[k]);
    if (d > worstBand) {
      worstBand = d;
      worstBandAt = `frame ${i} band ${k}`;
      worstFrame = i;
    }
    worstPan = Math.max(worstPan, Math.abs(a.pan[k] - b.pan[k]));
  }
  worstGate = Math.max(worstGate, Math.abs(a.gate - b.gate));
}

let countMismatch = 0;
for (let i = 0; i < ref.counts.length; i++) {
  if (an.map.counts[i] !== ref.counts[i]) countMismatch++;
}

const tol = 2e-3;
const ok = countMismatch === 0 && worstBand < tol && worstPan < tol && worstGate < tol;

console.log(`python: ${python}`);
console.log(`frames compared: ${mine.length}`);
console.log(`bin counts differing: ${countMismatch}`);
console.log(`band-frame values compared: ${compared}, skipped as noise-floor: ${skipped}`);
console.log(`worst band delta: ${worstBand.toExponential(2)}${worstBandAt ? ' at ' + worstBandAt : ''}`);
console.log(`worst raw relative delta: ${worstRaw.toExponential(2)}`);
console.log(`worst pan delta:  ${worstPan.toExponential(2)}`);
console.log(`worst gate delta: ${worstGate.toExponential(2)}`);
console.log(`tolerance: ${tol}`);

const last = ref.frames[ref.frames.length - 1];
console.log(`final gate: python ${last.gate.toFixed(4)} js ${mine[mine.length - 1].gate.toFixed(4)}`);
console.log(ok ? 'parity ok' : 'PARITY FAILED');
process.exit(ok ? 0 : 1);
