"""Deterministic battle regression tests."""

from datetime import datetime, timezone

import pytest

from pitwall_telemetry_engine.ingestion.timeline_replayer import TimelineReplayer
from pitwall_telemetry_engine.schemas.intervals import Intervals
from pitwall_telemetry_engine.schemas.pit import Pit
from pitwall_telemetry_engine.schemas.position import Position
from pitwall_telemetry_engine.schemas.race_control import RaceControlMessage


def at(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc)


@pytest.fixture
def replay(race_cache):
    cache, session_key = race_cache
    replayer = TimelineReplayer(cache.get_sync(session_key))
    replayer.seek(111)
    return replayer


def test_close_battle_names_actual_pair_without_attack_claims(replay):
    assert replay.assemble_frame()["battles"] == [{"attacker": 55, "defender": 16, "gap": 0.6}]


@pytest.mark.parametrize("gap", [None, "+1 LAP", 0, -0.2, 1.001, float("nan"), float("inf")])
def test_invalid_or_non_close_intervals_are_not_battles(replay, gap):
    replay.intervals[-1].interval = gap
    assert replay.assemble_frame()["battles"] == []


def test_one_second_boundary_is_included(replay):
    replay.intervals[-1].interval = 1.0
    assert replay.assemble_frame()["battles"][0]["gap"] == 1.0


@pytest.mark.parametrize("flag", ["YELLOW", "SC", "VSC", "RED", "CHEQUERED", "UNKNOWN"])
def test_non_racing_flags_suppress_battles(replay, flag):
    assert replay.detect_battles(flag, replay.get_latest_intervals()) == []


def test_drs_permission_does_not_define_a_close_battle(replay):
    replay.race_control.append(
        RaceControlMessage(session_key=1, date=at(105), category="Drs", message="DRS DISABLED")
    )
    replay.rc_times.append(105)
    frame = replay.assemble_frame()
    assert frame["drs_enabled"] is False
    assert frame["battles"] == [{"attacker": 55, "defender": 16, "gap": 0.6}]


@pytest.mark.parametrize("driver_number", [16, 55])
@pytest.mark.parametrize("duration_field", ["pit_duration", "lane_duration"])
def test_pit_status_is_applied_before_battle_detection(replay, driver_number, duration_field):
    replay.pits_by_driver[driver_number] = [
        Pit(
            session_key=1,
            meeting_key=1,
            driver_number=driver_number,
            date=at(105),
            **{duration_field: 20},
        )
    ]
    frame = replay.assemble_frame()
    assert frame["intervals"][str(driver_number)]["in_pit"] is True
    assert frame["battles"] == []


def test_pit_lane_duration_takes_priority_over_stop_duration(replay):
    replay.pits_by_driver[16] = [
        Pit(
            session_key=1,
            meeting_key=1,
            driver_number=16,
            date=at(105),
            pit_duration=2,
            lane_duration=20,
        )
    ]
    assert replay.assemble_frame()["battles"] == []


@pytest.mark.parametrize("driver_number", [16, 55])
def test_retired_driver_cannot_be_in_a_battle(replay, driver_number):
    intervals = replay.get_latest_intervals()
    intervals[driver_number]["is_dnf"] = True
    assert replay.detect_battles("GREEN", intervals) == []


@pytest.mark.parametrize("driver_number", [16, 55])
def test_lapped_status_is_not_mistaken_for_same_lap_battle(replay, driver_number):
    for interval in replay.intervals:
        if interval.driver_number == driver_number:
            interval.gap_to_leader = "+1 LAP"
    assert replay.assemble_frame()["battles"] == []


@pytest.mark.parametrize("timestamp", [100, 121])
def test_missing_or_stale_intervals_are_hidden(replay, timestamp):
    replay.seek(timestamp)
    assert replay.assemble_frame()["battles"] == []


@pytest.mark.parametrize("driver_number", [16, 55])
@pytest.mark.parametrize("samples", [[], [100], [120]])
def test_missing_stale_or_future_activity_is_not_used(replay, driver_number, samples):
    timeline = replay.timelines[driver_number]
    timeline.tel_times = samples
    timeline.loc_times = samples
    assert replay.detect_battles("GREEN", replay.get_latest_intervals()) == []


def test_missing_defender_does_not_fall_back_to_another_driver(replay):
    intervals = replay.get_latest_intervals()
    del intervals[16]
    assert replay.detect_battles("GREEN", intervals) == []


@pytest.mark.parametrize("position", [2, 3])
def test_ambiguous_positions_suppress_battles(replay, position):
    intervals = replay.get_latest_intervals()
    intervals[1]["position"] = position
    assert replay.detect_battles("GREEN", intervals) == []


def test_position_changes_wait_for_a_new_interval(replay):
    replay.positions.extend(
        [
            Position(session_key=1, meeting_key=1, date=at(111), driver_number=1, position=2),
            Position(session_key=1, meeting_key=1, date=at(111), driver_number=16, position=1),
        ]
    )
    replay.position_times.extend([111, 111])
    assert replay.assemble_frame()["battles"] == []
    replay.intervals.append(
        Intervals(
            session_key=1,
            meeting_key=1,
            date=at(112),
            driver_number=55,
            interval=0.7,
            gap_to_leader=2.7,
        )
    )
    replay.interval_times.append(112)
    replay.seek(112)
    assert replay.assemble_frame()["battles"] == [{"attacker": 55, "defender": 1, "gap": 0.7}]


def test_seek_pause_restart_and_independent_cursors_are_deterministic(replay):
    expected = replay.assemble_frame()["battles"]
    assert replay.assemble_frame()["battles"] == expected
    replay.seek(109)
    assert replay.step(dt=2)["battles"] == expected
    replay.seek(150)
    assert replay.assemble_frame()["battles"] == []
    replay.seek(111)
    assert replay.assemble_frame()["battles"] == expected
    replay.seek(replay.end_time)
    assert replay.assemble_frame()["battles"] == []
    replay.play()
    replay.seek(111)
    assert replay.assemble_frame()["battles"] == expected
    independent = TimelineReplayer(replay.dataset)
    independent.seek(111)
    assert independent.assemble_frame()["battles"] == expected
