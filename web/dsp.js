// Band analysis: the same pipeline as StreamCapture.get_bands in fizzualizer.py.
//
// This module touches no DOM, so tests/analyser_test.mjs can run it in node
// against synthetic audio and check the numbers rather than the pixels.

// Iterative radix-2 FFT. Size is fixed by FFT_SIZE and is a power of two.
export class FFT {
  constructor(n) {
    if ((n & (n - 1)) !== 0) throw new Error(`FFT size must be a power of two, got ${n}`);
    this.n = n;
    const bits = Math.log2(n);
    this.rev = new Uint32Array(n);
    for (let i = 0; i < n; i++) {
      let r = 0;
      for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b);
      this.rev[i] = r;
    }
    this.cos = new Float64Array(n / 2);
    this.sin = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      this.cos[i] = Math.cos((-2 * Math.PI * i) / n);
      this.sin[i] = Math.sin((-2 * Math.PI * i) / n);
    }
    this.re = new Float64Array(n);
    this.im = new Float64Array(n);
    this.mag = new Float32Array(n / 2 + 1);
  }

  // Magnitude spectrum of one real, already windowed block.
  magnitude(input) {
    const { n, re, im, rev, cos, sin, mag } = this;
    for (let i = 0; i < n; i++) {
      re[i] = input[rev[i]];
      im[i] = 0;
    }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1;
      const step = n / size;
      for (let i = 0; i < n; i += size) {
        for (let j = 0; j < half; j++) {
          const k = j * step;
          const a = i + j;
          const b = a + half;
          const tre = re[b] * cos[k] - im[b] * sin[k];
          const tim = re[b] * sin[k] + im[b] * cos[k];
          re[b] = re[a] - tre;
          im[b] = im[a] - tim;
          re[a] += tre;
          im[a] += tim;
        }
      }
    }
    for (let i = 0; i <= n / 2; i++) mag[i] = Math.hypot(re[i], im[i]);
    return mag;
  }
}

export function hanning(n) {
  const w = new Float32Array(n);
  for (let i = 0; i < n; i++) w[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1));
  return w;
}

// Log-spaced band edges and the bin-to-band map, matching
// np.digitize(rfftfreq, np.logspace(...)) - 1, clipped.
export function makeBandMap(numItems, freqMin, freqMax, fftSize, sampleRate) {
  const logMin = Math.log10(Math.max(freqMin, 1));
  const logMax = Math.log10(Math.max(freqMax, logMin + 0.1));
  const edges = new Float64Array(numItems + 1);
  for (let i = 0; i <= numItems; i++) {
    edges[i] = Math.pow(10, logMin + ((logMax - logMin) * i) / numItems);
  }
  const bins = fftSize / 2 + 1;
  const idx = new Int32Array(bins);
  for (let k = 0; k < bins; k++) {
    const f = (k * sampleRate) / fftSize;
    // upper bound: number of edges <= f
    let b = 0;
    while (b < edges.length && edges[b] <= f) b++;
    idx[k] = Math.min(numItems - 1, Math.max(0, b - 1));
  }
  const counts = new Float32Array(numItems);
  for (let k = 0; k < bins; k++) counts[idx[k]] += 1;
  return { edges, idx, counts };
}

const clamp01 = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);

export class BandAnalyser {
  constructor(cfg, sampleRate) {
    this.cfg = cfg;
    this.sampleRate = sampleRate;
    this.n = cfg.FFT_SIZE;
    this.fft = new FFT(this.n);
    this.window = hanning(this.n);
    this.map = makeBandMap(cfg.NUM_ITEMS, cfg.FREQ_MIN, cfg.FREQ_MAX, this.n, sampleRate);

    this.lin = new Float32Array(this.n);
    this.rin = new Float32Array(this.n);

    this.smoothed = new Float32Array(cfg.NUM_ITEMS);
    this.pan = new Float32Array(cfg.NUM_ITEMS);
    this.peak = new Float32Array(cfg.NUM_ITEMS).fill(1e-6);
    this.ratio = new Float32Array(cfg.NUM_ITEMS);
    this.meanL = new Float32Array(cfg.NUM_ITEMS);
    this.meanR = new Float32Array(cfg.NUM_ITEMS);
    this.refDb = -60;
    this.gate = 1;
  }

