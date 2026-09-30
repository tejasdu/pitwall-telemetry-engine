import asyncio
import time
from bisect import bisect_right
from datetime import datetime, timezone

from pitwall_telemetry_engine.ingestion.openf1_client import (
    get_car_data,
    get_drivers,
    get_intervals,
    get_laps,
    get_location,
    get_pit,
    get_position,
    get_race_control,
    get_session,
)
from pitwall_telemetry_engine.metrics.inferences import (
    calculate_deceleration,
    is_heavy_braking,
)
from pitwall_telemetry_engine.schemas.car_data import CarData
from pitwall_telemetry_engine.schemas.driver import Driver
from pitwall_telemetry_engine.schemas.location import Location


class DriverTimeline:
    """Helper Class: Stores a specific Driver's Telemetry information to be used for a session Timeline Replayer"""

    def __init__(
        self,
        driver_number: int,
        locations: list[Location],
        telemetry: list[CarData],
        session_start_time: float | None = None,
    ):
        self.driver_number = driver_number

        # 1. Filter out stationary (0, 0) coordinates and pre-race activity
        valid_locs = [
            loc
            for loc in locations
            if (loc.x != 0 or loc.y != 0)
            and (session_start_time is None or loc.date.timestamp() >= session_start_time)
        ]

        self.loc_times = [loc.date.timestamp() for loc in valid_locs]
        self.xs = [loc.x for loc in valid_locs]
        self.ys = [loc.y for loc in valid_locs]

        # 2. Filter telemetry ticks
        valid_tel = [
            t
            for t in telemetry
            if session_start_time is None or t.date.timestamp() >= session_start_time
        ]
        self.tel_times = [tel.date.timestamp() for tel in valid_tel]
        self.telemetry = valid_tel

    def get_position_at(self, t_sim_sec: float) -> tuple[float, float] | None:
        if not self.loc_times:
            return None

        # Boundary checks
        if t_sim_sec <= self.loc_times[0]:
            return (self.xs[0], self.ys[0])
        if t_sim_sec >= self.loc_times[-1]:
            return (self.xs[-1], self.ys[-1])

        # Binary search for bounding window
        idx = bisect_right(self.loc_times, t_sim_sec) - 1

        t_prev = self.loc_times[idx]
        t_next = self.loc_times[idx + 1]

        dt = t_next - t_prev
        alpha = 0.0 if dt <= 0 else (t_sim_sec - t_prev) / dt

        x = self.xs[idx] + (self.xs[idx + 1] - self.xs[idx]) * alpha
        y = self.ys[idx] + (self.ys[idx + 1] - self.ys[idx]) * alpha

        return (round(x, 2), round(y, 2))

    def get_telemetry_at(self, t_sim_sec: float) -> CarData | None:
        """Returns the closest telemetry tick at t_sim_sec."""
        if not self.tel_times:
            return None

        if t_sim_sec <= self.tel_times[0]:
            return self.telemetry[0]
        if t_sim_sec >= self.tel_times[-1]:
            return self.telemetry[-1]

        idx = bisect_right(self.tel_times, t_sim_sec) - 1
        return self.telemetry[idx]


