#!/usr/bin/env python3
"""Pitwall Telemetry Engine - Concurrent WebSocket Stress & Load Tester.

Simulates multiple concurrent client spectators connecting to the 60 FPS / 30 FPS
telemetry stream. Measures:
  - Connection handshake latency
  - Time to First Frame (TTFF - measures TimelineReplayer load time)
  - Sustained delivery frame rate (FPS)
  - Inter-frame delivery jitter & stall frequency
  - Error rates and abnormal connection drops
  - Resilience against concurrent interactive actions (seek, speed, driver select)

Usage:
  # Quick 5-client test for 15 seconds against local server:
  python scripts/load_test_websockets.py --clients 5 --duration 15

  # Chaos mode: 10 clients sending random seek/speed commands:
  python scripts/load_test_websockets.py --clients 10 --duration 20 --chaos

  # Test against production or custom host:
  python scripts/load_test_websockets.py --url wss://pitwall-f1.live/api/ws/telemetry?session_key=9472 --clients 15
"""

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field

try:
    import websockets
except ImportError:
    print("❌ Error: 'websockets' package is required. Install via 'uv sync' or 'pip install websockets'.")
    sys.exit(1)


@dataclass
class ClientMetrics:
    client_id: int
    connected: bool = False
    handshake_time_ms: float = 0.0
    ttff_ms: float = 0.0  # Time to first frame
    frames_received: int = 0
    errors: list[str] = field(default_factory=list)
    frame_intervals_ms: list[float] = field(default_factory=list)
    disconnected_early: bool = False
    disconnect_code: int | None = None
    actions_sent: int = 0


async def simulate_client(
    client_id: int,
    url: str,
    duration: float,
    chaos_mode: bool,
    metrics: ClientMetrics,
    stop_event: asyncio.Event,
    init_timeout: float = 30.0,
) -> None:
    """Connect a single simulated spectator and stream telemetry frames."""
    connect_start = time.perf_counter()

    try:
        async with websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            handshake_end = time.perf_counter()
            metrics.connected = True
            metrics.handshake_time_ms = (handshake_end - connect_start) * 1000

            last_frame_time: float | None = None

            # 1. Wait for initial frame (server needs time to instantiate TimelineReplayer from disk)
            try:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=init_timeout)
                now = time.perf_counter()
                metrics.ttff_ms = (now - handshake_end) * 1000
                metrics.frames_received += 1
                last_frame_time = now
            except asyncio.TimeoutError:
                metrics.errors.append(f"Initial frame timeout (server took >{init_timeout:.0f}s to load session)")
                return

            # 2. Benchmark sustained stream over the requested duration
            session_end_time = time.perf_counter() + duration

            # Background task for sending occasional actions if chaos mode is on
            chaos_task = None
            if chaos_mode:
                chaos_task = asyncio.create_task(
                    _run_chaos_actions(ws, metrics, session_end_time, stop_event)
                )

            try:
                while time.perf_counter() < session_end_time and not stop_event.is_set():
                    try:
                        raw_msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    except asyncio.TimeoutError:
                        metrics.errors.append("Stream stall (>3s without frame)")
                        continue

                    now = time.perf_counter()

                    if last_frame_time is not None:
                        interval = (now - last_frame_time) * 1000
                        metrics.frame_intervals_ms.append(interval)

                    last_frame_time = now
                    metrics.frames_received += 1

                    # Basic packet integrity validation
                    try:
                        data = json.loads(raw_msg)
                        if data.get("error"):
                            metrics.errors.append(f"Server error: {data.get('message')}")
                    except json.JSONDecodeError:
                        metrics.errors.append("Invalid JSON received")
            finally:
                if chaos_task and not chaos_task.done():
                    chaos_task.cancel()

    except websockets.exceptions.ConnectionClosed as e:
        metrics.disconnected_early = True
        metrics.disconnect_code = e.code
        metrics.errors.append(f"Connection closed early: code {e.code}")
    except Exception as e:
        metrics.errors.append(f"Socket connection failure: {type(e).__name__}: {str(e)}")