  // Set the config object's NUM_ITEMS or band range changed.
  rebuild() {
    const c = this.cfg;
    this.map = makeBandMap(c.NUM_ITEMS, c.FREQ_MIN, c.FREQ_MAX, this.n, this.sampleRate);
    this.smoothed = new Float32Array(c.NUM_ITEMS);
    this.pan = new Float32Array(c.NUM_ITEMS);
    this.peak = new Float32Array(c.NUM_ITEMS).fill(1e-6);
    this.ratio = new Float32Array(c.NUM_ITEMS);
    this.meanL = new Float32Array(c.NUM_ITEMS);
    this.meanR = new Float32Array(c.NUM_ITEMS);
  }

  bandMeans(mag, out) {
    const { idx, counts } = this.map;
    out.fill(0);
    for (let k = 0; k < idx.length; k++) out[idx[k]] += mag[k];
    for (let i = 0; i < out.length; i++) out[i] = counts[i] > 0 ? out[i] / counts[i] : 0;
  }

  // left/right: Float32Array of the newest FFT_SIZE samples per channel.
  // scale: frame time relative to REFERENCE_FPS, so per-frame constants keep
  // their wall-clock feel. mono: one channel duplicated, so pan stays zero.
  analyse(left, right, scale, mono) {
    const c = this.cfg;
    const n = this.n;
    const w = this.window;

    for (let i = 0; i < n; i++) this.lin[i] = left[i] * w[i];
    const magL = this.fft.magnitude(this.lin);
    this.bandMeans(magL, this.meanL);

    if (mono) {
      this.meanR.set(this.meanL);
    } else {
      for (let i = 0; i < n; i++) this.rin[i] = right[i] * w[i];
      const magR = this.fft.magnitude(this.rin);
      this.bandMeans(magR, this.meanR);
    }

    // RMS over both channels, matching np.mean over the stereo block.
    let sum = 0;
    for (let i = 0; i < n; i++) {
      sum += left[i] * left[i];
      if (!mono) sum += right[i] * right[i];
    }
    const rms = Math.sqrt(sum / (mono ? n : n * 2));

    let rawDb = 20 * Math.log10(Math.max(rms, 1e-9));
    if (!Number.isFinite(rawDb)) rawDb = -180;

    // Per-band adaptive normalization.
    const decay = Math.pow(c.PEAK_DECAY, scale);
    // Common normalizer: the gate.
    this.refDb = Math.max(rawDb, this.refDb - (c.GLOBAL_REF_FALL * scale) / c.REFERENCE_FPS);
    const below = this.refDb - rawDb;
    const targetGate = 1 - clamp01(below / Math.max(c.GLOBAL_RANGE_DB, 1e-3));
    if (targetGate > this.gate) {
      this.gate += Math.min(1, c.GLOBAL_ATTACK * scale) * (targetGate - this.gate);
    } else {
      this.gate += (1 - Math.pow(1 - c.GLOBAL_RELEASE, scale)) * (targetGate - this.gate);
    }
    const floorGain = c.GLOBAL_FLOOR + (1 - c.GLOBAL_FLOOR) * this.gate;

    const sens = 0.5 + (c.SENSITIVITY / 100) * 1.5;
    const attack = Math.min(1, c.ATTACK * scale);
    const release = 1 - Math.pow(1 - c.DECAY, scale);

    for (let i = 0; i < this.meanL.length; i++) {
      let raw = 0.5 * (this.meanL[i] + this.meanR[i]);
      if (!Number.isFinite(raw)) raw = 0;
      this.peak[i] = Math.max(raw, this.peak[i] * decay, 1e-6);
      this.ratio[i] = clamp01(raw / this.peak[i]);
      raw = clamp01(this.ratio[i] * floorGain * sens);

      if (raw > this.smoothed[i]) this.smoothed[i] += attack * (raw - this.smoothed[i]);
      else this.smoothed[i] += release * (raw - this.smoothed[i]);

      // Pan, weighted by the band so a quiet band cannot yank its ball about.
      let pan = 0;
      if (!mono) {
        const total = this.meanL[i] + this.meanR[i];
        if (total > 1e-9) pan = (this.meanR[i] - this.meanL[i]) / total;
      }
      const target = pan * this.smoothed[i];
      this.pan[i] += Math.min(1, c.PAN_SMOOTH * scale) * (target - this.pan[i]);
    }

    return { bands: this.smoothed, pan: this.pan, rms, gate: this.gate, refDb: this.refDb };
  }
}
