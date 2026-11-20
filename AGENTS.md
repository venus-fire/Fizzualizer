# Fizzualizer: agent contract

A real-time PipeWire audio visualizer in Python and OpenGL. `README.md` is the
project documentation and describes the design, the controls, every config setting and
the port's history. This file is what an agent needs to change the code without
breaking the copy that runs here.

Repo: https://github.com/venus-fire/Fizzualizer, branch `main`, remote `origin`.

## Running it

```sh
./run.sh                    # creates and uses .venv, then launches
./install-desktop.sh        # refresh the desktop entry after moving the checkout
```

`run.sh` builds `.venv` on a uv-provided 3.13, falling back to `python3 -m venv` only
when uv is absent. The fallback is the fragile path: a venv on `/usr/bin/python3` stops
importing its own packages when the image moves its python minor, and it looks like a
broken app rather than a broken environment. If `.venv` fails that way, delete it and
re-run with uv present.

`shell.nix` is the Nix route, for a machine that has Nix. This host does not.

## Layout

| file | role |
|---|---|
| `fizzualizer.py` | the app: capture, analysis, physics, render loop |
| `config.py` | every tunable, mirroring the Rainmeter `Visualizer.ini` |
| `overlay.py` | the slider panel drawn over the visual |
| `run.sh` | venv bootstrap and launch |
| `install-desktop.sh` | fills the `@EXEC@`/`@PATH@` placeholders and installs entry plus icon |
| `fizzualizer.desktop` | carries the placeholders, never the real path |
| `Visualizer.ini`, `@Resources` | the Rainmeter originals, kept for reference |
| `web/` | the browser build; see its own section below |

The desktop entry's `StartupWMClass` is `fizzualizer.py`, which is what SDL reports.
Changing the launcher name breaks the menu icon pairing.

## The web build

`web/` is a second target for the same visualizer, served as static files. It is
not a wrapper around the Python: `web/dsp.js` is the analysis, `web/physics.js` is
the collision code, and `web/renderer.js` is the instanced draw, all ported. The
desktop app is unaffected by it and shares no runtime with it.

Two rules, because the two builds can drift apart silently:

- **`web/config.js` and `config.py` are separate files and both are authoritative
  for their own build.** The web copy carries only the knobs the browser reads.
  When a shared knob changes meaning, change both and say so in the commit
  message. Do not generate one from the other: `config.py` is imported by the
  desktop app and is also written by the desktop slider panel, so it is not a
  source of truth the page can safely parse.
- **Do not weaken the parity test to make it pass.** `node tests/parity_check.mjs`
  compares the port against `tests/parity_reference.py`, which is the analysis
  half of `fizzualizer.py` with capture removed. If it fails, either the port
  drifted or the reference did; find out which. The one permitted exclusion is
  documented in the test: bands sitting on the FFT cancellation noise floor.

The page is served at `/fizzualizer/` by the home-gateway Caddy router from this
directory, so anything added here is published. Test harness files live under
`web/tests/`, which the route answers with 404.

The tab icon comes from `icons/fizzualizer.svg`, served by a dedicated
`/fizzualizer/favicon.svg` route so the launcher, the window and the tab all use
one file. `web/index.html` must keep its `link rel="icon"`: without it the
browser asks for `/favicon.ico` at the domain root, which is Immich, and the tab
shows Immich's icon.

Verification for this target is in two halves, and both are required before
calling a change done: the node tests, and a real browser. A headless DOM has no
WebGL and no audio device, so the render claim has to come from a browser that
draws actual pixels, the same way the desktop claim comes from the real window.

```sh
cd web && node tests/analyser_test.mjs && node tests/parity_check.mjs
```

## Traps that have cost time already

Capture must not be piped. Output written to a pipe rather than a terminal produced a
quarter of a percent NaN and runaway samples, so a probe that redirects stdout changes
what is being measured.

The GL context is a real window. There is no headless path worth trusting for a layout
or render claim: verify on the desktop, and measure rather than eyeball. The
`headless-render-verification` and `pygame-gl-desktop-app` skills carry the working
method for this app.

Frame-rate dependent constants are written for the nominal rate; the README's Motion
and pacing sections explain the scaling. Changing `FPS` without revisiting them changes
the physics.

## Rules

Update `config.py` and the README together. The README documents every setting, and a
knob that exists in code but not there is a knob nobody can find.

Do not reformat `Visualizer.ini` or `@Resources`. They are the port's reference material.

Commit style follows the existing history: one imperative subject line, lowercase,
no prefix tags.
