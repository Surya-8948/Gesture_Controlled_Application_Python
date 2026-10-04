
import time
import collections
import statistics
import logging
import math
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List

import config as cfg

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
class SystemState(Enum):
    SYSTEM_OFF   = auto()
    SYSTEM_ON    = auto()


# ─────────────────────────────────────────────────────────────────────────────
#  CH1 — PWM channel (UNCHANGED)
# ─────────────────────────────────────────────────────────────────────────────
class PWMChannel:
    def __init__(self):
        self._buf: collections.deque = collections.deque(maxlen=cfg.PWM_MEDIAN_WIN)
        self._ema: Optional[float]   = None
        self._out: int               = 0
        self.last_sent: int          = -1

    @property
    def value(self) -> int:
        return self._out

    def update(self, norm_y: float) -> int:
        self._buf.append(norm_y)
        med = statistics.median(self._buf) if len(self._buf) >= 3 else norm_y

        raw = (1.0 - med) * cfg.PWM_MAX
        raw = max(cfg.PWM_MIN, min(cfg.PWM_MAX, raw))

        if self._ema is None:
            self._ema = raw
        else:
            self._ema += cfg.PWM_EMA_ALPHA * (raw - self._ema)

        new = int(round(self._ema))
        if abs(new - self._out) >= cfg.PWM_DEADBAND:
            self._out = new
        return self._out

    def reset(self):
        self._buf.clear()
        self._ema      = None
        self._out      = 0
        self.last_sent = -1

    def needs_send(self) -> bool:
        return self._out != self.last_sent

    def mark_sent(self):
        self.last_sent = self._out


# ─────────────────────────────────────────────────────────────────────────────
#  Digital Channels (UNCHANGED)
# ─────────────────────────────────────────────────────────────────────────────
class DigitalChannel:

    def __init__(self, ch_id: int):
        self.ch_id          = ch_id
        self.state: bool    = False
        self.last_sent: int = -1
        self._hold_start: Optional[float] = None
        self._armed: bool   = True

    @property
    def value(self) -> int:
        return 1 if self.state else 0

    def update(self, gesture_active: bool, now: float) -> float:
        if not gesture_active:
            if self._hold_start and (now - self._hold_start < 0.2):
                return (now - self._hold_start) / cfg.DIGITAL_TOGGLE_SECS
            self._hold_start = None
            self._armed      = True
            return 0.0

        if not self._armed:
            return 1.0

        if self._hold_start is None:
            self._hold_start = now

        progress = min(1.0, (now - self._hold_start) / cfg.DIGITAL_TOGGLE_SECS)

        if progress >= 1.0:
            self.state  = not self.state
            self._armed = False
            logger.info("Digital CH%d → %s", self.ch_id + 1,
                        "ON" if self.state else "OFF")

        return progress

    def reset(self):
        self.state       = False
        self.last_sent   = -1
        self._hold_start = None
        self._armed      = True

    def needs_send(self) -> bool:
        return self.value != self.last_sent

    def mark_sent(self):
        self.last_sent = self.value


# ─────────────────────────────────────────────────────────────────────────────
#  NEW: Pinch Distance Function
# ─────────────────────────────────────────────────────────────────────────────
def get_pinch_distance(landmarks):
    x1, y1 = landmarks[4][1], landmarks[4][2]
    x2, y2 = landmarks[8][1], landmarks[8][2]
    return math.hypot(x2 - x1, y2 - y1)


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class GestureResult:
    state:           SystemState
    finger_count:    int
    active_channel:  int
    pwm_value:       int
    digital_states:  List[bool]
    hold_progress:   float
    dig_progress:    List[float]
    state_changed:   bool
    event:           Optional[str]


# ─────────────────────────────────────────────────────────────────────────────
class GestureEngine:

    def __init__(self):
        self._state  = SystemState.SYSTEM_OFF
        self._pwm    = PWMChannel()
        self._digital: List[DigitalChannel] = [
            DigitalChannel(i) for i in range(1, 5)
        ]

        self._sys_hold_start: Optional[float] = None

        self._dbuf: collections.deque = collections.deque(
            maxlen=cfg.GESTURE_DEBOUNCE_WIN
        )

        logger.info("GestureEngine ready: 1×PWM + 4×Digital")

    @property
    def state(self) -> SystemState:
        return self._state


    def process(self, fingers, landmarks, frame_h, frame_w):

        now          = time.monotonic()
        event        = None
        prev_state   = self._state

        raw = sum(fingers) if fingers is not None else 0
        self._dbuf.append(raw)
        if len(self._dbuf) == self._dbuf.maxlen:
            stable = max(set(self._dbuf), key=self._dbuf.count)
        else:
            stable = raw

        # ───────── SYSTEM TOGGLE (FIST) ─────────
        sys_progress = 0.0

        if stable == 0 and fingers is not None and sum(fingers) == 0:
            if self._sys_hold_start is None:
                self._sys_hold_start = now

            sys_progress = min(1.0,
                (now - self._sys_hold_start) / cfg.ACTIVATION_HOLD_SECS)

            if sys_progress >= 1.0:
                self._sys_hold_start = None

                if self._state == SystemState.SYSTEM_OFF:
                    self._state = SystemState.SYSTEM_ON
                    event = "SYSTEM_ON"
                else:
                    self._state = SystemState.SYSTEM_OFF
                    self._reset_all()
                    event = "SYSTEM_OFF"
        else:
            self._sys_hold_start = None

        is_on = (self._state == SystemState.SYSTEM_ON)

        active_ch = -1
        dig_progress = [0.0, 0.0, 0.0, 0.0]

        if is_on:

            #  PWM (Pinch control ONLY change)
            if stable == 1:
                active_ch = 0

                if landmarks is not None:
                    dist = get_pinch_distance(landmarks)

                    min_d = 20
                    max_d = 200

                    norm = (dist - min_d) / (max_d - min_d)
                    norm = max(0.0, min(1.0, norm))

                    # SAME smoothing pipeline use ho raha hai
                    self._pwm.update(1.0 - norm)

            # Digital channels (UNCHANGED)
            for i, dch in enumerate(self._digital):
                gesture_on = (stable == i + 2)
                dig_progress[i] = dch.update(gesture_on, now)

                if gesture_on:
                    active_ch = i + 1

        return GestureResult(
            state          = self._state,
            finger_count   = stable,
            active_channel = active_ch,
            pwm_value      = self._pwm.value,
            digital_states = [d.state for d in self._digital],
            hold_progress  = sys_progress,
            dig_progress   = dig_progress,
            state_changed  = (self._state != prev_state),
            event          = event,
        )

    def _reset_all(self):
        self._pwm.reset()
        for d in self._digital:
            d.reset()

