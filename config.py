"""
Fizzualizer configuration - mirrors the Rainmeter Visualizer.ini variables
"""

# Display
FULLSCREEN = False
WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
FPS = 60

# Audio settings
FFT_SIZE = 2048
FFT_OVERLAP = 1024
SAMPLE_RATE = 44100
CHANNELS = 1
SENSITIVITY = 55.0
# Attack/Decay smoothing (0.0-1.0, higher = faster response)
ATTACK = 0.75   # Rainmeter default 75
DECAY = 0.9     # Rainmeter default 100 (reversed: higher = slower decay)
FREQ_MIN = 10
FREQ_MAX = 15000

# Ball settings
NUM_ITEMS = 45
MIN_BALL_SIZE = 0
MAX_BALL_SIZE = 200
MAX_COLLIDER_SIZE = 160
SPACING_X = 12
SPACING_Y = 12
OFFSET_X = 800
OFFSET_Y = 350

# Particle settings
NO_PARTICLES = True   # set False to enable bouncing particles
PARTICLE_SIZE = 1
PARTICLE_COLOR = (255, 255, 255)

# Color settings (HSV)
HUE_START = 240       # blue
HUE_END = 350         # purple
SAT_ZERO = 0.0        # Saturation when band = 0
SAT_MIN = 0.75
SAT_MAX = 0.85
VAL_ZERO = 0.33       # Value when band = 0
VAL_MIN = 0.75
VAL_MAX = 1.0

# Audio device
# Set to None to auto-select the default monitor (loopback) device
# Or set a device index/name substring
AUDIO_DEVICE = None
