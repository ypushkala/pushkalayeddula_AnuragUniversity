"""Replay clock. The demo replays synthetic data as if it were arriving now.

Simulated time advances at `speed` times real time from an anchor, and can be paused or
moved. Every endpoint shows only data at or before the clock, so nothing from the future
leaks into the dashboard.
"""
from __future__ import annotations

import os
import threading
import time

from prativimb import config

T_END = config.N_DAYS * 1440 - 1


class DemoClock:
    def __init__(self, minute: float | None = None, speed: float = 10.0, paused: bool = False):
        self._lock = threading.Lock()
        self._base = float(minute if minute is not None else config.datetime_to_minute(config.DEMO_NOW))
        self._anchor = time.monotonic()
        self.speed = speed
        self.paused = paused

    @classmethod
    def from_env(cls) -> "DemoClock":
        return cls(speed=float(os.environ.get("PRATIVIMB_SPEED", 10)),
                   paused=os.environ.get("PRATIVIMB_PAUSED", "0") == "1")

    def minute(self) -> float:
        with self._lock:
            if self.paused:
                return self._base
            return min(self._base + (time.monotonic() - self._anchor) * self.speed / 60.0, T_END)

    def set(self, minute: float | None = None, speed: float | None = None, paused: bool | None = None) -> None:
        current = self.minute()
        with self._lock:
            self._base = float(min(max(minute if minute is not None else current, 0), T_END))
            self._anchor = time.monotonic()
            if speed is not None:
                self.speed = float(speed)
            if paused is not None:
                self.paused = bool(paused)

    def state(self) -> dict:
        m = self.minute()
        return {"minute": m, "now": config.minute_to_datetime(m).isoformat(), "speed": self.speed,
                "paused": self.paused, "start": config.START.isoformat(),
                "end": config.minute_to_datetime(T_END).isoformat()}
