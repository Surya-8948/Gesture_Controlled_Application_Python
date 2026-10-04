"""
ui_renderer.py — HUD for 1×PWM + 4×Digital channel system
"""

import cv2
import numpy as np
import math
import time
from typing import List

import config as cfg
from gesture_engine import SystemState, GestureResult

_FONT = cv2.FONT_HERSHEY_SIMPLEX

CH_LABELS = ["CH1  PWM", "CH2  DIG", "CH3  DIG", "CH4  DIG", "CH5  DIG"]


class UIRenderer:

    def __init__(self, fw: int, fh: int):
        self._fw = fw
        self._fh = fh
        self._flash_until = 0.0
        self._flash_color = cfg.UI["accent"]
        self._panel_x = fw - 265

    def draw(self, frame: np.ndarray, result: GestureResult,
             serial_ok: bool, fps: float) -> np.ndarray:
        now = time.monotonic()

        if result.event == "SYSTEM_ON":
            self._flash(cfg.UI["accent"])
        elif result.event == "SYSTEM_OFF":
            self._flash(cfg.UI["danger"])

        # Panel background
        ov = frame.copy()
        cv2.rectangle(ov, (self._panel_x - 10, 0), (self._fw, self._fh),
                      cfg.UI["panel"], -1)
        cv2.addWeighted(ov, 0.75, frame, 0.25, 0, frame)

        # Flash overlay
        if now < self._flash_until:
            prog  = (self._flash_until - now) / 0.35
            fl    = frame.copy()
            cv2.rectangle(fl, (0, 0), (self._fw, self._fh),
                          self._flash_color, -1)
            cv2.addWeighted(fl, 0.35 * prog, frame, 1 - 0.35 * prog, 0, frame)

        px = self._panel_x
        py = 22

        # ── Title ────────────────────────────────────────────────────────────
        self._txt(frame, "GESTURE PWM/DIG", px, py, scale=0.65,
                  color=cfg.UI["text"], thick=2)
        py += 32

        # ── System state badge ────────────────────────────────────────────────
        is_on   = (result.state == SystemState.SYSTEM_ON)
        s_col   = cfg.UI["accent"] if is_on else cfg.UI["inactive"]
        s_lbl   = " SYSTEM ON " if is_on else " SYSTEM OFF"
        self._badge(frame, s_lbl, px, py, s_col)

        # Serial badge  (right-aligned)
        sc_col = cfg.UI["accent"] if serial_ok else cfg.UI["danger"]
        self._badge(frame, " SER OK " if serial_ok else " SER ERR",
                    px + 145, py, sc_col)
        py += 34

        # ── Divider ───────────────────────────────────────────────────────────
        self._hline(frame, px, py)
        py += 12

        # ── Channel list ──────────────────────────────────────────────────────
        for i in range(5):
            is_active = (i == result.active_channel) and is_on
            if i == 0:
                # PWM bar
                self._pwm_row(frame, i, result.pwm_value, is_active, px, py)
            else:
                # Digital row
                di   = i - 1           # index into digital arrays
                dval = result.digital_states[di]
                dp   = result.dig_progress[di]
                self._dig_row(frame, i, dval, is_active, dp, px, py)
            py += 40

        py += 4
        self._hline(frame, px, py)
        py += 14

        # ── Finger indicator ──────────────────────────────────────────────────
        fc = result.finger_count
        self._txt(frame, f"Fingers: {fc}", px, py, scale=0.5,
                  color=cfg.UI["text"])
        py += 22

        # ── System hold arc ───────────────────────────────────────────────────
        if result.hold_progress > 0.01:
            lbl = "→ SYS ON" if not is_on else "→ SYS OFF"
            self._arc(frame, result.hold_progress, px + 48, py + 48, r=38,
                      color=cfg.UI["hold_arc"])
            self._txt(frame, lbl, px + 92, py + 52, scale=0.42,
                      color=cfg.UI["hold_arc"])
            py += 100

        # ── Active channel label ──────────────────────────────────────────────
        if is_on and result.active_channel >= 0:
            ac = result.active_channel
            if ac == 0:
                lbl = f"CH1: PWM {result.pwm_value}"
            else:
                state_txt = "ON" if result.digital_states[ac - 1] else "OFF"
                lbl = f"CH{ac+1}: {state_txt}"
            self._txt(frame, lbl, px, py, scale=0.6,
                      color=cfg.UI["ch_active"], thick=2)
            py += 26

        # ── Hint ─────────────────────────────────────────────────────────────
        self._hints(frame, result, py)

        # ── PWM zone guides ───────────────────────────────────────────────────
        self._zone_guides(frame)

        # ── FPS ──────────────────────────────────────────────────────────────
        self._txt(frame, f"FPS {fps:.1f}", 10, self._fh - 12,
                  scale=0.45, color=cfg.UI["inactive"])
        return frame

    # ─── Row renderers ────────────────────────────────────────────────────────

    def _pwm_row(self, frame, ch_i, val, is_active, px, py):
        bw  = 230
        bh  = 20
        pct = val / 255.0
        fill = int(bw * pct)
        bg   = cfg.UI["inactive"]
        fc   = cfg.UI["ch_active"] if is_active else cfg.UI["progress"]

        cv2.rectangle(frame, (px, py), (px + bw, py + bh), bg, -1, cv2.LINE_AA)
        if fill > 0:
            cv2.rectangle(frame, (px, py), (px + fill, py + bh), fc, -1, cv2.LINE_AA)
        bdr = cfg.UI["ch_active"] if is_active else (50, 52, 60)
        cv2.rectangle(frame, (px, py), (px + bw, py + bh), bdr, 1, cv2.LINE_AA)

        self._txt(frame, "CH1 PWM", px + 3, py + bh - 4, scale=0.4,
                  color=(10,10,10) if fill > 40 else cfg.UI["text"])
        val_s = str(val)
        (vw, _), _ = cv2.getTextSize(val_s, _FONT, 0.4, 1)
        self._txt(frame, val_s, px + bw - vw - 4, py + bh - 4,
                  scale=0.4, color=cfg.UI["text"])

    def _dig_row(self, frame, ch_i, state: bool, is_active: bool,
                 progress: float, px, py):
        bw = 230
        bh = 20

        # Background
        bg_col = cfg.UI["dig_on"] if state else cfg.UI["dig_off"]
        cv2.rectangle(frame, (px, py), (px + bw, py + bh), bg_col, -1, cv2.LINE_AA)

        # Progress fill (hold animation) while toggling
        if is_active and progress > 0.01 and progress < 1.0:
            fill = int(bw * progress)
            cv2.rectangle(frame, (px, py), (px + fill, py + bh),
                          cfg.UI["dig_active"], -1, cv2.LINE_AA)

        # Border
        bdr = cfg.UI["ch_active"] if is_active else (50, 52, 60)
        cv2.rectangle(frame, (px, py), (px + bw, py + bh), bdr, 1, cv2.LINE_AA)

        # Label
        lbl  = f"CH{ch_i + 1} DIG"
        self._txt(frame, lbl, px + 3, py + bh - 4, scale=0.4,
                  color=(10,10,10) if state else cfg.UI["text"])

        # State text
        s_txt  = "ON " if state else "OFF"
        s_col  = (10,10,10) if state else cfg.UI["inactive"]
        (sw, _), _ = cv2.getTextSize(s_txt, _FONT, 0.42, 1)
        self._txt(frame, s_txt, px + bw - sw - 4, py + bh - 4,
                  scale=0.42, color=s_col)

        # Small LED dot
        dot_x = px + bw - 12
        dot_y = py + bh // 2
        dot_c = cfg.UI["dig_on"] if state else (50, 50, 50)
        cv2.circle(frame, (dot_x, dot_y), 5, dot_c, -1, cv2.LINE_AA)
        cv2.circle(frame, (dot_x, dot_y), 5, (150, 150, 150), 1, cv2.LINE_AA)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _flash(self, color):
        self._flash_until = time.monotonic() + 0.35
        self._flash_color = color

    def _txt(self, frame, text, x, y, scale=0.5, color=None, thick=1):
        cv2.putText(frame, text, (int(x), int(y)), _FONT,
                    scale, color or cfg.UI["text"], thick, cv2.LINE_AA)

    def _badge(self, frame, label, x, y, color):
        (tw, th), _ = cv2.getTextSize(label, _FONT, 0.45, 1)
        pad = 5
        cv2.rectangle(frame, (x - pad, y - th - pad),
                      (x + tw + pad, y + pad), color, -1, cv2.LINE_AA)
        cv2.putText(frame, label, (x, y), _FONT, 0.45,
                    (10,10,10), 1, cv2.LINE_AA)

    def _hline(self, frame, x, y):
        cv2.line(frame, (x, y), (x + 240, y), cfg.UI["inactive"], 1)

    def _arc(self, frame, progress, cx, cy, r=38, color=None):
        color = color or cfg.UI["hold_arc"]
        cv2.circle(frame, (cx, cy), r, cfg.UI["inactive"], 2, cv2.LINE_AA)
        sweep = int(360 * progress)
        if sweep > 0:
            pts = []
            for deg in range(-90, -90 + sweep, 3):
                rad = math.radians(deg)
                pts.append([int(cx + r * math.cos(rad)),
                             int(cy + r * math.sin(rad))])
            if pts:
                cv2.polylines(frame,
                              [np.array(pts, np.int32).reshape(-1,1,2)],
                              False, color, 3, cv2.LINE_AA)
        pct = f"{int(progress*100)}%"
        (tw, th), _ = cv2.getTextSize(pct, _FONT, 0.4, 1)
        cv2.putText(frame, pct, (cx - tw//2, cy + th//2),
                    _FONT, 0.4, color, 1, cv2.LINE_AA)

    def _zone_guides(self, frame):
        ty  = int(cfg.PWM_ZONE_TOP    * self._fh)
        by  = int(cfg.PWM_ZONE_BOTTOM * self._fh)
        xe  = self._panel_x - 20
        ov  = frame.copy()
        cv2.line(ov, (0, ty), (xe, ty), cfg.UI["accent"], 1)
        cv2.line(ov, (0, by), (xe, by), cfg.UI["accent"], 1)
        cv2.addWeighted(ov, 0.4, frame, 0.6, 0, frame)
        self._txt(frame, "PWM 255", 6, ty - 4,  scale=0.38, color=cfg.UI["accent"])
        self._txt(frame, "PWM 0",   6, by + 14, scale=0.38, color=cfg.UI["accent"])

    def _hints(self, frame, result: GestureResult, y: int):
        is_on = (result.state == SystemState.SYSTEM_ON)
        hints = (["Hold 1 finger 2s → ON"]
                 if not is_on else
                 [" CH1 PWM  (wrist height)",
                  " 3 4 5 → toggle CH2-5",
                  "Hold 0.5s to toggle",
                  "Hold 1 finger 2s → OFF"])
        px = self._panel_x
        for h in hints:
            if y + 16 < self._fh - 10:
                self._txt(frame, h, px, y, scale=0.36, color=cfg.UI["inactive"])
                y += 15
