import json
import re
import socket
from threading import Thread
from time import monotonic

import pytest
import uvicorn

from pitwall_telemetry_engine.api import app as app_module
from pitwall_telemetry_engine.api import websocket_manager
from pitwall_telemetry_engine.ingestion.timeline_replayer import SessionCache


@pytest.fixture
def replay_server(isolated_cache_and_http, write_cached_race, monkeypatch):
    cache_dir = isolated_cache_and_http
    sessions = [
        write_cached_race(9472, country="Alpha"),
        write_cached_race(2, country="Beta", start=3700, drivers=(4, 44, 63)),
    ]
    calendar = cache_dir.parent / "calendar"
    calendar.mkdir()
    (calendar / "sessions_2026_Race.json").write_text(json.dumps(sessions), encoding="utf-8")
    for session, points in zip(
        sessions,
        [
            [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 0, "y": 100}],
            [{"x": 0, "y": 0}, {"x": 100, "y": 100}, {"x": 0, "y": 200}],
        ],
        strict=True,
    ):
        geometry = cache_dir / str(session["session_key"]) / "track_geometry.json"
        geometry.write_text(json.dumps({"points": points}), encoding="utf-8")

    cache = SessionCache()
    monkeypatch.setattr(app_module, "session_cache", cache)
    monkeypatch.setattr(websocket_manager, "session_cache", cache)
    server = uvicorn.Server(uvicorn.Config(app_module.app, timeout_graceful_shutdown=2))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        worker = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        worker.start()
        try:
            deadline = monotonic() + 5
            while not server.started and worker.is_alive() and monotonic() < deadline:
                worker.join(timeout=0.02)
            assert server.started, "Local replay server did not start"
            yield url
        finally:
            server.should_exit = True
            worker.join(timeout=5)
            assert not worker.is_alive(), "Local replay server did not shut down"


@pytest.mark.browser
def test_launch_compare_switch_and_restart_in_chromium(replay_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(5000)
            page.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(f"{replay_server}/")
                    else route.abort()
                ),
            )
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(replay_server)
            overlay = page.locator("#mission-control-overlay")
            picker = page.locator("#mc-session-select")
            launch_button = page.locator("#mc-launch-btn")
            clock = page.locator("#race-clock")
            comparison = page.locator("#active-duel-label")
            scrubber = page.locator("#scrubber")
            play_button = page.locator("#play-pause-btn")
            playing_icon = page.locator("#play-icon rect")

            def launch(session_key, country, start_clock, driver):
                expect(overlay).to_be_visible()
                picker.select_option(str(session_key))
                with page.expect_response(
                    f"{replay_server}/api/track-geometry?session_key={session_key}"
                ) as geometry:
                    launch_button.click()
                assert geometry.value.ok, f"Track geometry returned HTTP {geometry.value.status}"
                expect(overlay).to_be_hidden()
                expect(page.locator("#session-title")).to_contain_text(
                    f"{country} GP", ignore_case=True
                )
                expect(clock).to_have_text(re.compile(start_clock))
                expect(clock.locator("xpath=..")).to_contain_text("UTC")
                expect(page.locator(f'.tower-row[data-driver="{driver}"]')).to_be_visible()
                expect(page.locator("#track-canvas")).to_be_visible()

            launch(9472, "Alpha", r"^00:01:4\d$", 55)
            expect(playing_icon).to_have_count(2)
            play_button.click()
            expect(playing_icon).to_have_count(0)
            scrubber.fill("5.5")
            expect(clock).to_have_text("00:01:51")
            page.get_by_role("button", name="Compare D55 with D16: close battle").click()
            expect(comparison).to_have_text("COMPARING D55 VS D16")

            page.locator("#change-session-btn").click()
            launch(2, "Beta", r"^01:01:4\d$", 63)
            expect(page.locator('.tower-row[data-driver="55"]')).to_have_count(0)
            expect(comparison).to_have_text("COMPARING D4 VS D44")
            expect(page.locator("#scrubber-pct")).to_have_text(re.compile(r"^[0-4]\.\d%$"))

            page.locator("#change-session-btn").click()
            launch(9472, "Alpha", r"^00:01:4\d$", 55)
            expect(page.locator('.tower-row[data-driver="63"]')).to_have_count(0)
            scrubber.fill("100")
            expect(clock).to_have_text("00:05:00")
            expect(playing_icon).to_have_count(0)
            play_button.click()
            expect(clock).to_have_text(re.compile(r"^00:01:4\d$"))
            expect(playing_icon).to_have_count(2)
            assert not errors
        finally:
            browser.close()
