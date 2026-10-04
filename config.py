"""
config.py — Gesture Controller: 1 PWM + 4 Digital Channels
"""

import platform

# ── Camera ────────────────────────────────────────────────────────────────────
CAMERA_ID     = 0
FRAME_WIDTH   = 1280
FRAME_HEIGHT  = 720
FPS_TARGET    = 30

# ── Serial ────────────────────────────────────────────────────────────────────
SERIAL_PORT      = "COM3" if platform.system() == "Windows" else "/dev/ttyUSB0"
BAUD_RATE        = 115200
SERIAL_TIMEOUT   = 0.5
RECONNECT_DELAY  = 3.0
SERIAL_SEND_HZ   = 50         # max PWM update rate

# ── Gesture timing ────────────────────────────────────────────────────────────
ACTIVATION_HOLD_SECS  = 5.0    # 1-fist hold → system ON / OFF
DIGITAL_TOGGLE_SECS   = 1.0    # 2-5 finger hold → toggle that digital channel
DETECTION_CONFIDENCE  = 0.75
TRACKING_CONFIDENCE   = 0.75
MAX_HANDS             = 1
GESTURE_DEBOUNCE_WIN  = 4      # majority-vote window (frames)

# ── PWM (CH1 only) ────────────────────────────────────────────────────────────
PWM_MIN           = 0
PWM_MAX           = 255
PWM_EMA_ALPHA     = 0.15       # lower = smoother but laggier
PWM_MEDIAN_WIN    = 7          # odd integer
PWM_DEADBAND      = 4

PWM_ZONE_TOP      = 0.12       # wrist here → PWM 255
PWM_ZONE_BOTTOM   = 0.88       # wrist here → PWM 0

# ── Channel definitions ───────────────────────────────────────────────────────
# CH1 = PWM  |  CH2-CH5 = Digital
NUM_CHANNELS      = 5
PWM_CHANNEL_IDX   = 0          # index into channel arrays (0-based)
DIGITAL_CH_IDXS   = [1, 2, 3, 4]

# finger count → channel index (0-based)
FINGER_CHANNEL_MAP = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}

# ── Serial Protocol ───────────────────────────────────────────────────────────
# Combined snapshot: $STATE:<pwm>,<d1>,<d2>,<d3>,<d4>\n
#   pwm  = 0-255
#   d1-d4 = 0 or 1  (CH2-CH5)
CMD_SYS_ON    = b"$SYS:ON\n"
CMD_SYS_OFF   = b"$SYS:OFF\n"
CMD_STATE_FMT = "$STATE:{},{},{},{},{}\n"   # pwm, d2, d3, d4, d5
CMD_HEARTBEAT = b"$HB\n"
HEARTBEAT_INTERVAL = 1.0

# ── UI Colors (BGR) ───────────────────────────────────────────────────────────
UI = {
    "bg"        : (15,  15,  20),
    "panel"     : (28,  30,  38),
    "accent"    : (0,   210, 120),
    "warning"   : (0,   170, 255),
    "danger"    : (50,  60,  230),
    "text"      : (210, 215, 225),
    "inactive"  : (70,  72,  80),
    "ch_active" : (255, 200,  0),
    "progress"  : (30,  180, 90),
    "hold_arc"  : (0,   190, 255),
    "dig_on"    : (0,   220, 100),
    "dig_off"   : (60,  60,  70),
    "dig_active": (0,   200, 255),
}
