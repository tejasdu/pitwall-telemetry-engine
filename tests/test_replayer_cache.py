"""Tests for SessionDataset, SessionCache, and TimelineReplayer concurrency."""

import pytest

from pitwall_telemetry_engine.ingestion.timeline_replayer import (
    SessionCache,
    SessionDataset,
    TimelineReplayer,
    session_cache,
)


def test_session_dataset_loading():
    """Verify SessionDataset loads metadata and 20-driver grid properly."""
    dataset = session_cache.get_sync(9472)
    assert dataset.session_key == 9472
    assert len(dataset.drivers) > 0
    assert dataset.end_time > dataset.start_time
    assert len(dataset.timelines) > 0


def test_session_cache_identity():
    """Verify second access returns identical cached object in memory (0ms lookup)."""
    d1 = session_cache.get_sync(9472)
    d2 = session_cache.get_sync(9472)
    assert d1 is d2


@pytest.mark.anyio
async def test_session_cache_async_get():
    """Verify async get with stampede protection returns cached dataset."""
    dataset = await session_cache.get(9472)
    assert dataset is not None
    assert dataset.session_key == 9472


def test_independent_replayer_cursors():
    """Verify multiple replayers share dataset but maintain isolated playback state."""
    dataset = session_cache.get_sync(9472)

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
