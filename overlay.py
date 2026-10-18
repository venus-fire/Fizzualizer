"""Config sliders drawn over the visualiser.

Each slider edits a value in `config.py` live and the changed lines are written
back to that file on exit, so config.py stays the single source of truth and
stays hand-editable.

Everything is drawn with three instanced quads programs: rects for the panel
and the tracks, discs for the knobs, and one textured quad per label.
"""

import re

import numpy as np

# (attribute, label, low, high, step, integer)
SLIDERS = [
    ('SENSITIVITY',       'sensitivity',   0.0,   100.0,   1.0,   True),
    ('MAX_BALL_SIZE',     'max ball',      20.0,  600.0,   5.0,   True),
    ('MIN_BALL_SIZE',     'min ball',      0.0,   60.0,    1.0,   True),
    ('MAX_COLLIDER_SIZE', 'collider',      10.0,  500.0,   5.0,   True),
    ('COLLIDE_PUSH',      'collide push',  0.0,   1.0,     0.01,  False),
    ('SPRING_BACK',       'spring back',   0.0,   0.3,     0.005, False),
    ('STEREO_SHIFT',      'stereo shift',  0.0,   400.0,   5.0,   True),
    ('PAN_SMOOTH',        'pan smooth',    0.01,  1.0,     0.01,  False),
    ('ATTACK',            'attack',        0.01,  1.0,     0.01,  False),
    ('DECAY',             'decay',         0.5,   1.0,     0.005, False),
    ('PEAK_DECAY',        'peak decay',    0.9,   0.9999,  0.0005, False),
    ('SPACING_X',         'spacing x',     2.0,   80.0,    1.0,   True),
    ('SPACING_Y',         'spacing y',     0.0,   80.0,    1.0,   True),
    ('HUE_START',         'hue start',     0.0,   360.0,   1.0,   True),
    ('HUE_END',           'hue end',       0.0,   360.0,   1.0,   True),
    ('SAT_MIN',           'sat min',       0.0,   1.0,     0.01,  False),
    ('SAT_MAX',           'sat max',       0.0,   1.0,     0.01,  False),
    ('VAL_MIN',           'val min',       0.0,   1.0,     0.01,  False),
    ('VAL_MAX',           'val max',       0.0,   1.0,     0.01,  False),
    ('FPS',               'fps',           0.0,   240.0,   1.0,   True),
    ('VOLUME_STEP',       'volume step',   1.0,   10.0,    1.0,   True),
    ('MOUSE_HIDE_DELAY',  'mouse hide',    0.0,   20.0,    1.0,   True),
    ('UI_HOVER_ZONE',     'hover zone',    0.0,   1.0,     0.01,  False),
    ('UI_ALPHA',          'ui alpha',      0.05,  1.0,     0.05,  False),
]

# Attributes that need the app to rebuild something when they change
GEOMETRY_ATTRS = {'SPACING_X', 'SPACING_Y', 'MIN_BALL_SIZE'}
HUE_ATTRS = {'HUE_START', 'HUE_END'}

PAD = 16            # panel margin
GAP = 18            # between columns
CELL_H = 38         # one slider row
HEADER_H = 30
TRACK_H = 6
KNOB_R = 5
LABEL_PX = 19
TEXT_MARGIN = 8     # label offset inside the cell

RECT_VERTEX = """
#version 330
in vec2 in_corner;      // unit quad 0..1
in vec4 in_rect;        // x, y, w, h in pixels, top-left origin
in vec4 in_color;
uniform vec2 u_resolution;
out vec4 v_color;
void main() {
    vec2 pos = in_rect.xy + in_corner * in_rect.zw;
    vec2 clip = (pos / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
    v_color = in_color;
}
"""

RECT_FRAGMENT = """
#version 330
in vec4 v_color;
out vec4 f_color;
void main() { f_color = v_color; }
"""

DISC_VERTEX = """
#version 330
in vec2 in_offset;
in vec2 in_center;
in float in_radius;
in vec4 in_color;
uniform vec2 u_resolution;
out vec4 v_color;
out vec2 v_uv;
void main() {
    vec2 pos = in_center + in_offset * max(in_radius * 2.0, 1.0);
    vec2 clip = (pos / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
    v_uv = in_offset;
    v_color = in_color;
}
"""

DISC_FRAGMENT = """
#version 330
in vec4 v_color;
in vec2 v_uv;
out vec4 f_color;
void main() {
    if (length(v_uv) > 0.5) discard;
    f_color = v_color;
}
"""

