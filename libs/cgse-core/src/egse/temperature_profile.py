"""Shared temperature profile helpers for simulation and test scripts."""

from __future__ import annotations

import math
import random


def smoothstep(x: float) -> float:
    """Cubic smoothstep for x in [0, 1]."""
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def base_temperature(
    t: float,
    duration_s: float,
    room_temp: float,
    peak_temp: float,
    min_temp: float,
) -> float:
    """Piecewise warm-cool-warm profile for one cycle.

    Segments (fraction of total duration):
    - 0.00 .. 0.15: warm up room -> peak
    - 0.15 .. 0.70: asymptotic cool down peak -> min
    - 0.70 .. 1.00: asymptotic warm up min -> room
    """
    if duration_s <= 0:
        return room_temp

    p = max(0.0, min(1.0, t / duration_s))

    if p <= 0.15:
        x = p / 0.15
        return room_temp + (peak_temp - room_temp) * smoothstep(x)

    if p <= 0.70:
        x = (p - 0.15) / 0.55
        k = 6.0
        return min_temp + (peak_temp - min_temp) * math.exp(-k * x)

    x = (p - 0.70) / 0.30
    k = 3.5
    return room_temp - (room_temp - min_temp) * math.exp(-k * x)


def sensor_temperatures_3ch(base_temp: float, elapsed_s: float, rng: random.Random) -> tuple[float, float, float]:
    """Derive three sensor readings from the base profile with realistic offsets/noise."""
    sensor_1 = base_temp + rng.gauss(0.0, 0.05)
    sensor_2 = base_temp + 0.25 + 0.10 * math.sin(elapsed_s / 25.0) + rng.gauss(0.0, 0.06)
    sensor_3 = base_temp - 0.20 + 0.07 * math.cos(elapsed_s / 35.0) + rng.gauss(0.0, 0.08)
    return sensor_1, sensor_2, sensor_3


def sensor_temperature_for_id(base_temp: float, elapsed_s: float, sensor_id: str, rng: random.Random) -> float:
    """Derive one sensor reading from base profile with deterministic per-sensor variation."""
    sid_value = sum(ord(ch) for ch in sensor_id)
    phase = math.radians(sid_value % 360)
    offset = ((sid_value % 17) - 8) * 0.03
    drift = 0.08 * math.sin((elapsed_s / 25.0) + phase)
    noise = rng.gauss(0.0, 0.05)
    return base_temp + offset + drift + noise
