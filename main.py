

import cv2
import time
import logging
import argparse
import sys
import collections

from cvzone.HandTrackingModule import HandDetector

import config as cfg
from gesture_engine import GestureEngine, SystemState
from serial_handler  import SerialHandler
from ui_renderer     import UIRenderer

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger("main")


class FPSCounter:
    def __init__(self, win=30):
        self._ts: collections.deque = collections.deque(maxlen=win)

    def tick(self) -> float:
        self._ts.append(time.monotonic())
        if len(self._ts) < 2:
            return 0.0
        return (len(self._ts) - 1) / (self._ts[-1] - self._ts[0] + 1e-9)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--port",      default=cfg.SERIAL_PORT)
    p.add_argument("--baud",      type=int, default=cfg.BAUD_RATE)
    p.add_argument("--cam",       type=int, default=cfg.CAMERA_ID)
    p.add_argument("--no-serial", action="store_true",
                   help="Demo mode — skip serial")
    return p.parse_args()


def main():
    args = parse_args()
    cfg.SERIAL_PORT = args.port
    cfg.BAUD_RATE   = args.baud

    # ── Camera ────────────────────────────────────────────────────────────────
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_V4L2
    cap = cv2.VideoCapture(args.cam, backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cfg.FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          cfg.FPS_TARGET)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

    if not cap.isOpened():
        logger.error("Cannot open camera %d", args.cam)
        sys.exit(1)

    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logger.info("Camera %dx%d", fw, fh)

    # ── Modules ───────────────────────────────────────────────────────────────
    detector = HandDetector(
        detectionCon = cfg.DETECTION_CONFIDENCE,
        maxHands     = cfg.MAX_HANDS,
    )
    engine   = GestureEngine()
    renderer = UIRenderer(fw, fh)
    fps_ctr  = FPSCounter()

    serial_h = None if args.no_serial else SerialHandler()
    if args.no_serial:
        logger.warning("Demo mode — no serial output")

    # Track last-sent state for change detection
    last_pwm  = -1
    last_digs = [-1, -1, -1, -1]

    logger.info("Ready — Q to quit, R to reset engine")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            # ── Hand detection ────────────────────────────────────────────────
            hands, frame = detector.findHands(frame, draw=True, flipType=True)
            fingers = landmarks = None
            if hands:
                h         = hands[0]
                fingers   = detector.fingersUp(h)
                landmarks = h["lmList"]

            # ── Gesture engine ────────────────────────────────────────────────
            result = engine.process(fingers, landmarks, fh, fw)

            # ── Serial / console output ───────────────────────────────────────
            if serial_h is not None:
                if result.event == "SYSTEM_ON":
                    serial_h.send_system_on()
                    last_pwm  = -1
                    last_digs = [-1, -1, -1, -1]

                elif result.event == "SYSTEM_OFF":
                    serial_h.send_system_off()
                    last_pwm  = -1
                    last_digs = [-1, -1, -1, -1]

                if result.state == SystemState.SYSTEM_ON:
                    pwm  = result.pwm_value
                    digs = result.digital_states
                    d_int = [1 if d else 0 for d in digs]

                    changed = (pwm != last_pwm or
                               any(d_int[i] != last_digs[i] for i in range(4)))
                    if changed:
                        serial_h.send_state(pwm, digs)
                        last_pwm  = pwm
                        last_digs = d_int[:]
            else:
                if result.state == SystemState.SYSTEM_ON:
                    pwm   = result.pwm_value
                    d_int = [1 if d else 0 for d in result.digital_states]
                    if pwm != last_pwm or d_int != last_digs:
                        logger.debug("[DEMO] PWM=%d  DIG=%s", pwm, d_int)
                        last_pwm  = pwm
                        last_digs = d_int[:]

            # ── Render ────────────────────────────────────────────────────────
            fps  = fps_ctr.tick()
            s_ok = (serial_h is not None and serial_h.is_connected)
            frame = renderer.draw(frame, result, s_ok, fps)
            cv2.imshow("Gesture Controller  [Q=quit  R=reset]", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("r"):
                engine = GestureEngine()
                last_pwm  = -1
                last_digs = [-1, -1, -1, -1]
                logger.info("Engine reset")

    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        if serial_h:
            serial_h.send_system_off()
            time.sleep(0.15)
            serial_h.close()
        cap.release()
        cv2.destroyAllWindows()
        logger.info("Done.")


if __name__ == "__main__":
    main()
