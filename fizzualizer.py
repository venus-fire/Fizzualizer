#!/usr/bin/env python3
"""
Fizzualizer — GPU-accelerated audio visualizer
Port of undefinist's Rainmeter Fizzualizer for Linux/PipeWire

Audio: pw-cat --record + stream.capture.sink=true (system output, not mic)
Render: moderngl point sprites (single draw call for all 45 circles)
"""

import sys
import math
import os
import subprocess
import json
import signal
import threading
import time
import atexit

import numpy as np

import config as cfg


# =========================================================================
# Audio capture — pw-cat --record piped through subprocess
# =========================================================================

def _find_default_sink():
    """Return the node.name of the default audio sink."""
    try:
        raw = subprocess.check_output(['pw-dump'], text=True)
        data = json.loads(raw)
    except Exception as e:
        print(f"pw-dump failed: {e}", file=sys.stderr)
        return None

    best, best_prio = None, -1
    for obj in data:
        if obj.get('type') != 'PipeWire:Interface:Node':
            continue
        props = obj['info'].get('props', {})
        if props.get('media.class') != 'Audio/Sink':
            continue
        prio = int(props.get('priority.session', '0'))
        name = props.get('node.name', '')
        if prio > best_prio:
            best_prio = prio
            best = name
    return best


class StreamCapture:
    """Captures system audio via pw-cat --record (system output monitor)."""

    _processes = []

    def __init__(self):
        self._proc = None
        # Stereo, and a half-window hop so analyses overlap: a brief transient
        # lands inside two windows instead of possibly falling between them.
        self._channels = 2
        self._hop = cfg.FFT_SIZE // 2
        self._hop_bytes = self._hop * self._channels * 4
        self._ring = np.zeros((cfg.FFT_SIZE, self._channels), dtype=np.float32)
        self._start_pwcat()

        # Pre-compute band binning indices
        self._freqs = np.fft.rfftfreq(cfg.FFT_SIZE, 1.0 / cfg.SAMPLE_RATE)
        log_min = math.log10(max(cfg.FREQ_MIN, 1))
        log_max = math.log10(max(cfg.FREQ_MAX, log_min + 0.1))
        edges = np.logspace(log_min, log_max, cfg.NUM_ITEMS + 1)
        self._band_idx = np.digitize(self._freqs, edges) - 1
        self._band_idx = np.clip(self._band_idx, 0, cfg.NUM_ITEMS - 1)
        self._counts = np.bincount(self._band_idx,
                                   minlength=cfg.NUM_ITEMS).astype(np.float32)

        self._window = np.hanning(cfg.FFT_SIZE)
        self._smoothed = np.zeros(cfg.NUM_ITEMS, dtype=np.float32)
        self._pan = np.zeros(cfg.NUM_ITEMS, dtype=np.float32)
        self._per_band_peak = np.ones(cfg.NUM_ITEMS, dtype=np.float32) * 1e-6

    def _start_pwcat(self):
        sink_name = _find_default_sink()
        if sink_name is None:
            print("ERROR: no audio sink found. Is PipeWire running?", file=sys.stderr)
            sys.exit(1)
        self._sink_name = sink_name
        print(f"Audio: {sink_name} (sink monitor, {self._channels}ch)")
        try:
            self._proc = subprocess.Popen(
                ['pw-cat', '--record',
                 '--format', 'f32',
                 '--rate', str(cfg.SAMPLE_RATE),
                 '--channels', str(self._channels),
                 '--target', sink_name,
                 '--properties', '{"stream.capture.sink":true}',
                 '--latency', f'{self._hop * 1000 // cfg.SAMPLE_RATE}ms',
                 '-'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=self._hop_bytes * 4,
            )
        except FileNotFoundError:
            print("ERROR: pw-cat not found. Install pipewire.jack.", file=sys.stderr)
            raise
        StreamCapture._processes.append(self._proc)
        self._register_atexit()
        time.sleep(0.5)

    def _register_atexit(self):
        if not hasattr(StreamCapture, '_atexit_done'):
            StreamCapture._atexit_done = True
            @atexit.register
            def _cleanup_all():
                for p in list(StreamCapture._processes):
                    try:
                        p.terminate()
                        p.wait(timeout=2)
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass

    def close(self):
        if self._proc:
            try:
                StreamCapture._processes.remove(self._proc)
            except ValueError:
                pass
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    def __del__(self):
        self.close()

    def read_block(self):
        """Read one hop of interleaved stereo, or None on a short read."""
        if self._proc is None or self._proc.stdout is None:
            return None
        try:
            raw = self._proc.stdout.read(self._hop_bytes)
        except Exception:
            return None
        if len(raw) < self._hop_bytes:
            return None
        return np.frombuffer(raw, dtype=np.float32).reshape(-1, self._channels).copy()

    def get_bands(self):
        """Return (per-band amplitudes [0,1], per-band pan [-1 left .. +1 right]).

        The hop is half a window, so consecutive analyses overlap and a short
        transient cannot slip between them.
        """
        chunk = self.read_block()
        if chunk is not None:
            n = chunk.shape[0]
            if n >= cfg.FFT_SIZE:
                self._ring = chunk[-cfg.FFT_SIZE:].copy()
            else:
                self._ring = np.concatenate((self._ring[n:], chunk), axis=0)

        left = self._ring[:, 0] * self._window
        right = self._ring[:, 1] * self._window
        mag_l = np.abs(np.fft.rfft(left))
        mag_r = np.abs(np.fft.rfft(right))

        mean_l = np.divide(
            np.bincount(self._band_idx, weights=mag_l, minlength=cfg.NUM_ITEMS),
            self._counts, out=np.zeros(cfg.NUM_ITEMS), where=self._counts > 0)
        mean_r = np.divide(
            np.bincount(self._band_idx, weights=mag_r, minlength=cfg.NUM_ITEMS),
            self._counts, out=np.zeros(cfg.NUM_ITEMS), where=self._counts > 0)

        # level: the mean of the two channels, so the scale matches a downmix
        raw = 0.5 * (mean_l + mean_r)
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)

        # pan: how much of this band's energy sits in the right ear
        total = mean_l + mean_r
        pan = np.divide(mean_r - mean_l, total,
                        out=np.zeros(cfg.NUM_ITEMS), where=total > 1e-9)
        pan = np.nan_to_num(pan, nan=0.0, posinf=0.0, neginf=0.0)

        # Per-band adaptive normalization (each band tracks its own peak)
        # This prevents bass from drowning out treble. The release is slow
        # enough to ride out a note but fast enough that a quiet passage is
        # not squashed for ten seconds by the loud one before it.
        decay = cfg.PEAK_DECAY
        self._per_band_peak = np.maximum(raw, self._per_band_peak * decay)
        self._per_band_peak = np.maximum(self._per_band_peak, 1e-6)
        raw = raw / self._per_band_peak
        raw = np.clip(raw, 0.0, 1.0)

        sens = 0.5 + cfg.SENSITIVITY / 100.0 * 1.5
        raw = np.clip(raw * sens, 0.0, 1.0)

        rising = raw > self._smoothed
        self._smoothed[rising] += cfg.ATTACK * (raw[rising] - self._smoothed[rising])
        self._smoothed[~rising] += cfg.DECAY * (raw[~rising] - self._smoothed[~rising])

        # Pan, weighted by the band so a quiet band's noisy balance cannot yank
        # its ball about, then smoothed so the ball is not chasing a per-frame
        # twitch in the stereo image.
        target = pan * self._smoothed
        self._pan += cfg.PAN_SMOOTH * (target - self._pan)
        return self._smoothed.copy(), self._pan.copy()


