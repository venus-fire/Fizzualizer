# Fizzualizer

A real-time audio visualizer for Linux (PipeWire) — 45 frequency-analyzed
circles with collision physics, HSV color gradient, and optional particles.

This is a **complete port** of [undefinist's Rainmeter Fizzualizer](https://github.com/undefinist/Fizzualizer)
(an audio visualizer for the Windows desktop widget engine Rainmeter), rebuilt
from scratch as a standalone Linux application. The original Lua physics,
Rainmeter INI layout, and HSV colouring logic were translated to Python and
OpenGL.

**Built with AI** — this entire project, from translating the Rainmeter Lua
physics to debugging PipeWire audio capture and optimizing the GPU renderer,
was developed entirely through conversation with an LLM-based coding agent
([Hermes Agent](https://hermes-agent.nousresearch.com)). No human wrote a
single line of the code directly.

## Quick Start

Requires a Linux system with **PipeWire**.

```bash
./run.sh
```

`run.sh` creates a local `.venv` (numpy, pygame, moderngl) on first run and
launches from it. On an immutable distro (Bazzite, Silverblue) this is the
path that works — the Nix route below needs Nix installed.

Or with Nix:

```bash
nix-shell shell.nix --command "python fizzualizer.py"
```

Dependencies are auto-resolved by whichever launcher you use.

## How it works

1. **Audio capture** — `pw-cat --record` with the `stream.capture.sink=true`
   PipeWire property captures from the default speaker's **monitor** (system
   audio output, not the microphone). This is the same approach used by
   [cava](https://github.com/karlstav/cava).

2. **FFT analysis** — 45 logarithmically-spaced frequency bands (10 Hz – 15 kHz)
   from a 2048-point real FFT, with attack/decay smoothing and per-band
   adaptive normalization so treble bands aren't drowned out by bass.

3. **Collision physics** — Two-pass collision detection (centre outward in
   both directions) ported directly from the Rainmeter Lua. Each ball is
   pushed away from overlapping neighbours and springs back to its rest
   position.

4. **GPU rendering** — All 45 circles drawn in a single OpenGL draw call
   via instanced quads (moderngl), reaching 60+ fps on integrated graphics.

5. **HSV colouring** — Balls sweep from blue (Hue 240) to purple (Hue 350),
   with saturation and value varying by band amplitude, matching the original
   skin's look.

## Controls

| Key | Action |
|-----|--------|
| **q** | Quit |
| **F** or **F11** | Toggle fullscreen |
| **Space** | Play/pause the active MPRIS player (via `playerctl`) |
| **Left** / **Right** | Previous / next track |

Starts fullscreen by default. Set `FULLSCREEN = False` in `config.py` for a
window; fullscreen uses the display's own resolution rather than
`WINDOW_WIDTH`/`WINDOW_HEIGHT`. The window is resizable, and the balls stay
centred when it is resized or fullscreen is toggled.

The current track from MPRIS is drawn in the bottom right corner, refreshed
every 1.5s. It is truncated to fit the window width.

`playerctl` is what drives all of the above. Without it on `PATH` the keys do
nothing and the corner stays empty; everything else works.

## Desktop launcher

```bash
./install-desktop.sh
```

Installs `fizzualizer.desktop` into `~/.local/share/applications` and the icon
into the user icon theme, filling in this checkout's path. It then shows up in
the application menu and the taskbar. Re-run it after moving the repo.

The installed entry is generated from the repo copy, so edit
`fizzualizer.desktop` and re-run the script rather than editing the file in
`~/.local/share/applications`.

`icons/fizzualizer.png` is generated from the SVG and is what the window
itself uses as its icon:

```bash
magick -background none -density 384 icons/fizzualizer.svg -resize 256x256 \
  -depth 8 PNG32:icons/fizzualizer.png
```

Keep the SVG background-free. A black plate on a dark panel or in a dark
launcher reads as an empty icon.

## Configuration

Edit `config.py` to adjust colours, ball size, spacing, sensitivity,
particles, etc. All settings mirror the original Rainmeter
`Visualizer.ini` variables.

Key ones:

| Variable | Default | What it does |
|----------|---------|--------------|
| `SENSITIVITY` | 55 | Audio responsiveness (0-100) |
| `NO_PARTICLES` | True | Set `False` for bouncing particle effects |
| `HUE_START` | 240 | Colour gradient start (blue) |
| `HUE_END` | 350 | Colour gradient end (purple) |
| `MAX_BALL_SIZE` | 200 | Maximum ball diameter in pixels |
| `SPACING_X` | 12 | Horizontal spacing between balls |
| `SPACING_Y` | 12 | Vertical offset for staggered rows |

## Files

| File | What |
|------|------|
| `fizzualizer.py` | Main app (~520 lines) |
| `config.py` | All visualizer settings |
| `run.sh` | Launcher (creates and uses `.venv`) |
| `shell.nix` | Nix environment, alternative to `run.sh` |
| `fizzualizer.desktop` | Desktop entry template (`@EXEC@` / `@PATH@` filled at install) |
| `install-desktop.sh` | Installs the desktop entry and icon for the current user |
| `icons/fizzualizer.svg` | App icon source (no background plate) |
| `icons/fizzualizer.png` | Generated from the SVG; used as the window icon |
| `@Resources/` + `Visualizer.ini` | Original Rainmeter source files (kept for reference) |

## Original

- **Author:** undefinist (Malody Hoe)
- **Original skin:** [Fizzualizer on DeviantArt](https://www.deviantart.com/undefinist/art/The-Fizzualizer-762959030)
- **Rainmeter:** [rainmeter.net](https://www.rainmeter.net/)
