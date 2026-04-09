"""Send synthetic temperature-like telemetry to Metrics Hub at a sustained target rate.

This is a runnable load-generation script intended for stress testing the
Metrics Hub and backend write path without a physical data acquisition device.

The generated values follow a warm-cool-warm profile with realistic noise,
similar to ``script_send_metricshub_temperature_profile.py`` but scalable to
high sustained point rates across many channels.

By default, the profile is executed once across `-duration-s` (no repeat).
Use `--repeat-profile` to loop the profile with `--profile-period-s`.

Examples:
    uv run py tests/script_send_metricshub_load.py

    uv run py tests/script_send_metricshub_load.py \
        --hub-endpoint tcp://localhost:6130 \
        --req-endpoint tcp://localhost:6132 \
        --rate 7500 \
        --duration-s 3600 \
        --channels 128

    uv run py tests/script_send_metricshub_load.py \
        --rate 15000 \
        --tick-hz 50 \
        --repeat-profile \
        --profile-period-s 900 \
        --room-temp 21 --peak-temp 28 --min-temp -5

    uv run py tests/script_send_metricshub_load.py \
        --channels 3 \
        --sensor-biases=-0.3,0.0,0.25 \
        --rate 7500
"""

from __future__ import annotations

import argparse
import math
import random
import time
from dataclasses import dataclass
from typing import Any

from egse.metricshub.client import MetricsHubClient
from egse.metricshub.client import MetricsHubSender


