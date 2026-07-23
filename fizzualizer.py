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
        self._block_bytes = cfg.FFT_SIZE * 4
        self._start_pwcat()

        # Pre-compute band binning indices
        self._freqs = np.fft.rfftfreq(cfg.FFT_SIZE, 1.0 / cfg.SAMPLE_RATE)
        log_min = math.log10(max(cfg.FREQ_MIN, 1))
        log_max = math.log10(max(cfg.FREQ_MAX, log_min + 0.1))
        edges = np.logspace(log_min, log_max, cfg.NUM_ITEMS + 1)
        self._band_idx = np.digitize(self._freqs, edges) - 1
        self._band_idx = np.clip(self._band_idx, 0, cfg.NUM_ITEMS - 1)

        self._window = np.hanning(cfg.FFT_SIZE)
        self._smoothed = np.zeros(cfg.NUM_ITEMS, dtype=np.float32)
        self._per_band_peak = np.ones(cfg.NUM_ITEMS, dtype=np.float32) * 1e-6

    def _start_pwcat(self):
        sink_name = _find_default_sink()
        if sink_name is None:
            print("ERROR: no audio sink found. Is PipeWire running?", file=sys.stderr)
            sys.exit(1)
        self._sink_name = sink_name
        print(f"Audio: {sink_name} (sink monitor)")
        try:
            self._proc = subprocess.Popen(
                ['pw-cat', '--record',
                 '--format', 'f32',
                 '--rate', str(cfg.SAMPLE_RATE),
                 '--channels', '1',
                 '--target', sink_name,
                 '--properties', '{"stream.capture.sink":true}',
                 '--latency', f'{cfg.FFT_SIZE * 1000 // cfg.SAMPLE_RATE}ms',
                 '-'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=self._block_bytes * 4,
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
        if self._proc is None or self._proc.stdout is None:
            return None
        try:
            raw = self._proc.stdout.read(self._block_bytes)
        except Exception:
            return None
        if len(raw) < self._block_bytes:
            return None
        return np.frombuffer(raw, dtype=np.float32).copy()

    def get_bands(self):
        """Return smoothed per-band amplitudes [0,1]."""
        data = self.read_block()
        if data is None or len(data) < cfg.FFT_SIZE:
            return self._smoothed.copy()

        spectrum = np.fft.rfft(data * self._window)
        mag = np.abs(spectrum)

        counts = np.bincount(self._band_idx, minlength=cfg.NUM_ITEMS).astype(np.float32)
        sums = np.bincount(self._band_idx, weights=mag, minlength=cfg.NUM_ITEMS)
        raw = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
        raw = np.nan_to_num(raw, nan=0.0, posinf=0.0, neginf=0.0)
        # Per-band adaptive normalization (each band tracks its own peak)
        # This prevents bass from drowning out treble
        decay = 0.9995  # slow decay so peaks hold briefly
        self._per_band_peak = np.maximum(raw, self._per_band_peak * decay)
        self._per_band_peak = np.maximum(self._per_band_peak, 1e-6)
        raw = raw / self._per_band_peak
        raw = np.clip(raw, 0.0, 1.0)

        sens = 0.5 + cfg.SENSITIVITY / 100.0 * 1.5
        raw = np.clip(raw * sens, 0.0, 1.0)

        rising = raw > self._smoothed
        self._smoothed[rising] += cfg.ATTACK * (raw[rising] - self._smoothed[rising])
        self._smoothed[~rising] += cfg.DECAY * (raw[~rising] - self._smoothed[~rising])
        return self._smoothed.copy()


# =========================================================================
# MPRIS play/pause toggle — targets the most recently active player
# =========================================================================

def _toggle_mpris():
    """Toggle play/pause on the most recently active MPRIS player.

    Priority: Playing > Paused > Stopped. Among players with the same
    status, the one listed first by playerctl wins.
    """
    try:
        players = subprocess.check_output(
            ['playerctl', '-l'], text=True, timeout=2,
        ).strip().split()
    except Exception:
        return
    if not players:
        return

    # Priority buckets
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

    target = playing[0] if playing else (paused[0] if paused else (stopped[0] if stopped else None))
    if target is None:
        return

    subprocess.Popen(
        ['playerctl', '--player', target, 'play-pause'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# =========================================================================
# Ball physics
# =========================================================================

class Ball:
    __slots__ = ('ox', 'oy', 'x', 'y')
    def __init__(self, ox, oy):
        self.ox = ox
        self.oy = oy
        self.x = ox
        self.y = oy


def create_balls():
    total_w = (cfg.NUM_ITEMS - 1) * cfg.SPACING_X
    total_h = cfg.SPACING_Y + cfg.MIN_BALL_SIZE * 2 + 20
    offx = (cfg.WINDOW_WIDTH - total_w) // 2
    offy = (cfg.WINDOW_HEIGHT - total_h) // 2
    return [
        Ball(offx + i * cfg.SPACING_X, offy + (0 if i % 2 == 0 else cfg.SPACING_Y))
        for i in range(cfg.NUM_ITEMS)
    ]


def collide(balls, bands, first, step):
    """Collision push + spring-back, ported from Fizzualizer.lua."""
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
                bx = bj.x + abs(dx) * step / d * (br + rj)
                by = bj.y + dy / d * (br + rj)
            j -= step
        bx -= (bx - balls[i].ox) * 0.1
        by -= (by - balls[i].oy) * 0.1
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

    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

    pygame.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK,
                                    pygame.GL_CONTEXT_PROFILE_CORE)

    flags = pygame.OPENGL | pygame.DOUBLEBUF
    if cfg.FULLSCREEN:
        flags |= pygame.FULLSCREEN
    screen = pygame.display.set_mode((cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT), flags)
    pygame.display.set_caption("Fizzualizer")

    ctx = moderngl.create_context()
    ctx.enable(moderngl.BLEND)

    w, h = cfg.WINDOW_WIDTH, cfg.WINDOW_HEIGHT

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

    # Audio
    audio = StreamCapture()

    # Balls
    balls = create_balls()

    # Pre-compute per-ball hue
    hues = [
        (cfg.HUE_START + (cfg.HUE_END - cfg.HUE_START) * (i / cfg.NUM_ITEMS)) / 360.0
        for i in range(cfg.NUM_ITEMS)
    ]

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 14)

    # Mouse auto-hide
    pygame.mouse.set_visible(True)
    last_mouse_pos = pygame.mouse.get_pos()
    mouse_last_move = time.time()

    # 2D overlay for FPS text (no HUD in OpenGL, use a small pygame surface)
    fps_surf = None
    running = True

    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_f:
                        pygame.display.toggle_fullscreen()
                    elif event.key == pygame.K_SPACE:
                        _toggle_mpris()
                elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                    pygame.mouse.set_visible(True)
                    mouse_last_move = time.time()

            bands = audio.get_bands()

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

            # FPS overlay (use pygame overlay surface)
            fps = clock.get_fps()
            if fps_surf is None or clock.get_rawtime() > 500:
                fps_surf = font.render(f"{fps:.0f} fps", True, (80, 80, 80))

            # Blit FPS via SDL2 texture overlay
            pygame.display.flip()
            clock.tick(cfg.FPS)

            # Blit overlay AFTER flip for cleaner timing
            if fps_surf:
                screen.blit(fps_surf, (8, 8))

            # Auto-hide cursor after delay
            if time.time() - mouse_last_move > cfg.MOUSE_HIDE_DELAY:
                pygame.mouse.set_visible(False)

    finally:
        audio.close()
        pygame.quit()


if __name__ == "__main__":
    run()