async def _run_chaos_actions(
    ws,
    metrics: ClientMetrics,
    end_time: float,
    stop_event: asyncio.Event,
) -> None:
    """Randomly dispatch interactive seek, speed, and driver-selection actions."""
    speeds = [0.5, 1.0, 2.0, 5.0]
    driver_pools = [[1, 55], [16, 44], [4, 81], [63, 11]]

    while time.perf_counter() < end_time and not stop_event.is_set():
        # Wait 2 to 5 seconds between random actions
        await asyncio.sleep(random.uniform(2.0, 5.0))
        if stop_event.is_set():
            break

        action_type = random.choice(["seek_percent", "set_speed", "select_drivers"])
        msg = {}

        if action_type == "seek_percent":
            msg = {"action": "seek_percent", "percent": round(random.uniform(0.1, 0.9), 2)}
        elif action_type == "set_speed":
            msg = {"action": "set_speed", "speed": random.choice(speeds)}
        elif action_type == "select_drivers":
            msg = {"action": "select_drivers", "drivers": random.choice(driver_pools)}

        try:
            await ws.send(json.dumps(msg))
            metrics.actions_sent += 1
        except Exception:
            break


async def run_load_test(
    url: str,
    num_clients: int,
    duration: float,
    ramp_up: float,
    chaos_mode: bool,
    init_timeout: float = 30.0,
) -> list[ClientMetrics]:
    """Orchestrate concurrent client simulators."""
    print("=" * 80)
    print("🏎️   PITWALL TELEMETRY ENGINE - WEBSOCKET STRESS TEST RUNNER")
    print("=" * 80)
    print(f"  Target Endpoint  : {url}")
    print(f"  Concurrent Users : {num_clients}")
    print(f"  Streaming Time   : {duration:.1f} seconds (per client after warmup)")
    print(f"  Warmup Timeout   : {init_timeout:.1f} seconds (allow server to load)")
    print(f"  Ramp-up Time     : {ramp_up:.2f} seconds")
    print(f"  Chaos Mode       : {'ON (random seek/speed)' if chaos_mode else 'OFF (passive playback)'}")
    print("-" * 80)
    print("🚀 Spawning client connections...")

    all_metrics: list[ClientMetrics] = [ClientMetrics(client_id=i + 1) for i in range(num_clients)]
    stop_event = asyncio.Event()

    tasks = []
    stagger_delay = ramp_up / num_clients if num_clients > 0 else 0

    start_time = time.perf_counter()

    for i in range(num_clients):
        if stagger_delay > 0 and i > 0:
            await asyncio.sleep(stagger_delay)

        task = asyncio.create_task(
            simulate_client(
                client_id=i + 1,
                url=url,
                duration=duration,
                chaos_mode=chaos_mode,
                metrics=all_metrics[i],
                stop_event=stop_event,
                init_timeout=init_timeout,
            )
        )
        tasks.append(task)

    # Monitor progress with a live ticker
    try:
        while any(not t.done() for t in tasks):
            elapsed = time.perf_counter() - start_time
            active = sum(1 for m in all_metrics if m.connected and not m.disconnected_early)
            frames = sum(m.frames_received for m in all_metrics)
            errs = sum(len(m.errors) for m in all_metrics)
            agg_fps = frames / elapsed if elapsed > 0 else 0

            print(
                f"\r⏱️  [{elapsed:4.1f}s / {duration:.0f}s] Active: {active}/{num_clients} | "
                f"Total Frames: {frames:<6d} | Agg FPS: {agg_fps:5.1f} | Errors: {errs}",
                end="",
                flush=True,
            )
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user. Shutting down active connections...")
        stop_event.set()

    await asyncio.gather(*tasks, return_exceptions=True)
    print("\n" + "-" * 80)
    return all_metrics