@dataclass(slots=True)
class ChannelState:
    channel_id: int
    sensor_bias: float
    value: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send synthetic telemetry load to Metrics Hub.")

    parser.add_argument("--hub-endpoint", default="tcp://localhost:6130", help="Metrics Hub collector endpoint")
    parser.add_argument("--req-endpoint", default="tcp://localhost:6132", help="Metrics Hub request endpoint")
    parser.add_argument("--measurement", default="synthetic_load", help="Measurement name")
    parser.add_argument("--device-prefix", default="loadgen", help="Prefix used for the device_id tag")
    parser.add_argument("--profile", default="warm-cool-warm", help="Profile tag value")

    parser.add_argument("--rate", type=int, default=7_500, help="Target points per second")
    parser.add_argument("--duration-s", type=float, default=3_600.0, help="Run duration in seconds")
    parser.add_argument("--tick-hz", type=float, default=25.0, help="Scheduler tick rate in Hz")
    parser.add_argument("--channels", type=int, default=128, help="Number of synthetic channels to cycle through")
    parser.add_argument(
        "--profile-period-s",
        type=float,
        default=0.0,
        help="Cycle duration in seconds when --repeat-profile is enabled (0 uses --duration-s)",
    )
    parser.add_argument(
        "--repeat-profile",
        action="store_true",
        help="Repeat warm-cool-warm profile over the run; default is one cycle across --duration-s",
    )
    parser.add_argument("--room-temp", type=float, default=21.0, help="Room temperature in degC")
    parser.add_argument("--peak-temp", type=float, default=28.0, help="Peak temperature in degC")
    parser.add_argument("--min-temp", type=float, default=-5.0, help="Minimum temperature in degC")
    parser.add_argument("--noise-sigma", type=float, default=0.06, help="Per-sample gaussian noise (degC)")
    parser.add_argument(
        "--sensor-biases",
        type=str,
        default="",
        help=(
            "Comma-separated per-channel bias values in degC; must match --channels when provided. "
            "Use --sensor-biases=<values> when the first value is negative"
        ),
    )
    parser.add_argument(
        "--drift-sigma",
        type=float,
        default=0.010,
        help="Per-sample random-walk drift step (degC)",
    )
    parser.add_argument(
        "--report-interval-s",
        type=float,
        default=5.0,
        help="How often to print sender throughput statistics",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for repeatable signal generation")
    parser.add_argument(
        "--skip-status-check",
        action="store_true",
        help="Skip the initial Metrics Hub status request",
    )

    return parser.parse_args()


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _smoothstep(x: float) -> float:
    """Cubic smoothstep for x in [0, 1]."""
    x = _clamp(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _base_temperature(elapsed_s: float, args: argparse.Namespace) -> float:
    """Warm-cool-warm profile repeated every ``profile_period_s``.

    Segment fractions per cycle:
    - 0.00 .. 0.15: room -> peak
    - 0.15 .. 0.70: peak -> min (asymptotic)
    - 0.70 .. 1.00: min -> room (asymptotic)
    """
    if args.repeat_profile:
        period = max(args.profile_period_s, 1.0) if args.profile_period_s > 0 else max(args.duration_s, 1.0)
        p = (elapsed_s % period) / period
    else:
        duration = max(args.duration_s, 1.0)
        p = _clamp(elapsed_s / duration, 0.0, 1.0)

    if p <= 0.15:
        x = p / 0.15
        return args.room_temp + (args.peak_temp - args.room_temp) * _smoothstep(x)

    if p <= 0.70:
        x = (p - 0.15) / 0.55
        k = 6.0
        return args.min_temp + (args.peak_temp - args.min_temp) * math.exp(-k * x)

    x = (p - 0.70) / 0.30
    k = 3.5
    return args.room_temp - (args.room_temp - args.min_temp) * math.exp(-k * x)


def _build_channels(args: argparse.Namespace, rng: random.Random) -> list[ChannelState]:
    explicit_biases: list[float] = []
    if args.sensor_biases.strip():
        explicit_biases = [float(x.strip()) for x in args.sensor_biases.split(",") if x.strip()]
        if len(explicit_biases) != args.channels:
            raise ValueError("--sensor-biases must contain exactly one value per channel")

    channels: list[ChannelState] = []
    for channel_id in range(args.channels):
        sensor_bias = explicit_biases[channel_id] if explicit_biases else rng.gauss(0.0, 0.20)
        start_value = args.room_temp + sensor_bias + rng.gauss(0.0, 0.15)
        channels.append(
            ChannelState(
                channel_id=channel_id,
                sensor_bias=sensor_bias,
                value=start_value,
            )
        )
    return channels


def _next_value(channel: ChannelState, elapsed_s: float, args: argparse.Namespace, rng: random.Random) -> float:
    base = _base_temperature(elapsed_s, args)
    channel_variation = 0.08 * math.sin(elapsed_s / 25.0 + channel.channel_id * 0.17)
    target = base + channel.sensor_bias + channel_variation

    noise = rng.gauss(0.0, args.noise_sigma)
    drift = rng.gauss(0.0, args.drift_sigma)
    channel.value += 0.10 * (target - channel.value) + drift + noise

    # Keep temperatures in a sane envelope while preserving realistic dynamics.
    channel.value = _clamp(channel.value, args.min_temp - 10.0, args.peak_temp + 10.0)
    return channel.value


def _build_payload(
    args: argparse.Namespace,
    channel: ChannelState,
    elapsed_s: float,
    sample_idx: int,
    value: float,
) -> dict[str, Any]:
    device_id = f"{args.device_prefix}_{channel.channel_id:03d}"
    return {
        "measurement": args.measurement,
        "tags": {
            "device_id": device_id,
            "channel": f"ch_{channel.channel_id:03d}",
            "profile": args.profile,
        },
        "fields": {
            "temperature": round(value, 4),
            "sample_idx": sample_idx,
            "elapsed_s": round(elapsed_s, 3),
        },
        "time": time.time(),
    }


def _print_header(args: argparse.Namespace) -> None:
    print("Metrics Hub synthetic load sender")
    print(f"  collector endpoint: {args.hub_endpoint}")
    print(f"  request endpoint:   {args.req_endpoint}")
    print(f"  measurement:        {args.measurement}")
    print(f"  rate target:        {args.rate} points/s")
    print(f"  duration:           {args.duration_s:.1f} s")
    print(f"  channels:           {args.channels}")
    print(f"  tick rate:          {args.tick_hz:.1f} Hz")
    if args.repeat_profile:
        period = args.profile_period_s if args.profile_period_s > 0 else args.duration_s
        print("  profile mode:       repeating")
        print(f"  profile period:     {period:.1f} s")
    else:
        print("  profile mode:       single-cycle")
        print(f"  profile period:     {args.duration_s:.1f} s (run duration)")
    print(f"  room/peak/min:      {args.room_temp:.1f} / {args.peak_temp:.1f} / {args.min_temp:.1f} degC")
    if args.sensor_biases.strip():
        print(f"  sensor_biases:      {args.sensor_biases}")


def _print_status(req_endpoint: str) -> None:
    try:
        with MetricsHubClient(req_endpoint=req_endpoint, request_timeout=2.0) as client:
            info = client.server_status()
    except Exception as exc:
        print(f"Hub status check failed: {exc}")
        return

    if not info.get("success"):
        print(f"Hub status check failed: {info.get('error', 'unknown error')}")
        return

    backend = info.get("backend", {})
    stats = info.get("statistics", {})

    print("Hub status:")
    print(f"  status:             {info.get('status', '?')}")
    print(f"  backend:            {backend.get('name', '?')}")
    print(f"  backend reachable:  {backend.get('reachable', '?')}")
    print(f"  queue:              {stats.get('queue', '?')} / {stats.get('queue_maxsize', '?')}")


def run() -> int:
    args = _parse_args()

    if args.rate <= 0:
        raise ValueError("--rate must be > 0")
    if args.duration_s <= 0:
        raise ValueError("--duration-s must be > 0")
    if args.tick_hz <= 0:
        raise ValueError("--tick-hz must be > 0")
    if args.channels <= 0:
        raise ValueError("--channels must be > 0")
    if args.report_interval_s <= 0:
        raise ValueError("--report-interval-s must be > 0")

    rng = random.Random(args.seed)
    channels = _build_channels(args, rng)

    _print_header(args)
    if not args.skip_status_check:
        _print_status(args.req_endpoint)

    sender = MetricsHubSender(hub_endpoint=args.hub_endpoint)
    sender.connect()

    attempted = 0
    sent_ok = 0
    dropped = 0
    tick_idx = 0
    channel_idx = 0
    sample_idx = 0

    start = time.monotonic()
    next_report = start + args.report_interval_s

    try:
        while True:
            now = time.monotonic()
            elapsed_s = now - start
            if elapsed_s >= args.duration_s:
                break

            tick_idx += 1
            target_attempted = int(tick_idx * args.rate / args.tick_hz)
            to_send = max(0, target_attempted - attempted)

            for _ in range(to_send):
                channel = channels[channel_idx]
                value = _next_value(channel, elapsed_s, args, rng)
                payload = _build_payload(args, channel, elapsed_s, sample_idx, value)

                if sender.send(payload):
                    sent_ok += 1
                else:
                    dropped += 1

                attempted += 1
                sample_idx += 1
                channel_idx = (channel_idx + 1) % len(channels)

            now = time.monotonic()
            if now >= next_report:
                runtime = max(now - start, 1e-6)
                attempted_rate = attempted / runtime
                sent_rate = sent_ok / runtime
                print(
                    f"t={runtime:7.1f}s attempted={attempted} sent={sent_ok} dropped={dropped} "
                    f"attempted_rate={attempted_rate:8.0f}/s sent_rate={sent_rate:8.0f}/s"
                )
                next_report += args.report_interval_s

            sleep_until = start + (tick_idx / args.tick_hz)
            sleep_s = sleep_until - time.monotonic()
            if sleep_s > 0:
                time.sleep(sleep_s)

    except KeyboardInterrupt:
        print("\nInterrupted by user, stopping...")
    finally:
        sender.close()

    runtime = max(time.monotonic() - start, 1e-6)
    attempted_rate = attempted / runtime
    sent_rate = sent_ok / runtime

    print("Done.")
    print(f"  runtime:            {runtime:.1f} s")
    print(f"  attempted:          {attempted}")
    print(f"  sent successfully:  {sent_ok}")
    print(f"  dropped:            {dropped}")
    print(f"  attempted rate:     {attempted_rate:.0f} points/s")
    print(f"  sent rate:          {sent_rate:.0f} points/s")

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
