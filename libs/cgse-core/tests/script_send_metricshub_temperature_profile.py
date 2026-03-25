"""Send a simulated 3-sensor temperature profile to Metrics Hub.

This is a runnable test script (not a unit test) intended for dashboard and
pipeline validation. It generates one synthetic device profile where all three
sensors:

1. start near room temperature,
2. rise to about 28 degC,
3. slowly decrease asymptotically to about -5 degC,
4. slowly return to room temperature.

By default, the complete profile takes 10 minutes.

Usage examples:
    uv run py tests/script_send_metricshub_temperature_profile.py

    uv run py tests/script_send_metricshub_temperature_profile.py \
        --device-id hexapod_01 \
        --measurement device_temperature \
        --duration-s 600 \
        --interval-s 1.0

    uv run py tests/script_send_metricshub_temperature_profile.py \
        --hub-endpoint tcp://localhost:6130 --room-temp 21.5
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import time
from datetime import datetime
from datetime import timezone

from egse.metrics import DataPoint
from egse.metricshub.client import AsyncMetricsHubClient
from egse.metricshub.client import AsyncMetricsHubSender
from egse.metricshub.client import MetricsHubClient
from egse.metricshub.client import MetricsHubSender


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send simulated 3-sensor temperature profile to Metrics Hub.")

    parser.add_argument("--hub-endpoint", default="tcp://localhost:6130", help="Metrics Hub collector endpoint")
    parser.add_argument("--req-endpoint", default="tcp://localhost:6132", help="Metrics Hub request endpoint")

    parser.add_argument("--measurement", default="device_temperature", help="Measurement name")
    parser.add_argument("--device-id", default="device_01", help="Device identifier tag")
    parser.add_argument(
        "--async",
        action="store_true",
        dest="run_async",
        help="Run using asyncio client/sender instead of synchronous mode",
    )

    parser.add_argument(
        "--duration-s",
        type=float,
        default=600.0,
        help="Total profile duration in seconds (default: 600 = 10 minutes)",
    )
    parser.add_argument(
        "--interval-s",
        type=float,
        default=1.0,
        help="Sample interval in seconds (default: 1.0)",
    )

    parser.add_argument("--room-temp", type=float, default=21.0, help="Room temperature in degC")
    parser.add_argument("--peak-temp", type=float, default=28.0, help="Peak temperature in degC")
    parser.add_argument("--min-temp", type=float, default=-5.0, help="Minimum temperature in degC")

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for repeatable sensor noise",
    )

    return parser.parse_args()


def _smoothstep(x: float) -> float:
    """Cubic smoothstep for x in [0, 1]."""
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def _base_temperature(
    t: float,
    duration_s: float,
    room_temp: float,
    peak_temp: float,
    min_temp: float,
) -> float:
    """Piecewise profile for one cycle.

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
        return room_temp + (peak_temp - room_temp) * _smoothstep(x)

    if p <= 0.70:
        x = (p - 0.15) / 0.55
        k = 6.0
        return min_temp + (peak_temp - min_temp) * math.exp(-k * x)

    x = (p - 0.70) / 0.30
    k = 3.5
    return room_temp - (room_temp - min_temp) * math.exp(-k * x)


def _sensor_temperatures(base_temp: float, elapsed_s: float, rng: random.Random) -> tuple[float, float, float]:
    """Derive three sensor readings from the base profile with realistic offsets/noise."""
    sensor_1 = base_temp + rng.gauss(0.0, 0.05)
    sensor_2 = base_temp + 0.25 + 0.10 * math.sin(elapsed_s / 25.0) + rng.gauss(0.0, 0.06)
    sensor_3 = base_temp - 0.20 + 0.07 * math.cos(elapsed_s / 35.0) + rng.gauss(0.0, 0.08)
    return sensor_1, sensor_2, sensor_3


def _print_header(args: argparse.Namespace) -> None:
    print("Metrics Hub temperature profile sender")
    print(f"  mode:               {'asynchronous' if args.run_async else 'synchronous'}")
    print(f"  collector endpoint: {args.hub_endpoint}")
    print(f"  request endpoint:   {args.req_endpoint}")
    print(f"  measurement:        {args.measurement}")
    print(f"  device_id:          {args.device_id}")
    print(f"  duration:           {args.duration_s:.1f} s")
    print(f"  interval:           {args.interval_s:.3f} s")


def _print_status_sync(req_endpoint: str) -> None:
    try:
        with MetricsHubClient(req_endpoint=req_endpoint, request_timeout=2.0) as client:
            info = client.server_status()
            if info.get("success"):
                backend = info.get("backend", {})
                print("Hub status:")
                print("  status:             ok")
                print(f"  backend:            {backend.get('name', '?')}")
                print(f"  backend reachable:  {backend.get('reachable', '?')}")
                print(f"  repository class:   {backend.get('repository_class', '?')}")
            else:
                print(f"Hub status check failed: {info.get('error', 'unknown error')}")
    except Exception as exc:
        print(f"Hub status check failed: {exc}")


