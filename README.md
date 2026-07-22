# Fizzualizer

Audio visualizer for Linux (PipeWire) — port of undefinist's Rainmeter Fizzualizer.

45 frequency-analyzed circles with collision physics, HSV color gradient
(blue → purple), and optional bouncing particles.

Captures from the **default speaker's monitor** — listens to system audio
output (music, games, etc.), not the microphone.

## Quick Start

```bash
./run.sh
```

Or manually:

```bash
nix-shell shell.nix --command "python fizzualizer.py"
```

## Controls

- **Esc** — Quit
- **F** — Toggle fullscreen

## Configuration

Edit `config.py` to adjust colors, ball size, spacing, sensitivity, particles, etc.
All settings mirror the original Rainmeter `Visualizer.ini` variables.

Key ones:
- `SENSITIVITY` (0-100) — audio responsiveness
- `NO_PARTICLES` — set to `False` to enable bouncing particle effects
- `OFFSET_X` / `OFFSET_Y` — overrides auto-centering (set to center)
- `HUE_START` / `HUE_END` — color gradient range
- `MAX_BALL_SIZE` / `SPACING_X` / `SPACING_Y` — ball layout

## Dependencies (auto-resolved via nix-shell)

- Python 3, numpy, pygame
- System: PipeWire (with `pw-cat` / `pw-dump`)

The audio capture uses `pw-cat --record` targeting the default sink's
monitor — no ALSA/PortAudio device confusion.
