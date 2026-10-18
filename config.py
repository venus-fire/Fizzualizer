"""
Fizzualizer configuration - mirrors the Rainmeter Visualizer.ini variables
"""

# Display
FULLSCREEN = True
# Windowed size, used when FULLSCREEN is False and as a fallback if the
# desktop size cannot be read. Fullscreen always uses the display size.
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
FPS = 60
MOUSE_HIDE_DELAY = 3  # seconds of inactivity before cursor hides
VOLUME_STEP = 1       # percent per arrow-up / arrow-down press
VOLUME_REPEAT_DELAY = 0.25     # seconds held before the volume starts repeating
VOLUME_REPEAT_INTERVAL = 0.05  # seconds between steps while held (20 steps/s)

# Audio settings
FFT_SIZE = 2048
FFT_OVERLAP = 1024
SAMPLE_RATE = 44100
CHANNELS = 2           # stereo capture; the pan of each band moves its ball
SENSITIVITY = 55.0
# Attack/Decay smoothing (0.0-1.0, higher = faster response)
# These are per-frame factors and the loop runs at the hop rate, currently
# 1024 frames = about 43fps at 44.1kHz. A frame-rate change changes the feel.
ATTACK = 0.5    # Rainmeter default 75; higher = the hit lands harder
DECAY = 0.97    # Rainmeter default 100 (reversed: higher = slower decay)
FREQ_MIN = 10
FREQ_MAX = 15000
# Per-band peak tracking for the adaptive normalisation: how fast a band
# forgets its loudest recent moment. 0.995 is about a 3 second half-life at the
# current frame rate. Lower = a quiet passage recovers sooner after a loud one,
# higher = the loud peak keeps squashing everything for longer.
PEAK_DECAY = 0.995

# Ball settings
NUM_ITEMS = 45
MIN_BALL_SIZE = 6     # radius floor, so a quiet band is still a visible dot
MAX_BALL_SIZE = 300
# The collider is deliberately much smaller than the ball. It is what the
# balls push each other with, so scaling it with the drawn size flings the
# whole row off the screen. Raise it for more spread, lower it for a tighter
# row.
MAX_COLLIDER_SIZE = 150
SPACING_X = 12
SPACING_Y = 12
OFFSET_X = 800
OFFSET_Y = 350
# Collision and spring. SPRING_BACK is how fast a ball returns to its rest
# height, as a fraction of the remaining distance per frame. COLLIDE_PUSH is
# how much of an overlap is resolved in one frame: 1.0 snaps a ball to the
# contact point and pins it there, which is what made big balls freeze.
SPRING_BACK = 0.05
COLLIDE_PUSH = 0.2
# Stereo: a band leaning left pulls its ball up, right pushes it down. This is
# the most it travels, in pixels, at full pan and full volume.
STEREO_SHIFT = 120
PAN_SMOOTH = 0.12     # per-frame follow of the pan, lower is steadier

# Particle settings
NO_PARTICLES = True   # set False to enable bouncing particles
PARTICLE_SIZE = 1
PARTICLE_COLOR = (255, 255, 255)

# Color settings (HSV)
HUE_START = 240       # blue
HUE_END = 350         # purple
# Colour when a band is silent. The Rainmeter skin interpolates from SatMin /
# ValMin at zero, so the same values here keep a quiet ball a solid, saturated
# dot. Zeroing saturation and dropping the value turns those balls grey, which
# reads as washed out next to the live ones.
SAT_ZERO = 0.75
SAT_MIN = 0.75
SAT_MAX = 0.85
VAL_ZERO = 0.75
VAL_MIN = 0.75
VAL_MAX = 1.0

# Audio device
# Set to None to auto-select the default monitor (loopback) device
# Or set a device index/name substring
AUDIO_DEVICE = None