TEXT_VERTEX = """
#version 330
in vec2 in_pos;
uniform vec4 u_rect;
uniform vec2 u_resolution;
out vec2 v_uv;
void main() {
    vec2 pos = u_rect.xy + in_pos * u_rect.zw;
    vec2 clip = (pos / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
    v_uv = vec2(in_pos.x, 1.0 - in_pos.y);
}
"""

TEXT_FRAGMENT = """
#version 330
in vec2 v_uv;
uniform sampler2D u_tex;
uniform float u_alpha;
out vec4 f_color;
void main() {
    vec4 texel = texture(u_tex, v_uv);
    if (texel.a < 0.02) discard;
    f_color = vec4(texel.rgb, texel.a * u_alpha);
}
"""

QUAD = np.array([0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 1.0],
                dtype=np.float32)
DISC_QUAD = np.array([-0.5, -0.5, 0.5, -0.5, 0.5, 0.5,
                      -0.5, -0.5, 0.5, 0.5, -0.5, 0.5], dtype=np.float32)

MAX_INSTANCES = 256
PANEL_BG = (26, 26, 34)
TRACK_BG_ALPHA = 0.18
TRACK_BG = (255, 255, 255)
TEXT_COLOR = (215, 215, 228)
HEADER_COLOR = (150, 150, 168)


def _fmt(value, integer):
    if integer:
        return f'{int(round(value))}'
    text = f'{value:.4f}'.rstrip('0').rstrip('.')
    return text if text else '0'


