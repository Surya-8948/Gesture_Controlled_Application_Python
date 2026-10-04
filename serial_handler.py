"""
serial_handler.py — Thread-safe Arduino bridge
Protocol: $STATE:pwm,d2,d3,d4,d5\n
"""

import serial
import threading
import time
import queue
import logging
from typing import Optional, List

import config as cfg

logger = logging.getLogger(__name__)


class SerialHandler:

    MAX_QUEUE   = 32
    WRITE_RETRY = 2

    def __init__(self):
        self._port: Optional[serial.Serial] = None
        self._connected = threading.Event()
        self._stop      = threading.Event()
        self._q: queue.Queue = queue.Queue(maxsize=self.MAX_QUEUE)
        self._lock      = threading.Lock()

        self._min_interval = 1.0 / cfg.SERIAL_SEND_HZ
        self._last_send    = 0.0
        self._last_hb      = 0.0

        self.bytes_sent  = 0
        self.send_errors = 0

        self._thread = threading.Thread(
            target=self._worker, name="SerialWorker", daemon=True
        )
        self._thread.start()
        logger.info("SerialHandler started — %s @ %d", cfg.SERIAL_PORT, cfg.BAUD_RATE)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def send_system_on(self):
        self._enqueue(cfg.CMD_SYS_ON, priority=True)

    def send_system_off(self):
        self._enqueue(cfg.CMD_SYS_OFF, priority=True)

    def send_state(self, pwm: int, digitals: List[bool]):
        """
        Rate-limited state snapshot.
        pwm      — 0-255
        digitals — list of 4 booleans [CH2, CH3, CH4, CH5]
        """
        now = time.monotonic()
        if now - self._last_send < self._min_interval:
            return
        self._last_send = now
        d = [1 if v else 0 for v in digitals]
        payload = cfg.CMD_STATE_FMT.format(pwm, d[0], d[1], d[2], d[3]).encode()
        self._enqueue(payload)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2.0)
        if self._port and self._port.is_open:
            self._port.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _enqueue(self, data: bytes, priority: bool = False):
        try:
            if priority:
                # Flush queue for high-priority commands
                while not self._q.empty():
                    try: self._q.get_nowait()
                    except queue.Empty: break
            self._q.put_nowait(data)
        except queue.Full:
            try:
                self._q.get_nowait()
                self._q.put_nowait(data)
            except queue.Empty:
                pass

    def _connect(self) -> bool:
        try:
            self._port = serial.Serial(
                port=cfg.SERIAL_PORT, baudrate=cfg.BAUD_RATE,
                timeout=cfg.SERIAL_TIMEOUT, write_timeout=0.2
            )
            time.sleep(2.0)
            self._port.reset_input_buffer()
            self._connected.set()
            logger.info("Serial connected: %s", cfg.SERIAL_PORT)
            return True
        except serial.SerialException as e:
            logger.warning("Serial connect failed: %s", e)
            self._connected.clear()
            return False

    def _write(self, data: bytes) -> bool:
        for _ in range(self.WRITE_RETRY):
            try:
                with self._lock:
                    self._port.write(data)
                self.bytes_sent += len(data)
                return True
            except serial.SerialException as e:
                logger.warning("Write error: %s", e)
                time.sleep(0.05)
        self.send_errors += 1
        self._connected.clear()
        return False

    def _worker(self):
        while not self._stop.is_set():
            if not self._connected.is_set():
                if not self._connect():
                    time.sleep(cfg.RECONNECT_DELAY)
                    continue

            now = time.monotonic()
            if now - self._last_hb >= cfg.HEARTBEAT_INTERVAL:
                self._write(cfg.CMD_HEARTBEAT)
                self._last_hb = now

            try:
                data = self._q.get(timeout=0.05)
                if not self._write(data):
                    continue
            except queue.Empty:
                pass
