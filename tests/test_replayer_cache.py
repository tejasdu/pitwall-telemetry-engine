"""Tests for SessionDataset, SessionCache, and TimelineReplayer concurrency."""

import asyncio
from contextlib import aclosing
from datetime import datetime, timezone
from threading import Event

import pytest

from pitwall_telemetry_engine.ingestion.timeline_replayer import (
    SessionCache,
    SessionDataset,
    TimelineReplayer,
)
from pitwall_telemetry_engine.schemas.race_control import RaceControlMessage


def test_session_dataset_loading(race_cache):
    """Verify SessionDataset loads metadata and synthetic grid properly."""
    session_cache, session_key = race_cache
    dataset = session_cache.get_sync(session_key)
    assert dataset.session_key == session_key
    assert set(dataset.drivers) == {1, 16, 55}
    assert dataset.end_time > dataset.start_time
    assert set(dataset.timelines) == set(dataset.drivers)


def test_session_cache_identity(race_cache):
    """Verify second access returns identical cached object in memory (0ms lookup)."""
    session_cache, session_key = race_cache
    d1 = session_cache.get_sync(session_key)
    d2 = session_cache.get_sync(session_key)
    assert d1 is d2


@pytest.mark.anyio
async def test_session_cache_async_get(race_cache):
    """Verify async get with stampede protection returns cached dataset."""
    session_cache, session_key = race_cache
    dataset = await session_cache.get(session_key)
    assert dataset is not None
    assert dataset.session_key == session_key


def test_independent_replayer_cursors(race_cache):
    """Verify multiple replayers share dataset but maintain isolated playback state."""
    session_cache, session_key = race_cache
    dataset = session_cache.get_sync(session_key)

    replayer_a = TimelineReplayer(dataset, fps=30)
    replayer_b = TimelineReplayer(dataset, fps=30)

    # User A seeks to 10%
    replayer_a.seek_percent(0.10)
    # User B seeks to 50%
    replayer_b.seek_percent(0.50)

    assert replayer_a.t_sim != replayer_b.t_sim
    assert replayer_a.t_sim < replayer_b.t_sim

    # Advancing User A does not affect User B
    replayer_a.play()
    frame_a = replayer_a.step()

    assert "progress_pct" in frame_a
    assert "positions" in frame_a
    assert replayer_b.is_playing is False


@pytest.mark.anyio
async def test_cached_session_is_available_during_another_load(monkeypatch):
    cache = SessionCache(max_sessions=1)
    loop = asyncio.get_running_loop()
    load_started = asyncio.Event()
    release_load = Event()

    def load_dataset(self, session_key):
        self.session_key = session_key
        if session_key == 2:
            loop.call_soon_threadsafe(load_started.set)
            assert release_load.wait(timeout=5)

    monkeypatch.setattr(SessionDataset, "__init__", load_dataset)
    cached_dataset = cache.get_sync(1)
    loading = asyncio.create_task(cache.get(2))
    try:
        await asyncio.wait_for(load_started.wait(), timeout=5)
        cached_request = asyncio.create_task(cache.get(1))
        await asyncio.sleep(0)
        served_during_load = cached_request.done()
    finally:
        release_load.set()
        await loading

    assert await cached_request is cached_dataset
    assert served_during_load


@pytest.mark.anyio
async def test_interactive_replay_can_seek_and_resume_after_finish(race_cache):
    session_cache, session_key = race_cache
    replayer = TimelineReplayer(session_cache.get_sync(session_key))
    replayer.seek(replayer.end_time - replayer.frame_interval / 2)

    async with aclosing(replayer.stream_frames(keep_alive_at_end=True)) as frames:
        final_frame = await anext(frames)
        assert final_frame["progress_pct"] == 100
        assert final_frame["is_playing"] is False

        replayer.seek_percent(0.5)
        paused_frame = await anext(frames)
        assert paused_frame["progress_pct"] == 50
        assert paused_frame["is_playing"] is False

        replayer.play()
        resumed_frame = await anext(frames)
        assert resumed_frame["t_sim"] > paused_frame["t_sim"]
        assert resumed_frame["is_playing"] is True

        replayer.seek_percent(1.0)
        assert (await anext(frames))["is_playing"] is False

        replayer.toggle_play()
        restarted_frame = await anext(frames)
        assert replayer.start_time < restarted_frame["t_sim"] < paused_frame["t_sim"]
        assert restarted_frame["is_playing"] is True