def print_report(metrics: list[ClientMetrics], duration: float) -> int:
    """Generate comprehensive diagnostic summary report."""
    total_clients = len(metrics)
    connected_clients = sum(1 for m in metrics if m.connected)
    clean_exits = sum(1 for m in metrics if m.connected and not m.disconnected_early)
    total_frames = sum(m.frames_received for m in metrics)
    total_errors = sum(len(m.errors) for m in metrics)
    total_actions = sum(m.actions_sent for m in metrics)

    handshakes = [m.handshake_time_ms for m in metrics if m.connected]
    ttffs = [m.ttff_ms for m in metrics if m.ttff_ms > 0]
    client_fps = [m.frames_received / duration for m in metrics if m.connected]

    all_intervals: list[float] = []
    for m in metrics:
        all_intervals.extend(m.frame_intervals_ms)

    stalls = sum(1 for interval in all_intervals if interval > 100.0)

    print("\n📊 BENCHMARK RESULTS & METRICS SUMMARY")
    print("=" * 80)
    print(f"  Connections Attempted    : {total_clients}")
    print(f"  Successful Connections   : {connected_clients} ({connected_clients/total_clients*100:.1f}%)")
    print(f"  Clean Sessions Completed : {clean_exits} / {total_clients}")
    print(f"  Total Telemetry Frames   : {total_frames:,}")
    print(f"  Interactive Actions Sent : {total_actions}")
    print(f"  Total Errors Encountered : {total_errors}")

    print("\n⏱️  LATENCY & INITIALIZATION TIMING (ms):")
    if handshakes:
        print(f"  Handshake Latency (avg)  : {statistics.mean(handshakes):.1f} ms  (max: {max(handshakes):.1f} ms)")
    if ttffs:
        print(f"  Time to First Frame (TTFF): {statistics.mean(ttffs):.1f} ms  (min: {min(ttffs):.1f} ms, max: {max(ttffs):.1f} ms)")
        print("    ↳ Note: High TTFF indicates disk I/O bottlenecks in TimelineReplayer.__init__")

    print("\n🏎️  STREAM DELIVERY & STABILITY:")
    if client_fps:
        avg_fps = statistics.mean(client_fps)
        min_fps = min(client_fps)
        print(f"  Average Client FPS       : {avg_fps:.1f} FPS  (target: 30–60 FPS)")
        print(f"  Minimum Client FPS       : {min_fps:.1f} FPS")
    if all_intervals:
        avg_interval = statistics.mean(all_intervals)
        p95_interval = (
            statistics.quantiles(all_intervals, n=20)[18] if len(all_intervals) >= 20 else max(all_intervals)
        )
        print(f"  Mean Frame Interval      : {avg_interval:.1f} ms (target ~33.3 ms for 30 FPS)")
        print(f"  p95 Frame Interval       : {p95_interval:.1f} ms")
        print(f"  Stalls (>100ms jitter)   : {stalls} ({(stalls / len(all_intervals) * 100) if all_intervals else 0:.2f}% of frames)")

    # Print error breakdown if any
    if total_errors > 0:
        print("\n⚠️ ERROR BREAKDOWN:")
        error_counts: dict[str, int] = {}
        for m in metrics:
            for err in m.errors:
                error_counts[err] = error_counts.get(err, 0) + 1
        for err, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  [{count}x] {err}")

    # Verdict
    print("\n" + "=" * 80)
    passed = clean_exits == total_clients and total_errors == 0 and (client_fps and statistics.mean(client_fps) >= 20.0)
    if passed:
        print("🟢 VERDICT: PASS - Engine sustained target concurrency with zero dropped sessions.")
        return 0
    elif connected_clients > 0:
        print("🟡 VERDICT: DEGRADED - Connections survived but latency, jitter, or errors were observed.")
        return 1
    else:
        print("🔴 VERDICT: FAIL - Failed to establish connections or crashed under load.")
        return 2


def main():
    parser = argparse.ArgumentParser(
        description="Pitwall Telemetry Engine - Concurrent WebSocket Stress Tester",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--url",
        default="ws://127.0.0.1:8000/api/ws/telemetry?session_key=9472",
        help="Target WebSocket endpoint URL",
    )
    parser.add_argument(
        "--clients",
        "-c",
        type=int,
        default=5,
        help="Number of concurrent client connections",
    )
    parser.add_argument(
        "--duration",
        "-d",
        type=float,
        default=15.0,
        help="Duration of the load test in seconds",
    )
    parser.add_argument(
        "--ramp-up",
        type=float,
        default=1.0,
        help="Staggered ramp-up duration in seconds",
    )
    parser.add_argument(
        "--init-timeout",
        type=float,
        default=30.0,
        help="Initial warmup timeout in seconds for server to load session data and emit the first frame",
    )
    parser.add_argument(
        "--chaos",
        action="store_true",
        help="Enable chaos mode (sends random seek, speed, and driver-select commands)",
    )

    args = parser.parse_args()

    try:
        metrics = asyncio.run(
            run_load_test(
                url=args.url,
                num_clients=args.clients,
                duration=args.duration,
                ramp_up=args.ramp_up,
                chaos_mode=args.chaos,
                init_timeout=args.init_timeout,
            )
        )
        exit_code = print_report(metrics, args.duration)
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nTest aborted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
