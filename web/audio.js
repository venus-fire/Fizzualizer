// Audio capture for the browser build.
//
// The desktop app reads PipeWire's sink monitor, which is system audio. A
// browser cannot reach system audio on its own, so there are three routes, and
// they are not equivalent:
//
//   file      an audio file played by the page. Works everywhere, and it is the
//             route that makes the visualizer usable on any device.
//   display   getDisplayMedia with audio. Chrome and Edge can share tab audio
//             (and system audio on some Linux desktops); Firefox and Safari
//             hand back a video-only stream, so this is offered and checked
//             rather than assumed.
//   mic       getUserMedia. This is the microphone, not system audio, but on a
//             Linux host with PipeWire a monitor source often appears in the
//             device list, which makes it a real system-audio path.
//
// Two analysers read the newest FFT_SIZE samples per channel, which is what the
// desktop capture keeps as a ring buffer. The FFT and the band mapping happen in
// dsp.js; this file only gets audio in and time-domain blocks out.

export class AudioInput {
  constructor(cfg) {
    this.cfg = cfg;
    this.ctx = null;
    this.source = null;
    this.mono = true;
    this.label = '';
    this.kind = 'none';
    this.track = null; // plays the audio to the speakers for file sources
    this.lastError = '';
  }

  ensureContext() {
    if (this.ctx) return this.ctx;
    const ctx = new (window.AudioContext || window.webkitAudioContext)({
      latencyHint: 'interactive',
    });
    this.ctx = ctx;

    // The analysis bus. Nothing here reaches the speakers: a captured stream
    // routed to the destination would echo.
    this.bus = ctx.createGain();
    this.bus.gain.value = 1;
    this.splitter = ctx.createChannelSplitter(2);

    const mkAnalyser = () => {
      const a = ctx.createAnalyser();
      a.fftSize = this.cfg.FFT_SIZE;
      // The Python path does its own smoothing, so the analyser's own would
      // stack on top of the attack/decay constants.
      a.smoothingTimeConstant = 0;
      a.minDecibels = -140;
      a.maxDecibels = 0;
      return a;
    };
    this.analyserL = mkAnalyser();
    this.analyserR = mkAnalyser();

    this.bus.connect(this.splitter);
    this.splitter.connect(this.analyserL, 0);
    this.splitter.connect(this.analyserR, 1);

    this.bufL = new Float32Array(this.cfg.FFT_SIZE);
    this.bufR = new Float32Array(this.cfg.FFT_SIZE);
    return ctx;
  }

  async resume() {
    const ctx = this.ensureContext();
    if (ctx.state !== 'running') {
      try {
        await ctx.resume();
      } catch (e) {
        this.lastError = `audio context would not start: ${e.message}`;
      }
    }
    return ctx.state;
  }

  teardown() {
    if (this.source) {
      try {
        this.source.disconnect();
      } catch (e) {}
      if (typeof this.source.stop === 'function') {
        try {
          this.source.stop();
        } catch (e) {}
      }
      this.source = null;
    }
    if (this.track) {
      try {
        this.track.disconnect();
      } catch (e) {}
      this.track = null;
    }
    if (this.stream) {
      for (const t of this.stream.getTracks()) t.stop();
      this.stream = null;
    }
    this.kind = 'none';
    this.label = '';
    this.mono = true;
  }

  // Reads the newest window per channel. Returns {left, right, mono}.
  read() {
    if (!this.analyserL) return { left: this.bufL, right: this.bufR, mono: true };
    this.analyserL.getFloatTimeDomainData(this.bufL);
    if (!this.mono) this.analyserR.getFloatTimeDomainData(this.bufR);
    return { left: this.bufL, right: this.bufR, mono: this.mono };
  }

  async playFile(file) {
    const ctx = this.ensureContext();
    this.teardown();
    const bytes = await file.arrayBuffer();
    const buffer = await ctx.decodeAudioData(bytes);

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.loop = true;
    src.connect(this.bus);

    // File playback belongs on the speakers. Captured system audio does not.
    this.track = ctx.createGain();
    this.track.gain.value = 1;
    src.connect(this.track);
    this.track.connect(ctx.destination);

    this.source = src;
    this.mono = buffer.numberOfChannels === 1;
    this.kind = 'file';
    this.label = file.name;
    src.start();
    await this.resume();
    return this.label;
  }

  async captureDisplay() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      throw new Error('this browser has no screen capture API');
    }
    const ctx = this.ensureContext();
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length === 0) {
      for (const t of stream.getTracks()) t.stop();
      throw new Error(
        'no audio came with that share. In Chrome, pick the tab and tick Share tab audio; Firefox cannot share audio at all.',
      );
    }
    this.teardown();
    this.stream = stream;
    const src = ctx.createMediaStreamSource(stream);
    src.connect(this.bus);
    this.source = src;

    // Stopping the video track ends the whole capture in Chrome, so it is kept
    // alive and simply never displayed.
    const settings = audioTracks[0].getSettings ? audioTracks[0].getSettings() : {};
    this.mono = (settings.channelCount || 2) < 2;
    this.kind = 'display';
    this.label = audioTracks[0].label || 'shared audio';
    audioTracks[0].addEventListener('ended', () => {
      if (this.kind === 'display') this.teardown();
    });
    await this.resume();
    return this.label;
  }

  async captureMic() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('this browser has no microphone API');
    }
    const ctx = this.ensureContext();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false,
      },
    });
    this.teardown();
    this.stream = stream;
    const src = ctx.createMediaStreamSource(stream);
    src.connect(this.bus);
    this.source = src;
    const track = stream.getAudioTracks()[0];
    const settings = track.getSettings ? track.getSettings() : {};
    this.mono = (settings.channelCount || 1) < 2;
    this.kind = 'mic';
    this.label = track.label || 'microphone';
    await this.resume();
    return this.label;
  }

  // Synthetic source for testing the pipeline without asking for permissions:
  // a tone at a chosen frequency, amplitude modulated so the picture moves.
  startTestTone(freq = 220, amp = 0.35, modulate = true) {
    const ctx = this.ensureContext();
    this.teardown();
    const osc = ctx.createOscillator();
    osc.type = 'sawtooth';
    osc.frequency.value = freq;
    const gain = ctx.createGain();
    gain.gain.value = amp;
    osc.connect(gain);
    gain.connect(this.bus);

    if (modulate) {
      const lfo = ctx.createOscillator();
      lfo.frequency.value = 2.4;
      const depth = ctx.createGain();
      depth.gain.value = amp * 0.9;
      lfo.connect(depth);
      depth.connect(gain.gain);
      lfo.start();
      this.lfo = lfo;
    }

    osc.start();
    this.source = osc;
    this.mono = true;
    this.kind = 'test';
    this.label = `test tone ${freq} Hz`;
    return this.label;
  }
}
