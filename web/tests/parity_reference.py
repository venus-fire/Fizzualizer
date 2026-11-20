"""Reference implementation of get_bands, lifted from fizzualizer.py.

The desktop app's StreamCapture owns a PipeWire process, so it cannot be
imported to produce reference numbers. This module is the analysis half of it,
copied verbatim, with the capture replaced by blocks handed in by the caller.
tests/parity_check.mjs feeds both this and web/dsp.js the same audio and
compares the output.
"""

import json
import math
import sys

import numpy as np

# Mirrors config.py, kept here so the reference does not move under the test.
FFT_SIZE = 2048
SAMPLE_RATE = 44100
SENSITIVITY = 30
ATTACK = 0.5
DECAY = 0.97
FREQ_MIN = 10
FREQ_MAX = 15000
NUM_ITEMS = 45
PEAK_DECAY = 0.993
GLOBAL_FLOOR = 0.53
GLOBAL_RANGE_DB = 12.0
GLOBAL_REF_FALL = 0.2
GLOBAL_ATTACK = 0.35
GLOBAL_RELEASE = 0.06
REFERENCE_FPS = 43
PAN_SMOOTH = 0.01


class Reference:
    def __init__(self):
        self._freqs = np.fft.rfftfreq(FFT_SIZE, 1.0 / SAMPLE_RATE)
        log_min = math.log10(max(FREQ_MIN, 1))
        log_max = math.log10(max(FREQ_MAX, log_min + 0.1))
        edges = np.logspace(log_min, log_max, NUM_ITEMS + 1)
        self._band_idx = np.digitize(self._freqs, edges) - 1
        self._band_idx = np.clip(self._band_idx, 0, NUM_ITEMS - 1)
        self._counts = np.bincount(self._band_idx, minlength=NUM_ITEMS).astype(np.float32)
        self._window = np.hanning(FFT_SIZE)
        self._smoothed = np.zeros(NUM_ITEMS, dtype=np.float32)
        self._pan = np.zeros(NUM_ITEMS, dtype=np.float32)
        self._per_band_peak = np.ones(NUM_ITEMS, dtype=np.float32) * 1e-6
        self._band_ratio = np.zeros(NUM_ITEMS, dtype=np.float32)
        self._ref_db = -60.0
        self._gate = 1.0

    def get_bands(self, window, scale=1.0):
        left = window[:, 0] * self._window
        right = window[:, 1] * self._window
        mag_l = np.abs(np.fft.rfft(left))
        mag_r = np.abs(np.fft.rfft(right))

        mean_l = np.divide(
            np.bincount(self._band_idx, weights=mag_l, minlength=NUM_ITEMS),
            self._counts, out=np.zeros(NUM_ITEMS), where=self._counts > 0)
        mean_r = np.divide(
            np.bincount(self._band_idx, weights=mag_r, minlength=NUM_ITEMS),
            self._counts, out=np.zeros(NUM_ITEMS), where=self._counts > 0)

        raw = 0.5 * (mean_l + mean_r)
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
        raw_in = raw.copy()  # before normalization, for the parity comparison

        total = mean_l + mean_r
        pan = np.divide(mean_r - mean_l, total,
                        out=np.zeros(NUM_ITEMS), where=total > 1e-9)
        pan = np.nan_to_num(pan, nan=0.0, posinf=0.0, neginf=0.0)

        decay = PEAK_DECAY ** scale
        self._per_band_peak = np.maximum(raw, self._per_band_peak * decay)
        self._per_band_peak = np.maximum(self._per_band_peak, 1e-6)
        self._band_ratio = raw / self._per_band_peak
        self._band_ratio = np.clip(self._band_ratio, 0.0, 1.0)

        rms = float(np.sqrt(np.mean(window.astype(np.float64) ** 2)))
        db = 20.0 * math.log10(max(rms, 1e-9))
        self._ref_db = max(db, self._ref_db - GLOBAL_REF_FALL * scale / REFERENCE_FPS)
        below = self._ref_db - db
        target_gate = 1.0 - min(1.0, max(0.0, below / max(GLOBAL_RANGE_DB, 1e-3)))
        if target_gate > self._gate:
            self._gate += min(1.0, GLOBAL_ATTACK * scale) * (target_gate - self._gate)
        else:
            self._gate += (1.0 - (1.0 - GLOBAL_RELEASE) ** scale) * (target_gate - self._gate)
        raw = self._band_ratio * (GLOBAL_FLOOR + (1.0 - GLOBAL_FLOOR) * self._gate)

        sens = 0.5 + SENSITIVITY / 100.0 * 1.5
        raw = np.clip(raw * sens, 0.0, 1.0)

        attack = min(1.0, ATTACK * scale)
        release = 1.0 - (1.0 - DECAY) ** scale
        rising = raw > self._smoothed
        self._smoothed[rising] += attack * (raw[rising] - self._smoothed[rising])
        self._smoothed[~rising] += release * (raw[~rising] - self._smoothed[~rising])

        target = pan * self._smoothed
        self._pan += min(1.0, PAN_SMOOTH * scale) * (target - self._pan)
        return self._smoothed, self._pan, self._gate, self._ref_db, raw_in


def block(kind):
    """Deterministic stereo blocks, generated identically in JS."""
    t = np.arange(FFT_SIZE, dtype=np.float64) / SAMPLE_RATE
    if kind == "mix":
        left = 0.55 * np.sin(2 * np.pi * 440.0 * t) + 0.22 * np.sin(2 * np.pi * 3100.0 * t + 0.7)
        right = 0.40 * np.sin(2 * np.pi * 440.0 * t + 0.2) + 0.31 * np.sin(2 * np.pi * 3100.0 * t)
    elif kind == "quiet":
        left = 0.055 * np.sin(2 * np.pi * 440.0 * t) + 0.022 * np.sin(2 * np.pi * 3100.0 * t + 0.7)
        right = 0.040 * np.sin(2 * np.pi * 440.0 * t + 0.2) + 0.031 * np.sin(2 * np.pi * 3100.0 * t)
    else:
        left = np.zeros(FFT_SIZE)
        right = np.zeros(FFT_SIZE)
    return np.stack([left, right], axis=1).astype(np.float32)


def main():
    ref = Reference()
    out = []
    sequence = ["mix"] * 20 + ["quiet"] * 20 + ["silence"] * 40
    for i, kind in enumerate(sequence):
        w = block(kind)
        scale = 1.0 if kind != "silence" else 0.7
        bands, pan, gate, ref_db, raw = ref.get_bands(w, scale)
        out.append({
            "step": i,
            "kind": kind,
            "bands": [float(x) for x in bands],
            "pan": [float(x) for x in pan],
            "raw": [float(x) for x in raw],
            "gate": float(gate),
            "ref_db": float(ref_db),
        })
    json.dump({"counts": [int(c) for c in ref._counts], "frames": out}, sys.stdout)


if __name__ == "__main__":
    main()
