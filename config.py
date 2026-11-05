"""
Fizzualizer configuration - mirrors the Rainmeter Visualizer.ini variables
"""

# Display
FULLSCREEN = True
# Windowed size, used when FULLSCREEN is False and as a fallback if the
# desktop size cannot be read. Fullscreen always uses the display size.
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
FPS = 0
# The per-frame constants below are written for this rate. The app scales them
# by the real frame time, so changing FPS does not change how the balls feel.
REFERENCE_FPS = 43

# Config sliders drawn along the top of the window. They appear while the
# mouse is in the top UI_HOVER_ZONE of the window, as a fraction of its height,
# so 0.34 is the top third; 0 keeps them up all the time. UI_ALPHA is the
# panel's opacity, so 0.8 is 20% transparent.
UI_HOVER_ZONE = 0.34
UI_ALPHA = 0.8
MOUSE_HIDE_DELAY = 3  # seconds of inactivity before cursor hides
VOLUME_STEP = 1       # percent per arrow-up / arrow-down press
VOLUME_REPEAT_DELAY = 0.25     # seconds held before the volume starts repeating
VOLUME_REPEAT_INTERVAL = 0.05  # seconds between steps while held (20 steps/s)

# Audio settings
FFT_SIZE = 2048
SAMPLE_RATE = 44100
SENSITIVITY = 30
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
PEAK_DECAY = 0.993

# Common normalization, applied on top of the per-band one. Each band divides
# by its own recent peak, so once that peak has decayed a hushed band still
# reads near full and a quiet passage looks as busy as a chorus. This measures
# how loud the moment is against a slowly falling reference and scales every
# band by it, without changing the balance between bands.
# GLOBAL_FLOOR is how much of the band value survives when the gate is fully
# shut: 1.0 turns the whole thing off, 0.0 lets a silent passage collapse the
# picture to nothing. Start high and walk it down.
GLOBAL_FLOOR = 0.53
# Below the reference by this many dB, the gate is fully shut. This sets how
# much a passage has to drop before the balls start shrinking.
GLOBAL_RANGE_DB = 12.0
# How fast the reference falls, in dB per second. A loud chorus holds the gate
# open for a while at a slow value; a fast one lets the picture breathe with
# the song.
GLOBAL_REF_FALL = 0.2
# Per-frame rise and fall of the gate, scaled by the real frame time. The rise
# is quicker than the fall so a drop to a quiet passage is read immediately
# and the recovery is smooth instead of pumping.
GLOBAL_ATTACK = 0.35
GLOBAL_RELEASE = 0.06

# Ball settings
NUM_ITEMS = 45
MIN_BALL_SIZE = 0     # radius floor, so a quiet band is still a visible dot
MAX_BALL_SIZE = 230
# The collider is deliberately much smaller than the ball. It is what the
# balls push each other with, so scaling it with the drawn size flings the
# whole row off the screen. Raise it for more spread, lower it for a tighter
# row.
MAX_COLLIDER_SIZE = 390
SPACING_X = 30
SPACING_Y = 6
# Collision and spring. SPRING_BACK is how fast a ball returns to its rest
# height, as a fraction of the remaining distance per frame. COLLIDE_PUSH is
# how much of an overlap is resolved in one frame: 1.0 snaps a ball to the
# contact point and pins it there, which is what made big balls freeze.
SPRING_BACK = 0.255
COLLIDE_PUSH = 0.14
# Stereo: a band leaning left pulls its ball up, right pushes it down. This is
# the most it travels, in pixels, at full pan and full volume.
STEREO_SHIFT = 120
PAN_SMOOTH = 0.01     # per-frame follow of the pan, lower is steadier

# Color settings (HSV)
HUE_START = 240       # blue
HUE_END = 350         # purple
# Colour when a band is silent. The Rainmeter skin interpolates from SatMin /
# ValMin at zero, so the same values here keep a quiet ball a solid, saturated
# dot. Zeroing saturation and dropping the value turns those balls grey, which
# reads as washed out next to the live ones.
SAT_ZERO = 0.75
SAT_MIN = 0.69
SAT_MAX = 1
VAL_ZERO = 0.75
VAL_MIN = 0.52
VAL_MAX = 1