async def _print_status_async(req_endpoint: str) -> None:
    try:
        with AsyncMetricsHubClient(req_endpoint=req_endpoint, request_timeout=2.0) as client:
            info = await client.server_status()
            if info.get("success"):
                backend = info.get("backend", {})
                print("Hub status:")
                print("  status:             ok")
                print(f"  backend:            {backend.get('name', '?')}")
                print(f"  backend reachable:  {backend.get('reachable', '?')}")
                print(f"  repository class:   {backend.get('repository_class', '?')}")
            else:
                print(f"Hub status check failed: {info.get('error', 'unknown error')}")
    except Exception as exc:
        print(f"Hub status check failed: {exc}")


def _build_point(
    args: argparse.Namespace,
    t1: float,
    t2: float,
    t3: float,
    elapsed_s: float,
    sample_idx: int,
) -> DataPoint:
    return (
        DataPoint.measurement(args.measurement)
        .tag("device_id", args.device_id)
        .tag("profile", "warm-cool-warm")
        .field("sensor_1", round(t1, 3))
        .field("sensor_2", round(t2, 3))
        .field("sensor_3", round(t3, 3))
        .field("elapsed_s", round(elapsed_s, 3))
        .field("sample_idx", sample_idx)
        .time(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f%z"))
    )


def _run_sync(args: argparse.Namespace, rng: random.Random) -> tuple[int, int]:
    _print_status_sync(args.req_endpoint)

    sender = MetricsHubSender(hub_endpoint=args.hub_endpoint)
    sender.connect()

    start = time.monotonic()
    sent_ok = 0
    dropped = 0

    try:
        sample_idx = 0
        while True:
            now = time.monotonic()
            elapsed_s = now - start
            if elapsed_s > args.duration_s:
                break

            base_temp = _base_temperature(
                t=elapsed_s,
                duration_s=args.duration_s,
                room_temp=args.room_temp,
                peak_temp=args.peak_temp,
                min_temp=args.min_temp,
            )

            t1, t2, t3 = _sensor_temperatures(base_temp, elapsed_s, rng)
            point = _build_point(args, t1, t2, t3, elapsed_s, sample_idx)

            if sender.send(point):
                sent_ok += 1
            else:
                dropped += 1

            if sample_idx % 10 == 0:
                print(f"t={elapsed_s:6.1f}s T1={t1:6.2f}C T2={t2:6.2f}C T3={t3:6.2f}C sent={sent_ok} dropped={dropped}")

            sample_idx += 1

            target_elapsed = sample_idx * args.interval_s
            sleep_s = max(0.0, target_elapsed - (time.monotonic() - start))
            time.sleep(sleep_s)
    finally:
        sender.close()

    return sent_ok, dropped


async def _run_async(args: argparse.Namespace, rng: random.Random) -> tuple[int, int]:
    await _print_status_async(args.req_endpoint)

    sender = AsyncMetricsHubSender(hub_endpoint=args.hub_endpoint)
    sender.connect()

    start = time.monotonic()
    sent_ok = 0
    dropped = 0

    try:
        sample_idx = 0
        while True:
            now = time.monotonic()
            elapsed_s = now - start
            if elapsed_s > args.duration_s:
                break

            base_temp = _base_temperature(
                t=elapsed_s,
                duration_s=args.duration_s,
                room_temp=args.room_temp,
                peak_temp=args.peak_temp,
                min_temp=args.min_temp,
            )

            t1, t2, t3 = _sensor_temperatures(base_temp, elapsed_s, rng)
            point = _build_point(args, t1, t2, t3, elapsed_s, sample_idx)

            if await sender.send(point):
                sent_ok += 1
            else:
                dropped += 1

            if sample_idx % 10 == 0:
                print(f"t={elapsed_s:6.1f}s T1={t1:6.2f}C T2={t2:6.2f}C T3={t3:6.2f}C sent={sent_ok} dropped={dropped}")

            sample_idx += 1

            target_elapsed = sample_idx * args.interval_s
            sleep_s = max(0.0, target_elapsed - (time.monotonic() - start))
            await asyncio.sleep(sleep_s)
    finally:
        sender.close()

    return sent_ok, dropped


def run() -> int:
    args = _parse_args()

    if args.interval_s <= 0:
        raise ValueError("--interval-s must be > 0")
    if args.duration_s <= 0:
        raise ValueError("--duration-s must be > 0")

    rng = random.Random(args.seed)
    _print_header(args)
    sent_ok = 0
    dropped = 0

    try:
        if args.run_async:
            sent_ok, dropped = asyncio.run(_run_async(args, rng))
        else:
            sent_ok, dropped = _run_sync(args, rng)

    except KeyboardInterrupt:
        print("\nInterrupted by user, stopping...")

    total = sent_ok + dropped
    print("Done.")
    print(f"  total samples:      {total}")
    print(f"  sent successfully:  {sent_ok}")
    print(f"  dropped:            {dropped}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