def test_race_control_tracks_cautions_and_drs_independently():
    replayer = TimelineReplayer.__new__(TimelineReplayer)
    events = [
        {"category": "Drs", "message": "DRS DISABLED"},
        {"category": "Flag", "scope": "Track", "flag": "GREEN"},
        {"category": "Other", "message": "SAFETY CAR LIGHTS ON"},
        {"category": "SafetyCar", "message": "VSC DEPLOYED"},
        {"category": "SafetyCar", "message": "VIRTUAL SAFETY CAR ENDING"},
        {"category": "Flag", "scope": "Track", "flag": "CLEAR", "message": "TRACK CLEAR"},
        {"category": "Drs", "message": "DRS ENABLED"},
        {"category": "SafetyCar", "message": "SAFETY CAR DEPLOYED"},
        {"category": "SafetyCar", "message": "SAFETY CAR IN THIS LAP"},
        {"category": "Flag", "scope": "Track", "flag": "CLEAR", "message": "TRACK CLEAR"},
    ]
    replayer.rc_times = list(range(1, len(events) + 1))
    replayer.race_control = [
        RaceControlMessage(
            session_key=1, date=datetime.fromtimestamp(timestamp, timezone.utc), **event
        )
        for timestamp, event in zip(replayer.rc_times, events, strict=True)
    ]

    for timestamp, flag, drs_enabled in [
        (3, "GREEN", False),
        (4, "VSC", False),
        (5, "VSC", False),
        (6, "GREEN", False),
        (7, "GREEN", True),
        (9, "SC", True),
        (10, "GREEN", True),
        (5, "VSC", False),
    ]:
        replayer.t_sim = timestamp
        state = replayer.get_race_control_state()
        assert state["flag"] == flag
        assert state["drs_enabled"] is drs_enabled


def test_replay_reports_tyres_for_the_drivers_lap_after_seeking(race_cache):
    session_cache, session_key = race_cache
    replayer = TimelineReplayer(session_cache.get_sync(session_key))
    lap_start = next(
        lap.date_start
        for lap in replayer.laps_by_driver[1]
        if lap.lap_number == 2 and lap.date_start is not None
    )
    for offset, compound in [(-1, "SOFT"), (0, "HARD"), (-1, "SOFT")]:
        replayer.seek(lap_start.timestamp() + offset)
        intervals = replayer.assemble_frame()["intervals"]
        assert intervals["1"]["tyre_compound"] == compound
        assert intervals["16"]["tyre_compound"] == "SOFT"


def test_session_cache_lru_eviction():
    """Verify LRU cache evicts oldest session when max_sessions is exceeded."""
    small_cache = SessionCache(max_sessions=2)
    # Pre-populate dummy objects
    d1 = SessionDataset.__new__(SessionDataset)
    d1.session_key = 1
    d2 = SessionDataset.__new__(SessionDataset)
    d2.session_key = 2
    d3 = SessionDataset.__new__(SessionDataset)
    d3.session_key = 3

    small_cache._cache[1] = d1
    small_cache._access_order.append(1)

    small_cache._cache[2] = d2
    small_cache._access_order.append(2)

    # Insert 3rd item
    small_cache._cache[3] = d3
    small_cache._access_order.append(3)
    small_cache._evict_if_needed()

    assert 1 not in small_cache._cache
    assert 2 in small_cache._cache
    assert 3 in small_cache._cache
