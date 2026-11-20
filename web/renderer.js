// WebGL2 instanced circles: one instanced draw call for all 45 balls, the same
// shape as the desktop build's moderngl renderer. A unit quad of four vertices
// and six indices is instanced once per ball, and the fragment shader discards
// everything outside radius 0.5 of the quad.
//
// Positions and radii are CSS pixels. On a high-DPI screen the backing store is
// larger than the CSS size, so the viewport follows the backing store while the
// shader keeps working in the units the config is written in.

import { hsvToRgb } from './physics.js';

const VERT = `#version 300 es
in vec2 in_offset;      // unit quad corner, -0.5 .. 0.5
in vec2 in_center;      // per instance, CSS pixels, top-left origin
in float in_radius;     // per instance
in vec3 in_color;       // per instance

uniform vec2 u_resolution;

out vec3 v_color;
out vec2 v_uv;

void main() {
    vec2 pos = in_center + in_offset * max(in_radius * 2.0, 1.0);
    vec2 clipv = (pos / u_resolution) * 2.0 - 1.0;
    gl_Position = vec4(clipv.x, -clipv.y, 0.0, 1.0);
    v_uv = in_offset;
    v_color = in_color;
}`;

const FRAG = `#version 300 es
precision highp float;
in vec3 v_color;
in vec2 v_uv;
out vec4 f_color;

void main() {
    if (length(v_uv) > 0.5) discard;
    f_color = vec4(v_color, 1.0);
}`;

const QUAD_VERTS = new Float32Array([-0.5, -0.5, 0.5, -0.5, 0.5, 0.5, -0.5, 0.5]);
const QUAD_INDICES = new Uint16Array([0, 1, 2, 0, 2, 3]);

function compile(gl, type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    throw new Error(`shader compile failed: ${gl.getShaderInfoLog(sh)}`);
  }
  return sh;
}

export class BallRenderer {
  constructor(canvas, maxInstances = 256) {
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: false });
    if (!gl) throw new Error('WebGL2 is not available in this browser');
    this.gl = gl;
    this.canvas = canvas;
    this.width = canvas.clientWidth || 1;
    this.height = canvas.clientHeight || 1;
    this.instances = new Float32Array(maxInstances * 6); // cx, cy, radius, r, g, b

    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error(`program link failed: ${gl.getProgramInfoLog(prog)}`);
    }
    this.prog = prog;
    this.uResolution = gl.getUniformLocation(prog, 'u_resolution');

    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);

    const quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    gl.bufferData(gl.ARRAY_BUFFER, QUAD_VERTS, gl.STATIC_DRAW);
    const aOffset = gl.getAttribLocation(prog, 'in_offset');
    gl.enableVertexAttribArray(aOffset);
    gl.vertexAttribPointer(aOffset, 2, gl.FLOAT, false, 0, 0);

    this.instBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf);
    gl.bufferData(gl.ARRAY_BUFFER, this.instances.byteLength, gl.DYNAMIC_DRAW);
    const stride = 6 * 4;
    const bind = (name, size, offset) => {
      const loc = gl.getAttribLocation(prog, name);
      if (loc < 0) return;
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, offset);
      gl.vertexAttribDivisor(loc, 1);
    };
    bind('in_center', 2, 0);
    bind('in_radius', 1, 8);
    bind('in_color', 3, 12);

    const idxBuf = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idxBuf);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, QUAD_INDICES, gl.STATIC_DRAW);

    gl.bindVertexArray(null);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);
    gl.clearColor(0, 0, 0, 1);
  }

  resize(cssWidth, cssHeight, dpr) {
    const gl = this.gl;
    const bw = Math.max(1, Math.round(cssWidth * dpr));
    const bh = Math.max(1, Math.round(cssHeight * dpr));
    if (this.canvas.width !== bw || this.canvas.height !== bh) {
      this.canvas.width = bw;
      this.canvas.height = bh;
    }
    gl.viewport(0, 0, bw, bh);
    this.width = cssWidth;
    this.height = cssHeight;
  }

  draw(count, cfg, balls, bands, hues) {
    const gl = this.gl;
    const inst = this.instances;
    const span = cfg.MAX_BALL_SIZE - cfg.MIN_BALL_SIZE;

    for (let i = 0; i < count; i++) {
      const bv = bands[i];
      let radius = bv * span + cfg.MIN_BALL_SIZE;
      let r = 0;
      let g = 0;
      let b = 0;
      if (Number.isFinite(radius) && radius >= 1) {
        let s;
        let v;
        if (bv === 0) {
          s = cfg.SAT_ZERO;
          v = cfg.VAL_ZERO;
        } else {
          s = cfg.SAT_MIN + (cfg.SAT_MAX - cfg.SAT_MIN) * bv;
          v = cfg.VAL_MIN + (cfg.VAL_MAX - cfg.VAL_MIN) * bv;
        }
        [r, g, b] = hsvToRgb(hues[i], Math.min(1, Math.max(0, s)), Math.min(1, Math.max(0, v)));
      } else {
        radius = 0;
      }
      const k = i * 6;
      inst[k] = balls[i].x;
      inst[k + 1] = balls[i].y;
      inst[k + 2] = radius;
      inst[k + 3] = r;
      inst[k + 4] = g;
      inst[k + 5] = b;
    }

    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, inst, 0, count * 6);
    gl.useProgram(this.prog);
    gl.uniform2f(this.uResolution, this.width, this.height);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawElementsInstanced(gl.TRIANGLES, 6, gl.UNSIGNED_SHORT, 0, count);
    gl.bindVertexArray(null);
  }
}