class Overlay:
    """The slider panel. Owns its GL objects, the layout and the mouse."""

    def __init__(self, ctx, cfg, visible=False):
        self.ctx = ctx
        self.cfg = cfg
        self.visible = visible
        self.changed = set()      # attributes changed since the last frame
        self.dirty = set()        # every attribute touched, for the save
        self.dragging = None

        self.hot = None
        self._w = self._h = 0
        self._layout = {}          # name -> (track_x, track_y, track_w)
        self._textures = {}        # name -> (texture, (w, h), string)
        self._header_tex = None
        self._header_str = None
        self.info = ''             # shown in the header, set by the app

        self.rect_prog = ctx.program(vertex_shader=RECT_VERTEX,
                                     fragment_shader=RECT_FRAGMENT)
        self.corner_vbo = ctx.buffer(QUAD.tobytes())
        self.rect_vbo = ctx.buffer(reserve=MAX_INSTANCES * 8 * 4)
        self.rect_vao = ctx.vertex_array(
            self.rect_prog,
            [(self.corner_vbo, '2f', 'in_corner'),
             (self.rect_vbo, '4f 4f/i', 'in_rect', 'in_color')])

        self.disc_prog = ctx.program(vertex_shader=DISC_VERTEX,
                                     fragment_shader=DISC_FRAGMENT)
        self.disc_quad = ctx.buffer(DISC_QUAD.tobytes())
        self.disc_vbo = ctx.buffer(reserve=MAX_INSTANCES * 7 * 4)
        self.disc_vao = ctx.vertex_array(
            self.disc_prog,
            [(self.disc_quad, '2f', 'in_offset'),
             (self.disc_vbo, '2f 1f 4f/i', 'in_center', 'in_radius', 'in_color')])

        self.text_prog = ctx.program(vertex_shader=TEXT_VERTEX,
                                     fragment_shader=TEXT_FRAGMENT)
        self.text_vbo = ctx.buffer(QUAD.tobytes())
        self.text_vao = ctx.vertex_array(self.text_prog, [(self.text_vbo, '2f', 'in_pos')])

        import pygame
        self.font = pygame.font.SysFont("monospace", LABEL_PX)
        self.header_font = pygame.font.SysFont("monospace", LABEL_PX, bold=True)
        self._rects = np.zeros((MAX_INSTANCES, 8), dtype=np.float32)
        # 7 floats per instance, matching the '2f 1f 4f/i' vertex format: a
        # mismatch here makes every instance after the first read the wrong
        # bytes, and the knobs come out as giant white discs.
        self._discs = np.zeros((MAX_INSTANCES, 7), dtype=np.float32)

    # -- values ----------------------------------------------------------

    def value(self, name):
        return getattr(self.cfg, name)

    def _set(self, name, raw, integer):
        lo, hi, step = self._range(name)
        v = min(hi, max(lo, round(raw / step) * step))
        if integer:
            v = float(int(round(v)))
        if abs(v - getattr(self.cfg, name)) > 1e-9:
            setattr(self.cfg, name, v)
            self.changed.add(name)
            self.dirty.add(name)

    def _range(self, name):
        for attr, _label, lo, hi, step, _i in SLIDERS:
            if attr == name:
                return lo, hi, step
        return 0.0, 1.0, 0.01

    def take_changed(self):
        out = self.changed
        self.changed = set()
        return out

    # -- layout ----------------------------------------------------------

    def layout(self, width, height):
        self._w, self._h = width, height
        cols = max(1, min(5, width // 470))
        rows = (len(SLIDERS) + cols - 1) // cols
        cell_w = (width - 2 * PAD - (cols - 1) * GAP) // cols
        self.panel = (0.0, 0.0, float(width), float(PAD * 2 + HEADER_H + rows * CELL_H))
        self._layout = {}
        for i, (attr, label, lo, hi, step, integer) in enumerate(SLIDERS):
            col, row = divmod(i, rows)
            x = PAD + col * (cell_w + GAP)
            y = PAD + HEADER_H + row * CELL_H
            value_w = 62
            track_x = x + TEXT_MARGIN
            track_w = cell_w - TEXT_MARGIN * 2 - value_w
            self._layout[attr] = (float(track_x), float(y + 22), float(track_w),
                                  float(value_w), label, integer)

    # -- interaction -----------------------------------------------------

    def handle_event(self, event):
        """Return True if the panel used the event."""
        import pygame
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            hit = self._hit(event.pos)
            if hit:
                self.dragging = hit
                self._drag_to(event.pos)
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = None
                return True
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                self._drag_to(event.pos)
                return True
            self.hot = self._hit(event.pos)
        return False

    def update_hover(self, pos, height):
        """Show the panel while the mouse is in the top of the window.

        `UI_HOVER_ZONE` is the fraction of the window height that counts, so
        0.34 is the top third; 0 keeps the panel up all the time. A drag holds
        it open, because pulling a slider off the top of the screen should not
        make the panel disappear under the cursor.
        """
        zone = float(getattr(self.cfg, 'UI_HOVER_ZONE', 0.0))
        if zone <= 0.0:
            self.visible = True
            return
        if self.dragging is not None:
            return
        self.visible = pos[1] < height * zone

    def _hit(self, pos):
        mx, my = pos
        if my > self.panel[3]:
            return None
        for attr, (tx, ty, tw, _vw, _l, _i) in self._layout.items():
            if tx - 12 <= mx <= tx + tw + 12 and ty - 12 <= my <= ty + 12:
                return attr
        return None

    def _drag_to(self, pos):
        attr = self.dragging
        tx, _ty, tw, _vw, _label, integer = self._layout[attr]
        lo, hi, _step = self._range(attr)
        frac = (pos[0] - tx) / max(1.0, tw)
        self._set(attr, lo + min(1.0, max(0.0, frac)) * (hi - lo), integer)

    # -- drawing ---------------------------------------------------------

    def _text(self, key, string, color, bold=False):
        import pygame
        tex, _size, shown = self._textures.get(key, (None, None, None))
        if shown == string and tex is not None:
            return tex, self._textures[key][1]
        if tex is not None:
            tex.release()
        font = self.header_font if bold else self.font
        body = font.render(string, True, color)
        # a one pixel drop shadow, because the panel is translucent and the
        # balls behind it can be brighter than the text
        shadow = font.render(string, True, (0, 0, 0))
        size = (body.get_width() + 1, body.get_height() + 1)
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.blit(shadow, (1, 1))
        surf.blit(body, (0, 0))
        tex = self.ctx.texture(size, 4, pygame.image.tostring(surf, 'RGBA', True))
        tex.filter = (self.ctx.LINEAR, self.ctx.LINEAR)
        self._textures[key] = (tex, size, string)
        return tex, size

    def _quad(self, tex, size, x, y, alpha):
        self.text_prog['u_rect'].write(
            np.array([x, y, size[0], size[1]], dtype=np.float32).tobytes())
        self.text_prog['u_alpha'].value = alpha
        tex.use(0)
        self.text_prog['u_tex'].value = 0
        self.text_vao.render(mode=4, vertices=6)

    def draw(self, width, height):
        if not self.visible:
            return
        import moderngl
        alpha = float(getattr(self.cfg, 'UI_ALPHA', 1.0))
        self.rect_prog['u_resolution'].write(
            np.array([width, height], dtype=np.float32).tobytes())
        self.disc_prog['u_resolution'].write(
            np.array([width, height], dtype=np.float32).tobytes())
        self.text_prog['u_resolution'].write(
            np.array([width, height], dtype=np.float32).tobytes())

        nr = nd = 0

        def rect(x, y, w, h, rgb, a):
            nonlocal nr
            self._rects[nr, 0:4] = (x, y, w, h)
            self._rects[nr, 4:7] = rgb
            self._rects[nr, 7] = a
            nr += 1

        def disc(x, y, r, rgb, a):
            nonlocal nd
            self._discs[nd, 0:2] = (x, y)
            self._discs[nd, 2] = r
            self._discs[nd, 3:6] = rgb
            self._discs[nd, 6] = a
            nd += 1

        rect(0, 0, self.panel[2], self.panel[3], np.array(PANEL_BG) / 255.0, alpha)

        for i, (attr, label, lo, hi, step, integer) in enumerate(SLIDERS):
            tx, ty, tw, value_w, _label, _int = self._layout[attr]
            hue = 0.667 + 0.305 * (i / max(1, len(SLIDERS) - 1))
            rgb = _hsv(hue, 0.55, 1.0)
            frac = 0.0 if hi <= lo else (self.value(attr) - lo) / (hi - lo)
            frac = min(1.0, max(0.0, frac))
            rect(tx, ty - TRACK_H / 2, tw, TRACK_H, np.array([1.0, 1.0, 1.0]),
                 TRACK_BG_ALPHA * alpha)
            disc(tx, ty, TRACK_H / 2, np.array([1.0, 1.0, 1.0]), TRACK_BG_ALPHA * alpha)
            disc(tx + tw, ty, TRACK_H / 2, np.array([1.0, 1.0, 1.0]),
                 TRACK_BG_ALPHA * alpha)
            if frac > 0.001:
                rect(tx, ty - TRACK_H / 2, tw * frac, TRACK_H, rgb, alpha)
                disc(tx, ty, TRACK_H / 2, rgb, alpha)
            disc(tx + tw * frac, ty, KNOB_R, np.array([1.0, 1.0, 1.0]), alpha)

        self.rect_vbo.write(self._rects[:nr].tobytes())
        self.rect_vao.render(moderngl.TRIANGLES, vertices=6, instances=nr)
        self.disc_vbo.write(self._discs[:nd].tobytes())
        self.disc_vao.render(moderngl.TRIANGLES, vertices=6, instances=nd)

        # labels, drawn last so they sit on top of the tracks
        for attr, label, lo, hi, step, integer in SLIDERS:
            tx, ty, tw, value_w, _label, _int = self._layout[attr]
            if attr == 'FPS':
                shown = 'auto' if self.value(attr) == 0 else _fmt(self.value(attr), integer)
            else:
                shown = _fmt(self.value(attr), integer)
            string = f'{label} {shown}'
            tex, size = self._text(attr, string, TEXT_COLOR)
            self._quad(tex, size, tx, ty - 24, alpha)
        head = ('config  always on'
                if float(getattr(self.cfg, 'UI_HOVER_ZONE', 0.0)) <= 0.0
                else 'config  hover the top of the window')
        if self.info:
            head += f'   {self.info}'
        tex, size = self._text('__header__', head, HEADER_COLOR, bold=True)
        self._quad(tex, size, PAD + TEXT_MARGIN, PAD + 4, alpha)

    # -- saving ----------------------------------------------------------

    def save(self, path):
        """Write the changed values back into config.py, keeping the rest of
        the file, comments included, exactly as it was."""
        changed = self.dirty
        if not changed:
            return []
        try:
            with open(path, 'r') as fh:
                lines = fh.readlines()
        except OSError as exc:
            print(f'could not read {path}: {exc}', flush=True)
            return []
        written = []
        for name in sorted(changed):
            value = getattr(self.cfg, name, None)
            if value is None:
                continue
            pattern = re.compile(rf'^(\s*{name}\s*=\s*)(-?[\d.]+)([^\n]*)(\n?)$')
            for i, line in enumerate(lines):
                m = pattern.match(line)
                if not m:
                    continue
                new = f'{m.group(1)}{value:g}{m.group(3)}{m.group(4)}'
                if new != line:
                    lines[i] = new
                    written.append(name)
                break
        if written:
            try:
                with open(path, 'w') as fh:
                    fh.writelines(lines)
            except OSError as exc:
                print(f'could not write {path}: {exc}', flush=True)
                return []
        return written


def _hsv(h, s, v):
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i %= 6
    return np.array([(v, t, p), (q, v, p), (p, v, t),
                     (p, q, v), (t, p, v), (v, p, q)][i], dtype=np.float32)