# =========================================================================
# MPRIS control — play/pause, track skip, and the now-playing line
# =========================================================================

_last_mpris_target = None  # remember which player we last commanded


def _pick_player(remember=True):
    """Return the player name to command, or None if there is none.

    Priority: last-commanded player > currently Playing > Paused > Stopped.
    This prevents commanding a wrong paused player when the one you were
    just interacting with is also paused.
    """
    global _last_mpris_target

    try:
        players = subprocess.check_output(
            ['playerctl', '-l'], text=True, timeout=2,
        ).strip().split()
    except Exception:
        return None
    if not players:
        return None

    playing, paused, stopped = [], [], []
    for p in players:
        try:
            status = subprocess.check_output(
                ['playerctl', '--player', p, 'status'],
                text=True, timeout=2,
            ).strip()
        except Exception:
            continue
        if status == 'Playing':
            playing.append(p)
        elif status == 'Paused':
            paused.append(p)
        else:
            stopped.append(p)

    # Pick target: last-used > currently Playing > Paused > Stopped
    if _last_mpris_target in players:
        target = _last_mpris_target
    elif playing:
        target = playing[0]
    elif paused:
        target = paused[0]
    elif stopped:
        target = stopped[0]
    else:
        return None

    if remember:
        _last_mpris_target = target
    return target