class TimelineReplayer:
    """
    Master simulation engine for Pitwall v2.
    Synchronizes 20-driver coordinates, active drawer telemetry, timing intervals,
    and FIA race flags under a unified simulation clock (T_sim) running at 30-60 Hz.
    """

    def __init__(self, session_key: str | int = "latest", fps: int = 30):
        self.session_key = session_key
        self.fps = fps
        self.frame_interval = 1.0 / fps

        # 1. Load session metadata and Driver Registry
        self.session = get_session(session_key)
        self.drivers: dict[int, Driver] = get_drivers(session_key)

        if not self.drivers:
            raise ValueError(f"No driver or telemetry records found for session {session_key}")

        if not self.session.date_start or not self.session.date_end:
            raise ValueError(f"Session {session_key} does not have valid start and end timestamps")

        # 2. Set simulation time boundaries (Unix epoch seconds)
        self.start_time = self.session.date_start.timestamp()
        self.end_time = self.session.date_end.timestamp()
        if self.end_time <= self.start_time:
            raise ValueError(f"Session {session_key} duration is invalid (end <= start)")
        self.t_sim = self.start_time

        # 3. Playback control state
        self.is_playing = False
        self.playback_speed = (
            1.0  # 1x, 2x, 5x, 10x TO CHANGE; SHOULD LET USER CONTROL (FOR MODE A: Session Replay)
        )

        # 4. Load timelines for all 20 drivers
        print(
            f"🏎️  Loading 20-driver grid for {self.session.circuit_short_name} ({self.session.year})..."
        )
        self.timelines: dict[int, DriverTimeline] = {}
        for d_num in self.drivers.keys():
            locs = get_location(session_key, driver_number=d_num)
            tel = get_car_data(session_key, driver_number=d_num)
            self.timelines[d_num] = DriverTimeline(
                driver_number=d_num,
                locations=locs,
                telemetry=tel,
                session_start_time=self.start_time,
            )

        # Ensure that at least one driver has telemetry or coordinates
        has_any_data = any(
            len(tl.telemetry) > 0 or len(tl.loc_times) > 0 for tl in self.timelines.values()
        )
        if not has_any_data:
            raise ValueError(f"No telemetry or GPS coordinates recorded for session {session_key}")

        # 5. Load and index macro intervals, positions & race control events
        self.intervals = sorted(get_intervals(session_key), key=lambda i: i.date)
        self.interval_times = [i.date.timestamp() for i in self.intervals]

        self.positions = sorted(get_position(session_key), key=lambda p: p.date)
        self.position_times = [p.date.timestamp() for p in self.positions]

        self.race_control = sorted(get_race_control(session_key), key=lambda m: m.date)
        self.rc_times = [m.date.timestamp() for m in self.race_control]

        self.pits_by_driver = {}
        for p in get_pit(session_key):
            if p.driver_number not in self.pits_by_driver:
                self.pits_by_driver[p.driver_number] = []
            self.pits_by_driver[p.driver_number].append(p)

        self.laps_by_driver = {}
        for lap in get_laps(session_key):
            if lap.driver_number not in self.laps_by_driver:
                self.laps_by_driver[lap.driver_number] = []
            if lap.lap_duration and lap.date_start:
                self.laps_by_driver[lap.driver_number].append(lap)
        for d in self.laps_by_driver:
            self.laps_by_driver[d].sort(key=lambda x: x.date_start)

        self.starting_positions = {}
        for p in sorted(get_position(session_key), key=lambda x: x.date):
            if p.driver_number not in self.starting_positions:
                self.starting_positions[p.driver_number] = p.position

        # Cache previous ticks per driver to compute deceleration gradients
        self._prev_ticks: dict[int, CarData] = {}

    def play(self) -> None:
        """Starts or resumes race playback."""
        self.is_playing = True

    def pause(self) -> None:
        """Pauses race playback."""
        self.is_playing = False

    def toggle_play(self) -> bool:
        """Toggles between play and pause states."""
        self.is_playing = not self.is_playing
        return self.is_playing

    def set_speed(self, multiplier: float) -> None:
        """Sets playback speed multiplier (bounded between 0.25x and 50x)."""
        self.playback_speed = max(0.25, min(50.0, float(multiplier)))

    def seek(self, target_time_sec: float) -> None:
        """Jumps directly to a specific timestamp in the race."""
        self.t_sim = max(self.start_time, min(self.end_time, target_time_sec))

    def seek_percent(self, pct: float) -> None:
        """Jumps to a percentage through the race (0.0 to 1.0)."""
        clamped = max(0.0, min(1.0, pct))
        self.seek(self.start_time + clamped * (self.end_time - self.start_time))

    def get_race_control_state(self) -> dict:
        """
        Computes the complete race control state at current t_sim:
        - Global flag: GREEN, YELLOW, SC, VSC, RED, CHEQUERED
        - Active caution sectors: e.g. [2, 4] for track map highlights
        - DRS global status: True/False
        - Recent messages (last 5) for the broadcast ticker overlay
        - Recent driver-specific flags (e.g. BLUE, BLACK AND WHITE)
        """
        if not self.rc_times:
            return {
                "flag": "GREEN",
                "sectors": [],
                "drs_enabled": True,
                "messages": [],
                "driver_flags": {},
            }

        idx = bisect_right(self.rc_times, self.t_sim) - 1
        if idx < 0:
            return {
                "flag": "GREEN",
                "sectors": [],
                "drs_enabled": True,
                "messages": [],
                "driver_flags": {},
            }

        # 1. Collect last 5 messages for the UI ticker feed
        recent_messages = []
        for i in range(idx, max(-1, idx - 5), -1):
            m = self.race_control[i]
            recent_messages.append(
                {
                    "date": m.date.isoformat(),
                    "category": m.category,
                    "flag": m.flag,
                    "scope": m.scope,
                    "sector": m.sector,
                    "driver_number": m.driver_number,
                    "message": m.message,
                }
            )

        # 2. Determine global track flag and yellow sectors
        active_flag = "GREEN"
        sector_status: dict[int, str] = {}
        drs_enabled = True
        drs_checked = False
        driver_flags: dict[int, str] = {}

        # Scan backwards from current event
        for i in range(idx, -1, -1):
            msg = self.race_control[i]
            flag_val = (msg.flag or "").upper()
            msg_text = (msg.message or "").upper()
            cat = (msg.category or "").upper()

            # Driver-specific flags (within last 30s of t_sim)
            if msg.driver_number is not None and flag_val in ("BLUE", "BLACK AND WHITE"):
                if msg.driver_number not in driver_flags:
                    if (self.t_sim - self.rc_times[i]) <= 30.0:
                        driver_flags[msg.driver_number] = flag_val

            # Track global DRS state
            if not drs_checked and cat == "DRS":
                if "ENABLED" in msg_text:
                    drs_enabled = True
                    drs_checked = True
                elif "DISABLED" in msg_text:
                    drs_enabled = False
                    drs_checked = True

            # Track-wide session conclusion
            if flag_val == "CHEQUERED" or "CHEQUERED FLAG" in msg_text:
                active_flag = "CHEQUERED"
                break

            # Track-wide emergency red flag
            if "RED FLAG" in msg_text or flag_val == "RED":
                active_flag = "RED"
                break

            # Safety Car / Virtual Safety Car
            if "SAFETY CAR" in msg_text or "VSC" in msg_text:
                active_flag = "SC"
                break

            # Sector yellow vs clear status resolution
            if msg.sector is not None:
                if msg.sector not in sector_status:
                    if flag_val in ("YELLOW", "DOUBLE YELLOW") or "YELLOW" in msg_text:
                        sector_status[msg.sector] = "YELLOW"
                    elif flag_val in ("CLEAR", "GREEN") or "CLEAR" in msg_text:
                        sector_status[msg.sector] = "CLEAR"

            # Global track clear
            if msg.scope == "Track" and (
                flag_val in ("CLEAR", "GREEN") or "TRACK CLEAR" in msg_text
            ):
                if not any(status == "YELLOW" for status in sector_status.values()):
                    active_flag = "GREEN"
                    break

        yellow_sectors = sorted([s for s, status in sector_status.items() if status == "YELLOW"])
        if active_flag not in ("RED", "SC", "CHEQUERED") and yellow_sectors:
            active_flag = "YELLOW"

        return {
            "flag": active_flag,
            "sectors": yellow_sectors,
            "drs_enabled": drs_enabled,
            "messages": recent_messages,
            "driver_flags": driver_flags,
        }

    def get_current_flag(self) -> str:
        return self.get_race_control_state()["flag"]

    def get_latest_intervals(self) -> dict[int, dict]:
        """Returns the latest position, gap, and interval for each driver at t_sim."""
        latest_by_driver: dict[int, dict] = {}

        # 1. Fetch latest official positions
        if self.position_times:
            idx = bisect_right(self.position_times, self.t_sim) - 1
            if idx >= 0:
                start_search = max(0, idx - 1000)
                for i in range(idx, start_search - 1, -1):
                    rec = self.positions[i]
                    if rec.driver_number not in latest_by_driver:
                        latest_by_driver[rec.driver_number] = {"position": rec.position}
                    if len(latest_by_driver) >= len(self.drivers):
                        break

        # 2. Fetch latest intervals and gaps
        if self.interval_times:
            idx = bisect_right(self.interval_times, self.t_sim) - 1
            if idx >= 0:
                start_search = max(0, idx - 1000)
                drivers_found = set()
                for i in range(idx, start_search - 1, -1):
                    rec = self.intervals[i]
                    if rec.driver_number not in drivers_found:
                        drivers_found.add(rec.driver_number)
                        if rec.driver_number not in latest_by_driver:
                            latest_by_driver[rec.driver_number] = {}
                        latest_by_driver[rec.driver_number]["interval"] = rec.interval
                        latest_by_driver[rec.driver_number]["gap_to_leader"] = rec.gap_to_leader
                    if len(drivers_found) >= len(self.drivers):
                        break

        return latest_by_driver

    def detect_battles(self, flag: str, intervals_map: dict[int, dict]) -> list[dict]:
        """
        Identifies active battles, DRS attack windows, and dive-bomb threats.
        """
        # DRS & overtaking is prohibited under a flag
        if flag in ("YELLOW", "SC", "RED"):
            return []

        battles = []
        for d_num, data in intervals_map.items():
            gap = data.get("interval")
            if isinstance(gap, (int, float)) and 0.0 < gap <= 1.0:
                # Driver is within DRS threat window (<= 1.000s)
                tl = self.timelines.get(d_num)
                curr_tick = tl.get_telemetry_at(self.t_sim) if tl else None
                prev_tick = self._prev_ticks.get(d_num)

                decel = (
                    calculate_deceleration(prev_tick, curr_tick)
                    if prev_tick and curr_tick
                    else None
                )
                dive_bomb = (
                    gap <= 0.400 and curr_tick is not None and is_heavy_braking(curr_tick, decel)
                )

                battles.append(
                    {
                        "attacker": d_num,
                        "gap": round(gap, 3),
                        "is_drs_threat": True,
                        "is_dive_bomb": dive_bomb,
                    }
                )

                if curr_tick:
                    self._prev_ticks[d_num] = curr_tick

        return battles

    def assemble_frame(self, selected_drivers: list[int] | None = None) -> dict:
        """
        Packs a complete, broadcast-grade telemetry frame at current t_sim.
        Includes 20-car 2D coordinates, deep telemetry for active drivers, flag state, and battles.
        """
        target_drivers = selected_drivers if selected_drivers is not None else [1, 55]

        # 1. 2D Map: All 20 moving driver coordinates (sub-frame interpolated)
        positions = []
        for d_num, tl in self.timelines.items():
            pos = tl.get_position_at(self.t_sim)
            if pos is not None:
                drv = self.drivers.get(d_num)
                positions.append(
                    {
                        "driver_number": d_num,
                        "acronym": drv.name_acronym if drv else f"#{d_num}",
                        "team_color": drv.team_colour if drv else "ffffff",
                        "x": pos[0],
                        "y": pos[1],
                    }
                )

        # 2. Cockpit Drawer: Deep high-frequency telemetry for active 1-3 drivers
        telemetry = {}
        for d_num in target_drivers:
            tl = self.timelines.get(d_num)
            if tl:
                tick = tl.get_telemetry_at(self.t_sim)
                if tick:
                    telemetry[str(d_num)] = {
                        "speed": tick.speed,
                        "rpm": tick.rpm,
                        "gear": tick.n_gear,
                        "throttle": tick.throttle,
                        "brake": tick.brake,
                        "drs": tick.drs,
                    }

        # 3. Track caution flag status and race control events
        rc_state = self.get_race_control_state()
        flag = rc_state["flag"]

        # 4. Gaps, battles, and status flags (PIT / DNF)
        intervals_map = self.get_latest_intervals()
        battles = self.detect_battles(flag, intervals_map)

        for d_num in self.drivers.keys():
            if d_num not in intervals_map:
                intervals_map[d_num] = {}

            in_pit = False
            pits = self.pits_by_driver.get(d_num, [])
            pit_count = 0
            for p in pits:
                if p.date.timestamp() <= self.t_sim:
                    pit_count += 1
                if p.pit_duration:
                    end_time = p.date.timestamp() + p.pit_duration
                    if p.date.timestamp() <= self.t_sim <= end_time:
                        in_pit = True

            is_dnf = False
            tl = self.timelines.get(d_num)
            if not in_pit and flag not in ("RED", "SC", "CHEQUERED"):
                if tl:
                    last_tel = tl.tel_times[-1] if tl.tel_times else 0
                    last_loc = tl.loc_times[-1] if tl.loc_times else 0
                    last_update = max(last_tel, last_loc)
                    if last_update > 0 and self.t_sim - last_update > 120:
                        is_dnf = True

            last_lap = None
            for lap in self.laps_by_driver.get(d_num, []):
                if lap.date_start.timestamp() + lap.lap_duration <= self.t_sim:
                    last_lap = lap.lap_duration
                else:
                    break

            curr_pos = intervals_map[d_num].get("position", 0)
            start_pos = self.starting_positions.get(d_num, curr_pos)
            pos_change = start_pos - curr_pos if curr_pos > 0 else 0

            intervals_map[d_num]["in_pit"] = in_pit
            intervals_map[d_num]["is_dnf"] = is_dnf
            intervals_map[d_num]["pit_count"] = pit_count
            intervals_map[d_num]["last_lap_time"] = last_lap
            intervals_map[d_num]["pos_change"] = pos_change

        # 5. Progress calculation
        total_duration = max(1.0, self.end_time - self.start_time)
        progress_pct = round(
            max(0.0, min(1.0, (self.t_sim - self.start_time) / total_duration)) * 100,
            2,
        )

        return {
            "t_sim": self.t_sim,
            "t_sim_iso": datetime.fromtimestamp(self.t_sim, tz=timezone.utc).isoformat(),
            "progress_pct": progress_pct,
            "is_playing": self.is_playing,
            "playback_speed": self.playback_speed,
            "flag": flag,
            "caution_sectors": rc_state["sectors"],
            "drs_enabled": rc_state["drs_enabled"],
            "driver_flags": rc_state["driver_flags"],
            "race_control_messages": rc_state["messages"],
            "positions": positions,
            "telemetry": telemetry,
            "battles": battles,
            "intervals": {str(k): v for k, v in intervals_map.items()},
        }

    def step(self, dt: float | None = None, selected_drivers: list[int] | None = None) -> dict:
        """Advances the simulation clock by one frame interval & returns new frame"""
        step_dt = (dt if dt is not None else self.frame_interval) * self.playback_speed
        self.t_sim = min(self.end_time, self.t_sim + step_dt)

        return self.assemble_frame(selected_drivers=selected_drivers)

    async def stream_frames(self, get_selected_drivers_cb=None):
        """Streams broadcast frames at the target FPS."""
        self.is_playing = True
        frame_dt = self.frame_interval

        while self.t_sim < self.end_time:
            loop_start = time.perf_counter()

            selected = get_selected_drivers_cb() if callable(get_selected_drivers_cb) else None

            if self.is_playing:
                # Advance clock and emit frame
                frame = self.step(selected_drivers=selected)
            else:
                # Keep stream alive but do not advance clock
                frame = self.assemble_frame(selected_drivers=selected)

            yield frame

            # Drift compensation: sleep only the remaining time in this frame window
            elapsed = time.perf_counter() - loop_start
            sleep_time = max(0.0, frame_dt - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
