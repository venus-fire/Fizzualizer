# Fizzualizer

A real-time audio visualizer for Linux on PipeWire. 45 frequency-analyzed
circles with collision physics and an HSV colour gradient.

**Try it in a browser:** <https://plausibly-exceeding-murkiness.ngrok-free.dev/fizzualizer/>

That page is the [web build](#web-build), served from the machine this app was
developed on, so it is up while that machine and its tunnel are. Press Visit Site
on ngrok's warning page, then Load audio, or drop an audio file onto the window.
The desktop application is the full version. The page captures audio differently,
and the web build section says how.

This is a **complete port** of [undefinist's Rainmeter Fizzualizer](https://www.deviantart.com/undefinist/art/The-Fizzualizer-690602015),
an audio visualizer for the Windows desktop widget engine Rainmeter, rebuilt from
scratch as a standalone Linux application. The original Lua physics, Rainmeter INI
layout, and HSV colouring logic were translated to Python and OpenGL.

**Built with AI.** The whole project, from translating the Rainmeter Lua physics
to debugging PipeWire capture and optimizing the GPU renderer, was written through
conversation with an LLM coding agent, [Hermes Agent](https://hermes-agent.nousresearch.com).
No human wrote any of the code directly.

## Quick start

Requires a Linux system with **PipeWire**.

```bash
./run.sh
```

`run.sh` creates a local `.venv` with numpy, pygame and moderngl on first run, and
launches from it. On an immutable distro such as Bazzite or Silverblue this is the
path that works, since the Nix route below needs Nix installed. It asks `uv` for a
3.13 interpreter first, on PATH or at `~/.hermes/bin/uv`, and only falls back to
plain `python3 -m venv` when neither exists. That order matters because a venv
built on the distro's `/usr/bin/python3` stops importing its own packages as soon
as the image moves its python minor, and the failure reads as a broken app rather
than a broken environment. If `.venv` ever fails that way, delete it and re-run
with uv present.

Or with Nix:

```bash
nix-shell shell.nix --command "python fizzualizer.py"
```

Both launchers resolve the dependencies themselves.

## How it works

1. **Audio capture.** `parec` reads the default speaker's **monitor**, which is
   system audio output rather than the microphone. `pw-cat --record` with the
   `stream.capture.sink=true` property is the fallback for a host without pulse
   utils, and [cava](https://github.com/karlstav/cava) takes the same approach.
   parec comes first because `pw-cat` and `pw-record` both hand back about a
   quarter of a percent of NaN and runaway samples when their stdout is a pipe,
   which is enough to blank every band.

2. **FFT analysis.** 45 logarithmically spaced frequency bands covering 10 Hz to
   15 kHz, taken from a 2048-point real FFT, with attack and decay smoothing, a
   per-band adaptive normalizer so treble bands are not drowned out by bass, and a
   common normalizer on top so the picture tracks how loud the music actually is.

3. **Collision physics.** Two-pass collision detection, from the centre outward in
   both directions, ported directly from the Rainmeter Lua. Each ball is pushed
   away from overlapping neighbours and springs back to its rest position.

4. **GPU rendering.** All 45 circles drawn in a single OpenGL draw call with
   instanced quads through moderngl, reaching 60+ fps on integrated graphics.

5. **HSV colouring.** Balls sweep from blue at hue 240 to purple at hue 350, with
   saturation and value varying by band amplitude, matching the original skin's
   look.

## Controls

| Key | Action |
|-----|--------|
| **q** | Quit |
| **F** or **F11** | Toggle fullscreen |
| **Space** | Play/pause the active MPRIS player (via `playerctl`) |
| **Left** / **Right** | Previous / next track |
| **Up** / **Down** | System volume up / down by 1% |
| **D** | Toggle the Sonos delay compensation |

Holding up or down repeats, one step every `VOLUME_REPEAT_INTERVAL` seconds once
it has been held for `VOLUME_REPEAT_DELAY`, so the volume moves at a steady pace
instead of one step per tap. Both knobs are in `config.py`.

Starts fullscreen by default. Set `FULLSCREEN = False` in `config.py` to start in
a window instead. Fullscreen always uses the display's own resolution rather than
`WINDOW_WIDTH` and `WINDOW_HEIGHT`. The window is resizable, and the balls stay
centred when it is resized or fullscreen is toggled.

The current track from MPRIS is drawn in the bottom right corner, refreshed every
1.5s, and truncated to fit the window width.

`playerctl` drives the track keys and the corner line. Without it on `PATH` those
do nothing and the corner stays empty; everything else works. The volume keys use
`wpctl` under WirePlumber, falling back to `pactl`. The step size is
`VOLUME_STEP` in `config.py`.

## Sonos output

When the output is a Sonos speaker the sound and the picture drift apart.
sonos-linux serves the stream, the speaker buffers two to five seconds of it, and
the visualizer analyses the audio the moment it leaves the application, so the
balls land before you hear anything.

Press **D** and the analysis is held back by `SONOS_DELAY` seconds, so a drum
hit draws when it is heard rather than when it was played. The panel header
shows the state as `sonos +4.0s`, and the `sonos delay` slider sets the number
between 0 and 8 seconds. Raising it freezes the picture once while the queue
fills, which is the delay line filling rather than a stall. Lowering it drains
the queue, which skips the picture forward.

`SONOS_AUTO` does that on its own, and it is on by default. Every two seconds the
app asks WirePlumber which sink it routes new streams to, through `wpctl`, and
falls back to `pactl` when `wpctl` is missing, because the two can disagree; when it is one of the `sonos_<zone>` sinks that
sonos-linux creates, the delay applies itself and the log says so. The capture
also follows the default sink, because the speaker plays audio the previous
sink's monitor does not carry: selecting the speaker mid-run re-points the
capture, and selecting the onboard output again turns the delay back off.

The delay is measured in seconds rather than in frames, so changing
`SAMPLE_RATE` does not change what the number means.

## Config sliders

Move the mouse into the top third of the window and a strip of sliders appears
along the top, one for every numeric knob in `config.py`, each showing its current
value. Move the pointer away and they are gone. The panel stays hidden at launch
until the pointer actually moves, so opening the app with the cursor resting in
the top of the screen does not show it.

Dragging a slider applies the change live and writes it back into `config.py` when
the drag ends, or after a second without movement if the release never arrives.
That keeps `config.py` the single source of truth and hand-editable, and a kill or
a crash cannot lose a session's tuning. Only the number changes. Comments and the
rest of the file are left alone.

`UI_HOVER_ZONE` is how much of the window height counts, 0.34 for the top third,
and 0 keeps the sliders up permanently. It is itself a slider, so it can be dialled
in from the app. A drag holds the panel open regardless, so pulling a slider down
the screen does not make it vanish under the cursor.

The panel is drawn at `UI_ALPHA` opacity, 0.8 by default, so it is 20% transparent,
and `UI_ALPHA` is one of the sliders too. The labels carry a one pixel drop shadow
because the panel is translucent and a bright ball behind it would wash the text
out.

Some sliders need the app to rebuild something rather than read the value again,
and the app does it. `SPACING_X`, `SPACING_Y` and `MIN_BALL_SIZE` recreate the
balls, and `HUE_START` and `HUE_END` recompute the colour ramp. Everything else is
read fresh each frame.

## Motion

The skin's collision code sets a colliding ball's position to the contact point
outright. That pins the ball to whatever it touched, so a big ball sits frozen
while everything around it moves, and a band change of any size teleports it. This
pushes by a fraction of the overlap instead, so a ball slides out of the way and
keeps moving. `COLLIDE_PUSH` is that fraction and `SPRING_BACK` is how fast the
ball returns to its rest position.

`MAX_COLLIDER_SIZE` is what the balls push each other with, and it is much smaller
than `MAX_BALL_SIZE` on purpose, because it is the knob for how far apart a loud
passage spreads the row. Raise it and the row fans out until it leaves the window;
lower it and the balls pile into a tight row.

## Stereo

Capture is stereo, and each band's left and right balance moves its ball: a band
louder in the left ear pulls its ball up, one louder in the right ear pushes it
down. The travel scales with how loud the band is, so a quiet band barely moves,
and it is applied to the ball's rest height so the existing spring carries it there
rather than teleporting it. `STEREO_SHIFT` in `config.py` is the maximum travel in
pixels at full pan and full volume.

## Loudness

Each band divides by its own recent peak. That keeps bass from drowning out treble,
but on its own it makes the picture loudness-invariant: the peak decays to meet a
quiet passage within seconds, so a hushed stretch reads as fully as a chorus. A
common normalizer runs after the per-band divide and scales all 45 bands by how
loud the moment is against a falling reference measured in dB, leaving the balance
between the bands untouched.

On a piano track whose quiet passages sit about 30 dB down, the mean band value
went from 0.37 against 0.41 to 0.20 against 0.37, comparing the quietest and
loudest three second stretches. `GLOBAL_FLOOR` is how much of a band value survives
a fully shut gate and is the one to tune by ear, `GLOBAL_RANGE_DB` is how far the
music has to drop to shut it, and `GLOBAL_REF_FALL` is how fast the reference
forgets, in dB per second.

Loudness comes from the window's own RMS rather than from the band magnitudes. An
unweighted average over 45 log-spaced bands reads a thin bass note as quiet and a
wash of broadband hiss as loud, which inverts the gate on sparse material. Sparse
ambient music with almost no sustained dynamic range therefore barely moves the
gate, which is the limit of the approach rather than a bug.

## Analysis rate and pacing

A reader thread keeps the newest 2048 sample window in a ring, advancing it every
1024 samples, about 43 times a second at 44.1kHz. The render loop takes whatever
window is current and presents at the display's refresh rate, so the app runs at
the panel rate instead of the audio hop rate. Reading the audio inline is what
pinned the whole app to 43fps in bursts.

`FPS = 0` means "use the refresh rate of the output the window is on", read from
`xrandr` at startup and again when the window is resized. SDL exposes no refresh
rate under XWayland and pygame 2.6 has no API for one, so `xrandr` is the only
source. Each connected output's first starred mode is the one it is running, and
the window is matched to an output by size. Set `FPS` to a number to override it.

`ATTACK`, `DECAY`, `PEAK_DECAY`, `PAN_SMOOTH`, `COLLIDE_PUSH`, `SPRING_BACK`,
`GLOBAL_ATTACK` and `GLOBAL_RELEASE` are per-frame factors written for
`REFERENCE_FPS`. The app scales them by the real frame time, so raising `FPS`
smooths the motion without speeding it up. `PEAK_DECAY` is how fast each band
forgets its loudest recent moment. At 0.993 that is about a three second half-life,
so a band recovers from a preceding loud passage in a couple of seconds instead of
staying squashed for ten.

There is no working vsync on this stack. SDL's `vsync=1` does not throttle
presentation under KWin, moderngl 5.13 has no swap interval, and no GLX
swap-control entry point is reachable from Python. A tight render loop measures
over a million presents a second either way. The compositor owns presentation, so
there is no tearing to fix. What matters is that frames arrive evenly, and that is
the pacer.

pygame's `Clock.tick` is not that pacer. It waits with `SDL_Delay`, which rounds
down and undershoots by most of a millisecond a frame. At 60Hz that reads as 62fps
and nobody notices, but on a 144Hz panel it reads as 165fps, a frame every 6.08ms
against a 6.94ms period, and every frame lands somewhere different in the scan.
`Pacer` sleeps to an absolute deadline instead and measures 6.96ms mean with 90% of
frames inside 1ms of the period.

## Desktop launcher

```bash
./install-desktop.sh
```

Installs `fizzualizer.desktop` into `~/.local/share/applications` and the icon into
the user icon theme, filling in this checkout's path. It then shows up in the
application menu and the taskbar. Re-run it after moving the repo. The installed
entry is generated from the repo copy, so edit `fizzualizer.desktop` and re-run the
script rather than editing the file in `~/.local/share/applications`.

`icons/fizzualizer.png` is generated from the SVG and is what the window itself
uses as its icon:

```bash
magick -background none -density 384 icons/fizzualizer.svg -resize 256x256 \
  -depth 8 PNG32:icons/fizzualizer.png
```

Keep the SVG background-free. A black plate on a dark panel or in a dark launcher
reads as an empty icon.

## Configuration

Every setting lives in `config.py`, which stays the single source of truth and
stays hand-editable. Defaults below are the shipped values.

### Display

| Setting | Default | What it does |
|---|---|---|
| `FULLSCREEN` | `True` | Start fullscreen. Fullscreen always uses the display's own resolution. |
| `WINDOW_WIDTH` | `1920` | Window width when not fullscreen, and the fallback if the desktop size cannot be read. |
| `WINDOW_HEIGHT` | `1080` | Window height, same as above. |
| `FPS` | `0` | Frame rate target. 0 follows the refresh rate of the output the window is on. |
| `REFERENCE_FPS` | `43` | The rate the per-frame constants were written for. The app scales them by real frame time, so changing FPS does not change how the motion feels. |

### Sliders and input

| Setting | Default | What it does |
|---|---|---|
| `UI_HOVER_ZONE` | `0.34` | Fraction of the window height that shows the slider panel, 0.34 for the top third. 0 keeps it up permanently. |
| `UI_ALPHA` | `0.8` | Slider panel opacity, so 0.8 is 20% transparent. |
| `MOUSE_HIDE_DELAY` | `3` | Seconds of no mouse movement before the cursor hides. |
| `VOLUME_STEP` | `1` | Volume percent per up or down key press. |
| `VOLUME_REPEAT_DELAY` | `0.25` | Seconds a volume key is held before it starts repeating. |
| `VOLUME_REPEAT_INTERVAL` | `0.05` | Seconds between volume steps while held. |

### Audio analysis

| Setting | Default | What it does |
|---|---|---|
| `FFT_SIZE` | `2048` | Samples per analysis window. The window advances by half of this, so analyses overlap. |
| `SAMPLE_RATE` | `44100` | Capture rate. Must be a rate the capture tool can resample to. |
| `FREQ_MIN` | `10` | Lowest frequency the first band covers, in Hz. |
| `FREQ_MAX` | `15000` | Highest frequency the last band covers, in Hz. |
| `NUM_ITEMS` | `45` | Number of bands, which is also the number of balls. |
| `SENSITIVITY` | `30` | Overall responsiveness, 0 to 100. Higher means a quiet band reads louder. |
| `ATTACK` | `0.5` | How fast a band value rises toward a louder reading. Higher lands the hit harder. |
| `DECAY` | `0.97` | How fast a band value falls back. Higher is slower, so the tail lasts longer. |

### Sonos output

| Setting | Default | What it does |
|---------|---------|--------------|
| `SONOS_DELAY` | `4.0` | Seconds the analysis is held back, to match the speaker's own buffer. Tune it by ear between 2 and 5; the slider covers 0 to 8. |
| `SONOS_DELAY_ON` | `False` | The manual toggle, key **D**. Turning it with the key writes the new value back into this file. |
| `SONOS_AUTO` | `True` | Apply the delay by itself when the default sink is a `sonos_*` sink, and follow the default sink when it changes. |

### Normalization

| Setting | Default | What it does |
|---|---|---|
| `PEAK_DECAY` | `0.993` | How fast each band forgets its own loudest recent moment. At the current hop rate 0.993 is about a three second half-life. |
| `GLOBAL_FLOOR` | `0.53` | The common normalizer's floor: the share of a band value that survives when the gate is fully shut. 1.0 turns the common normalizer off, 0.0 lets a silent passage collapse the picture. |
| `GLOBAL_RANGE_DB` | `12.0` | How far below the reference a passage has to drop before the gate is fully shut. |
| `GLOBAL_REF_FALL` | `0.2` | How fast the reference falls, in dB per second. Lower means longer memory of the loudest recent moment. |
| `GLOBAL_ATTACK` | `0.35` | Per-frame rise of the gate. The rise is quicker than the fall so a drop is read at once. |
| `GLOBAL_RELEASE` | `0.06` | Per-frame fall of the gate. Higher follows a quiet passage down faster. |

### Balls

| Setting | Default | What it does |
|---|---|---|
| `MIN_BALL_SIZE` | `0` | Radius floor, so a silent band still draws something. 0 means the ball is not drawn at all. |
| `MAX_BALL_SIZE` | `230` | Radius of a band at full value. |
| `MAX_COLLIDER_SIZE` | `390` | Radius the balls push each other with. Much smaller than the drawn size on purpose: it sets how far a loud passage spreads the row. |
| `SPACING_X` | `30` | Horizontal distance between ball rest positions. |
| `SPACING_Y` | `6` | Vertical offset between staggered rows. |
| `SPRING_BACK` | `0.255` | How fast a ball returns to its rest height, as a fraction of the remaining distance per frame. |
| `COLLIDE_PUSH` | `0.14` | Fraction of an overlap resolved in one frame. 1.0 pins a ball to the contact point, which is what made big balls freeze. |
| `STEREO_SHIFT` | `120` | Most a ball travels up or down for the stereo pan, in pixels, at full pan and full volume. |
| `PAN_SMOOTH` | `0.01` | How quickly a ball follows a change in the pan. Lower is steadier. |

### Colour

| Setting | Default | What it does |
|---|---|---|
| `HUE_START` | `240` | Gradient start, 240 is blue. |
| `HUE_END` | `350` | Gradient end, 350 is purple. |
| `SAT_ZERO` | `0.75` | Saturation of a band reading exactly zero. Its own value, because a band at 0.001 uses the ramp below and the two sitting side by side is what looks washed out. |
| `SAT_MIN` | `0.69` | Saturation at the bottom of the ramp. |
| `SAT_MAX` | `1` | Saturation at full band value. |
| `VAL_ZERO` | `0.75` | Value, meaning brightness, of a band reading exactly zero. |
| `VAL_MIN` | `0.52` | Value at the bottom of the ramp. |
| `VAL_MAX` | `1` | Value at full band value. |

## Web build

`web/` is the same visualizer as a web page: no build step, no dependencies,
nothing to install. Three ways in, and they are not equivalent:

| Source | What it captures | Works in |
|---|---|---|
| **Load audio** | an audio file the page plays | any browser |
| **Share audio** | tab or system audio through `getDisplayMedia` | Chrome and Edge. Firefox and Safari hand back a video-only stream |
| **Microphone** | the microphone, which on PipeWire often includes a monitor source of the output | any browser, with permission |

The browser cannot read system audio on its own, which is the one thing the desktop
build does that this one cannot. Sharing a tab's audio is the closest equivalent,
and a device with a PipeWire monitor in its input list makes the microphone route a
real system-audio path.

Run it with any static file server, or use the copy served at
`https://plausibly-exceeding-murkiness.ngrok-free.dev/fizzualizer/`. That route is
documented in `~/.config/home-gateway/AGENTS.md`:

```bash
cd web && python3 -m http.server 8199 --bind 127.0.0.1
# http://127.0.0.1:8199/
```

It has to be served over HTTP, not opened as a `file://` path, because ES modules
and the audio APIs are blocked on `file://`.

Keys: **F** toggles fullscreen, **H** toggles the settings panel. Everything the
desktop app binds to MPRIS has no browser equivalent and is not bound here: space,
left, right and the volume keys.

Differences from the desktop build, all deliberate:

- **No PipeWire.** See the table above.
- **Settings live in `web/config.js` and in localStorage.** The panel writes each
  change into this browser's storage rather than into a file, since a page cannot
  write its own source. `config.js` holds the defaults, and a slider that has been
  moved stores only its difference from them.
- **The layout scales to the window.** Every spatial setting is in pixels for a
  1920x1080 window, which is what the desktop always has. The page multiplies the
  spatial constants by `min(width/1920, height/1080)`, clamped to 0.15..1.6, so
  the row fits a narrow browser window instead of running off the edge. At
  1920x1080 that factor is 1 and the picture is the desktop picture.
- **The silent state is a black page.** `MIN_BALL_SIZE` is 0, so with no audio
  every ball has a radius of 0. The hint line is the only thing on screen until
  something plays.

### Tests

```bash
cd web
node tests/analyser_test.mjs    # FFT, band map, gate, pan, frame scaling, physics
node tests/parity_check.mjs     # this port against the Python, frame by frame
```

`tests/parity_reference.py` is the analysis half of `fizzualizer.py` with the
capture removed, kept as the reference the port is measured against. The parity
check runs it in the project venv and compares 80 frames of band, pan, gate and
reference values. Bands whose true content is zero are excluded and counted
separately. Two FFTs sum in different orders, so a band sitting on the
cancellation noise floor agrees in character rather than in digits.

## Files

| File | What |
|------|------|
| `fizzualizer.py` | Main app (~1030 lines) |
| `overlay.py` | The config sliders: layout, mouse, drawing, and the write-back |
| `config.py` | All visualizer settings, 45 of them |
| `run.sh` | Launcher (creates and uses `.venv`) |
| `shell.nix` | Nix environment, alternative to `run.sh` |
| `fizzualizer.desktop` | Desktop entry template (`@EXEC@` / `@PATH@` filled at install) |
| `install-desktop.sh` | Installs the desktop entry and icon for the current user |
| `icons/fizzualizer.svg` | App icon source (no background plate) |
| `icons/fizzualizer.png` | Generated from the SVG; used as the window icon |
| `web/` | The browser build: `index.html`, `main.js`, `dsp.js`, `physics.js`, `renderer.js`, `audio.js`, `config.js` |
| `web/tests/` | Node tests, and the Python reference they measure parity against |
| `@Resources/` + `Visualizer.ini` | Original Rainmeter source files (kept for reference) |

## Original

- **Author:** [undefinist](https://github.com/undefinist), Malody Hoe
- **Original skin:** [The Fizzualizer on DeviantArt](https://www.deviantart.com/undefinist/art/The-Fizzualizer-690602015), published 2017, last updated 2018
- **Rainmeter:** [rainmeter.net](https://www.rainmeter.net/)

There is no GitHub repository for the original skin. DeviantArt is where it was
published, and that page is the only canonical source. The Rainmeter project is not
connected to this port.
