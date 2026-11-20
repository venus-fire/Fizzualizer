// Ball layout and collision physics: a direct port of create_balls and
// collide() from fizzualizer.py, which were themselves ported from the
// Rainmeter skin's Fizzualizer.lua.

export function createBalls(cfg, width, height) {
  const n = cfg.NUM_ITEMS;
  const totalW = (n - 1) * cfg.SPACING_X;
  const totalH = cfg.SPACING_Y + cfg.MIN_BALL_SIZE * 2 + 20;
  const offx = Math.floor((width - totalW) / 2);
  const offy = Math.floor((height - totalH) / 2);
  const balls = [];
  for (let i = 0; i < n; i++) {
    const x = offx + i * cfg.SPACING_X;
    const y = offy + (i % 2 === 0 ? 0 : cfg.SPACING_Y);
    balls.push({ ox: x, oy: y, baseY: y, x, y });
  }
  return balls;
}

// The skin set a colliding ball's position to the contact point outright, which
// pins it to whatever it touched. This pushes by a fraction of the overlap
// instead, so a ball slides out of the way and keeps moving.
export function collide(cfg, balls, bands, first, step, scale) {
  const push = Math.min(1, cfg.COLLIDE_PUSH * scale);
  const spring = Math.min(1, cfg.SPRING_BACK * scale);
  const n = bands.length;
  // Matches range(first + step, NUM_ITEMS if step == 1 else 1, step).
  const stop = step === 1 ? n : 1;

  for (let i = first + step; step === 1 ? i < stop : i > stop; i += step) {
    if (i < 0 || i >= n) break;
    const ball = balls[i];
    let bx = ball.x;
    let by = ball.y;
    const br = bands[i] * (cfg.MAX_COLLIDER_SIZE - cfg.MIN_BALL_SIZE) + cfg.MIN_BALL_SIZE;

    for (let j = i - step; step === 1 ? j >= first : j <= first; j -= step) {
      if (j < 0 || j >= n) break;
      const bj = balls[j];
      const rj = bands[j] * (cfg.MAX_COLLIDER_SIZE - cfg.MIN_BALL_SIZE) + cfg.MIN_BALL_SIZE;
      const dx = bx - bj.x;
      const dy = by - bj.y;
      const d2 = dx * dx + dy * dy;
      const reach = br + rj;
      if (d2 < reach * reach && d2 > 1e-8) {
        const d = Math.sqrt(d2);
        const overlap = (reach - d) * push;
        bx += ((Math.abs(dx) * step) / d) * overlap;
        by += (dy / d) * overlap;
      }
    }

    bx -= (bx - ball.ox) * spring;
    by -= (by - ball.oy) * spring;
    if (Math.abs(bx - ball.ox) < 0.1) bx = ball.ox;
    if (Math.abs(by - ball.oy) < 0.1) by = ball.oy;
    ball.x = bx;
    ball.y = by;
  }
}

export function hsvToRgb(h, s, v) {
  const i0 = Math.floor(h * 6);
  const f = h * 6 - i0;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  const i = ((i0 % 6) + 6) % 6;
  switch (i) {
    case 0: return [v, t, p];
    case 1: return [q, v, p];
    case 2: return [p, v, t];
    case 3: return [p, q, v];
    case 4: return [t, p, v];
    default: return [v, p, q];
  }
}

// Hue per item, recomputed when HUE_START / HUE_END / NUM_ITEMS change.
export function hueRamp(cfg) {
  const n = cfg.NUM_ITEMS;
  const hues = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    hues[i] = (cfg.HUE_START + (cfg.HUE_END - cfg.HUE_START) * (i / n)) / 360;
  }
  return hues;
}