def _mpris_command(action):
    """Send one playerctl command to the selected player."""
    target = _pick_player()
    if target is None:
        return
    subprocess.Popen(
        ['playerctl', '--player', target, action],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _toggle_mpris():
    _mpris_command('play-pause')


def _mpris_next():
    _mpris_command('next')


def _mpris_previous():
    _mpris_command('previous')


def _now_playing():
    """'Artist - Title' for the selected player, or '' when there is none."""
    target = _pick_player(remember=False)
    if target is None:
        return ''
    try:
        line = subprocess.check_output(
            ['playerctl', '--player', target, 'metadata', '--format',
             '{{artist}} - {{title}}'],
            text=True, timeout=2,
        ).strip()
    except Exception:
        return ''
    # drop empty fields, so a missing artist does not leave a leading dash
    return ' - '.join(part.strip() for part in line.split(' - ') if part.strip())


def _volume_step(delta):
    """Change the default sink volume by delta percent (1 means one percent)."""
    sign = '+' if delta > 0 else '-'
    amount = abs(delta)
    devnull = subprocess.DEVNULL
    try:
        # WirePlumber: the sign goes after the percent sign
        subprocess.Popen(
            ['wpctl', 'set-volume', '@DEFAULT_AUDIO_SINK@', f'{amount}%{sign}'],
            stdout=devnull, stderr=devnull,
        )
        return
    except FileNotFoundError:
        pass
    except Exception:
        return
    try:
        # PulseAudio fallback: the sign goes before the number
        subprocess.Popen(
            ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{sign}{amount}%'],
            stdout=devnull, stderr=devnull,
        )
    except Exception:
        pass


class NowPlaying:
    """Polls the selected MPRIS player off the render thread."""

    def __init__(self, interval=1.5):
        self._text = ''
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._thread.start()

    def _loop(self, interval):
        while not self._stop.wait(interval):
            try:
                text = _now_playing()
            except Exception:
                text = ''
            with self._lock:
                self._text = text

    def text(self):
        with self._lock:
            return self._text

    def stop(self):
        self._stop.set()


# =========================================================================
# Ball physics
# =========================================================================

class Ball:
    __slots__ = ('ox', 'oy', 'x', 'y', 'base_y')
    def __init__(self, ox, oy):
        self.ox = ox
        self.oy = oy
        self.x = ox
        self.y = oy
        self.base_y = oy   # rest height; oy moves with the stereo pan


def create_balls(width=None, height=None):
    """Rest positions for every ball, centred in width x height."""
    width = cfg.WINDOW_WIDTH if width is None else width
    height = cfg.WINDOW_HEIGHT if height is None else height
    total_w = (cfg.NUM_ITEMS - 1) * cfg.SPACING_X
    total_h = cfg.SPACING_Y + cfg.MIN_BALL_SIZE * 2 + 20
    offx = (width - total_w) // 2
    offy = (height - total_h) // 2
    return [
        Ball(offx + i * cfg.SPACING_X, offy + (0 if i % 2 == 0 else cfg.SPACING_Y))
        for i in range(cfg.NUM_ITEMS)
    ]


def collide(balls, bands, first, step):
    """Collision push + spring-back, ported from Fizzualizer.lua.

    The skin sets a colliding ball's position to the contact point outright,
    which pins it to whatever it touched: a big ball then sits frozen while its
    neighbours move. This pushes by a fraction of the overlap instead, so a
    ball keeps sliding out of the way and stays live.
    """
    last = cfg.NUM_ITEMS if step == 1 else 1
    for i in range(first + step, last, step):
        bx, by = balls[i].x, balls[i].y
        br = bands[i] * (cfg.MAX_COLLIDER_SIZE - cfg.MIN_BALL_SIZE) + cfg.MIN_BALL_SIZE
        j = i - step
        while (step == 1 and j >= first) or (step == -1 and j <= first):
            bj = balls[j]
            rj = bands[j] * (cfg.MAX_COLLIDER_SIZE - cfg.MIN_BALL_SIZE) + cfg.MIN_BALL_SIZE
            dx, dy = bx - bj.x, by - bj.y
            d2 = dx * dx + dy * dy
            if d2 < (br + rj) * (br + rj) and d2 > 1e-8:
                d = math.sqrt(d2)
                overlap = ((br + rj) - d) * cfg.COLLIDE_PUSH
                bx += abs(dx) * step / d * overlap
                by += dy / d * overlap
            j -= step
        bx -= (bx - balls[i].ox) * cfg.SPRING_BACK
        by -= (by - balls[i].oy) * cfg.SPRING_BACK
        if abs(bx - balls[i].ox) < 0.1:
            bx = balls[i].ox
        if abs(by - balls[i].oy) < 0.1:
            by = balls[i].oy
        balls[i].x, balls[i].y = bx, by


# =========================================================================
# OpenGL rendering (instanced quads — no point size limit)
# =========================================================================

VERTEX_SHADER = """
#version 330
in vec2 in_offset;
in vec2 in_center;
in float in_radius;
in vec3 in_color;

out vec3 v_color;
out vec2 v_uv;

uniform vec2 u_resolution;

void main() {
    vec2 pos = in_center + in_offset * max(in_radius * 2.0, 1.0);
    vec2 clip = (pos / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
    v_uv = in_offset;
    v_color = in_color;
}
"""

FRAGMENT_SHADER = """
#version 330
in vec3 v_color;
in vec2 v_uv;
out vec4 f_color;

void main() {
    float dist = length(v_uv);
    if (dist > 0.5) discard;
    f_color = vec4(v_color, 1.0);
}
"""

# 4 vertices of a unit quad (centered at origin)
QUAD_VERTS = np.array([
    -0.5, -0.5,
     0.5, -0.5,
     0.5,  0.5,
    -0.5,  0.5,
], dtype=np.float32)

# 6 indices for 2 triangles (clockwise)
QUAD_INDICES = np.array([
    0, 1, 2,
    0, 2, 3,
], dtype=np.int32)

# -------------------------------------------------------------------------
# Text overlay: one textured quad in the bottom right corner. pygame renders
# the string into a surface, that becomes a GL texture.
# -------------------------------------------------------------------------

TEXT_VERTEX_SHADER = """
#version 330
in vec2 in_pos;          // unit quad, 0..1
uniform vec4 u_rect;     // x, y, w, h in pixels, top-left origin
uniform vec2 u_resolution;

out vec2 v_uv;

void main() {
    vec2 pos = u_rect.xy + in_pos * u_rect.zw;
    vec2 clip = (pos / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
    // the texture was uploaded bottom-up, so flip v
    v_uv = vec2(in_pos.x, 1.0 - in_pos.y);
}
"""

TEXT_FRAGMENT_SHADER = """
#version 330
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 f_color;

void main() {
    vec4 texel = texture(u_tex, v_uv);
    if (texel.a < 0.02) discard;
    f_color = texel;
}
"""

TEXT_QUAD_VERTS = np.array([
    0.0, 0.0,
    1.0, 0.0,
    1.0, 1.0,
    0.0, 1.0,
], dtype=np.float32)

TEXT_MARGIN = 16  # pixels from the window edge
TEXT_COLOR = (190, 190, 190)


def hsv_to_rgb(h, s, v):
    """HSV → RGB float 0-1."""
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i %= 6
    if i == 0:
        return v, t, p
    elif i == 1:
        return q, v, p
    elif i == 2:
        return p, v, t
    elif i == 3:
        return p, q, v
    elif i == 4:
        return t, p, v
    else:
        return v, p, q


def run():
    import pygame
    import moderngl
    from pygame._sdl2.video import Window

    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK,
                                    pygame.GL_CONTEXT_PROFILE_CORE)

    # Window icon: this is what the titlebar and taskbar draw, separately from
    # the .desktop file's icon.
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'icons', 'fizzualizer.png')
    try:
        pygame.display.set_icon(pygame.image.load(icon_path))
    except Exception as e:
        print(f"Icon not loaded from {icon_path}: {e}", file=sys.stderr)

    flags = pygame.OPENGL | pygame.DOUBLEBUF | pygame.RESIZABLE
    if cfg.FULLSCREEN:
        flags |= pygame.FULLSCREEN
        desktop = pygame.display.Info()
        w, h = desktop.current_w, desktop.current_h
        if w <= 0 or h <= 0:
            # Wayland can report 0 before the first window exists
            w, h = cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT
    else:
        w, h = cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT
    screen = pygame.display.set_mode((w, h), flags)
    pygame.display.set_caption("Fizzualizer")

    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)

    # SDL's own window size is the only trustworthy one here: under XWayland
    # pygame's surface size and moderngl's cached framebuffer size both stay
    # at whatever the window was created with.
    window = Window.from_display_module()
    w, h = window.size
    print(f"Display: {w}x{h} {'fullscreen' if cfg.FULLSCREEN else 'windowed'}")

    # Compile shader program
    prog = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
    prog['u_resolution'].write(np.array([w, h], dtype=np.float32).tobytes())

    # Full index buffer: 6 indices per ball × 45 balls
    ibo_data = np.tile(QUAD_INDICES, cfg.NUM_ITEMS)
    # Adjust indices for each ball
    for i in range(1, cfg.NUM_ITEMS):
        ibo_data[i * 6:(i + 1) * 6] += i * 4
    ibo = ctx.buffer(ibo_data.astype(np.int32).tobytes())

    # VBO: 4 verts × 8 floats per ball = all balls in one flat array
    # Each vert: [offset.x, offset.y, center.x, center.y, radius, R, G, B]
    vbo_data = np.zeros(cfg.NUM_ITEMS * 4 * 8, dtype=np.float32)
    vbo = ctx.buffer(vbo_data)
    vao = ctx.vertex_array(
        prog,
        [(vbo, '2f 2f 1f 3f', 'in_offset', 'in_center', 'in_radius', 'in_color')],
        index_buffer=ibo,
    )

    # Text overlay program and its quad
    text_prog = ctx.program(vertex_shader=TEXT_VERTEX_SHADER,
                            fragment_shader=TEXT_FRAGMENT_SHADER)
    text_prog['u_resolution'].write(np.array([w, h], dtype=np.float32).tobytes())
    text_vbo = ctx.buffer(TEXT_QUAD_VERTS.tobytes())
    text_ibo = ctx.buffer(np.array([0, 1, 2, 0, 2, 3], dtype=np.int32).tobytes())
    text_vao = ctx.vertex_array(text_prog, [(text_vbo, '2f', 'in_pos')],
                                index_buffer=text_ibo)
    text_tex = None
    text_size = (0, 0)
    text_shown = None

    # Audio
    audio = StreamCapture()

    # Balls
    balls = create_balls(w, h)

    # Pre-compute per-ball hue
    hues = [
        (cfg.HUE_START + (cfg.HUE_END - cfg.HUE_START) * (i / cfg.NUM_ITEMS)) / 360.0
        for i in range(cfg.NUM_ITEMS)
    ]

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 22)
    now_playing = NowPlaying()

    # Mouse auto-hide
    pygame.mouse.set_visible(True)
    mouse_last_pos = pygame.mouse.get_pos()
    mouse_last_move = time.time()

    # Held volume keys step on their own timer
    volume_key = None
    volume_next = 0.0

    running = True

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        running = False
                    elif event.key in (pygame.K_f, pygame.K_F11):
                        pygame.display.toggle_fullscreen()
                        if not (screen.get_flags() & pygame.FULLSCREEN):
                            # leaving fullscreen: back to the configured size
                            try:
                                window.size = (cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT)
                            except Exception:
                                pass
                    elif event.key == pygame.K_SPACE:
                        _toggle_mpris()
                    elif event.key == pygame.K_RIGHT:
                        _mpris_next()
                    elif event.key == pygame.K_LEFT:
                        _mpris_previous()
                    elif event.key == pygame.K_UP:
                        _volume_step(cfg.VOLUME_STEP)
                        volume_key = pygame.K_UP
                        volume_next = time.time() + cfg.VOLUME_REPEAT_DELAY
                    elif event.key == pygame.K_DOWN:
                        _volume_step(-cfg.VOLUME_STEP)
                        volume_key = pygame.K_DOWN
                        volume_next = time.time() + cfg.VOLUME_REPEAT_DELAY
                elif event.type == pygame.KEYUP:
                    if event.key in (pygame.K_UP, pygame.K_DOWN):
                        volume_key = None
                elif event.type == pygame.WINDOWFOCUSLOST:
                    # a held key never delivers its KEYUP once focus is gone
                    volume_key = None
                elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                    pygame.mouse.set_visible(True)
                    mouse_last_move = time.time()

            # Track the window size: a resize or fullscreen toggle moves the
            # centre, so the viewport, the projection uniform and the ball rest
            # positions all have to follow.
            size = tuple(window.size)
            if size != (w, h):
                w, h = size
                print(f"Display: {w}x{h}")
                ctx.viewport = (0, 0, w, h)
                prog['u_resolution'].write(np.array([w, h], dtype=np.float32).tobytes())
                text_prog['u_resolution'].write(np.array([w, h], dtype=np.float32).tobytes())
                balls = create_balls(w, h)
                text_shown = None  # re-render the label for the new width

            # Held volume keys: step at a steady rate, counted from elapsed
            # time so the pace does not depend on the frame rate. pygame's own
            # key repeat is off, and switching it on would repeat the track
            # keys and the space bar too. The render loop runs at the audio
            # block rate, well under 60fps, so a frame can carry several steps.
            if volume_key is not None:
                now = time.time()
                steps = int((now - volume_next) / cfg.VOLUME_REPEAT_INTERVAL)
                if steps > 0:
                    steps = min(steps, 20)  # a stalled frame must not jump the volume
                    delta = steps * cfg.VOLUME_STEP
                    _volume_step(delta if volume_key == pygame.K_UP else -delta)
                    volume_next += steps * cfg.VOLUME_REPEAT_INTERVAL

            bands, pan = audio.get_bands()

            # Stereo: bands leaning left pull their ball up, right push it down.
            # This moves the rest height, so the spring in collide() follows it
            # elastically instead of teleporting the ball.
            for i, ball in enumerate(balls):
                ball.oy = ball.base_y + pan[i] * cfg.STEREO_SHIFT

            # Physics
            mid = cfg.NUM_ITEMS // 2
            collide(balls, bands, mid, -1)
            collide(balls, bands, mid, 1)

            # Pack VBO: 4 verts per ball × 8 floats = [ox,oy, cx,cy, radius, R,G,B]
            for i, ball in enumerate(balls):
                bv = bands[i]
                radius = bv * (cfg.MAX_BALL_SIZE - cfg.MIN_BALL_SIZE) + cfg.MIN_BALL_SIZE
                if math.isnan(radius) or radius < 1:
                    radius = 0.0
                    r, g, b = 0.0, 0.0, 0.0
                else:
                    if bv == 0:
                        s, v = cfg.SAT_ZERO, cfg.VAL_ZERO
                    else:
                        s = cfg.SAT_MIN + (cfg.SAT_MAX - cfg.SAT_MIN) * bv
                        v = cfg.VAL_MIN + (cfg.VAL_MAX - cfg.VAL_MIN) * bv
                    r, g, b = hsv_to_rgb(hues[i], max(0, min(1, s)), max(0, min(1, v)))

                base = i * 4 * 8
                cx, cy = ball.x, ball.y
                for j, (ox, oy) in enumerate([(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]):
                    idx = base + j * 8
                    vbo_data[idx] = ox
                    vbo_data[idx + 1] = oy
                    vbo_data[idx + 2] = cx
                    vbo_data[idx + 3] = cy
                    vbo_data[idx + 4] = radius
                    vbo_data[idx + 5] = r
                    vbo_data[idx + 6] = g
                    vbo_data[idx + 7] = b

            # Upload and draw (270 indexed vertices = 45 balls × 6 indices)
            vbo.write(vbo_data.tobytes())
            ctx.clear(0.0, 0.0, 0.0, 1.0)
            vao.render(moderngl.TRIANGLES, vertices=cfg.NUM_ITEMS * 6)

            # Now-playing line, bottom right. Re-rendered only when the text
            # or the window width changes.
            label = now_playing.text()
            if label != text_shown:
                text_shown = label
                if text_tex is not None:
                    text_tex.release()
                    text_tex = None
                if label:
                    max_w = max(64, w - 2 * TEXT_MARGIN)
                    while label and font.size(label)[0] > max_w:
                        label = label[:-1]
                    if label:
                        surf = font.render(label, True, TEXT_COLOR)
                        text_size = surf.get_size()
                        text_tex = ctx.texture(text_size, 4,
                                               pygame.image.tostring(surf, 'RGBA', True))
                        text_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)

            if text_tex is not None:
                tw, th = text_size
                text_prog['u_rect'].write(np.array(
                    [w - tw - TEXT_MARGIN, h - th - TEXT_MARGIN, tw, th],
                    dtype=np.float32).tobytes())
                text_tex.use(0)
                text_prog['u_tex'].value = 0
                text_vao.render(moderngl.TRIANGLES, vertices=6)

            pygame.display.flip()
            clock.tick(cfg.FPS)

            # Auto-hide cursor after delay
            if time.time() - mouse_last_move > cfg.MOUSE_HIDE_DELAY:
                pygame.mouse.set_visible(False)

    finally:
        now_playing.stop()
        audio.close()
        pygame.quit()


if __name__ == "__main__":
    run()
