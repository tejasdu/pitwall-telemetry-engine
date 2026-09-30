/**
 * PITWALL TELEMETRY ENGINE - MAIN APPLICATION CONDUCTOR
 * Manages WebSocket transport, state distribution, and HUD updates.
 */

import { initTrackMap } from './track_map.js';
import { initTimingTower } from './timing_tower.js';
import { initCockpit } from './cockpit.js';

export const state = {
    sessionKey: null,
    selectedDrivers: [],
    isPlaying: false,
    playbackSpeed: 1.0,
    latestFrame: null,
};

let isIntentionalDisconnect = false;

export function resetApp() {
    isIntentionalDisconnect = true;
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    if (ws) {
        ws.close();
        ws = null;
    }
    state.latestFrame = null;
    state.selectedDrivers = [];
    state.isPlaying = false;
    document.getElementById('session-title').innerText = 'AWAITING SESSION LINK...';
}

let ws = null;
let reconnectTimer = null;

const frameListeners = [];

/**
 * Registers a module callback to receive each 30 FPS telemetry frame.
 * @param {Function} callback - Function receiving (frame)
 */
export function onFrame(callback) {
    if (typeof callback === 'function') {
        frameListeners.push(callback);
    }
}

// Sends a command action JSON to the backend over the active WebSocket.
export function sendAction(data) {
    if (ws && ws.readyState === WebSocket.OPEN) { ws.send(JSON.stringify(data)); }
    else { console.warn('[Pitwall] Cannot send action: WebSocket not connected', data); }
}

// Connects to the FastAPI WebSocket streaming endpoint.
function connectWebSocket() {
    isIntentionalDisconnect = false;
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/telemetry?session_key=${state.sessionKey}`;

    console.log(`[Pitwall] Connecting to live telemetry: ${wsUrl}`);
    ws = new WebSocket(wsUrl);

    ws.onopen = async () => {
        console.log('[Pitwall] Telemetry WebSocket connected.');
        updateTicker('TELEMETRY STREAM CONNECTED &bull; LIVE FEED ACTIVE');

        // Hide the overlay only after connection is successful
        const overlay = document.getElementById('mission-control-overlay');
        if (overlay) overlay.classList.add('hidden');

        // Sync initial driver selection if already populated
        if (state.selectedDrivers.length > 0) {
            sendAction({ action: 'select_drivers', drivers: state.selectedDrivers });
        }
    };

    ws.onmessage = (event) => {
        try {
            const frame = JSON.parse(event.data);

            // Handle server-side telemetry availability error
            if (frame.error || frame.type === 'error') {
                console.error('[Pitwall] Telemetry error:', frame.message);
                updateTicker(`⚠️ ${frame.message.toUpperCase()}`);

                // Re-open Mission Control so user can select another race
                const overlay = document.getElementById('mission-control-overlay');
                if (overlay) overlay.classList.remove('hidden');

                const launchBtn = document.getElementById('mc-launch-btn');
                if (launchBtn) {
                    launchBtn.innerHTML = 'LAUNCH ENGINE';
                    launchBtn.disabled = false;
                }
                const yearSelect = document.getElementById('mc-year-select');
                const sessionSelect = document.getElementById('mc-session-select');
                if (yearSelect) yearSelect.disabled = false;
                if (sessionSelect) sessionSelect.disabled = false;
                return;
            }

            state.latestFrame = frame;
            state.isPlaying = frame.is_playing;
            state.playbackSpeed = frame.playback_speed;

            // 1. Update Top Header HUD
            updateHeaderHUD(frame);

            // 2. Dispatch frame to all registered UI module subscribers
            for (const listener of frameListeners) {
                listener(frame);
            }
        } catch (err) {
            console.error('[Pitwall] Error parsing frame JSON:', err);
        }
    };

    ws.onclose = (event) => {
        if (isIntentionalDisconnect) {
            console.log('[Pitwall] WebSocket closed intentionally by user.');
            return;
        }

        // If the session has no telemetry recorded (server code 4004), abort reconnect loop
        if (event.code === 4004) {
            console.warn('[Pitwall] Session unavailable (code 4004). Reconnect aborted.');
            updateTicker('SESSION HAS NO TELEMETRY DATA &bull; PLEASE SELECT ANOTHER GRAND PRIX');

            const overlay = document.getElementById('mission-control-overlay');
            if (overlay) overlay.classList.remove('hidden');

            const launchBtn = document.getElementById('mc-launch-btn');
            if (launchBtn) {
                launchBtn.innerHTML = 'LAUNCH ENGINE';
                launchBtn.disabled = false;
            }
            const yearSelect = document.getElementById('mc-year-select');
            const sessionSelect = document.getElementById('mc-session-select');
            if (yearSelect) yearSelect.disabled = false;
            if (sessionSelect) sessionSelect.disabled = false;
            return;
        }

        console.warn('[Pitwall] WebSocket closed. Reconnecting in 2 seconds...');
        updateTicker('STREAM DISCONNECTED &bull; RECONNECTING...');
        reconnectTimer = setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = (err) => {
        console.error('[Pitwall] WebSocket error:', err);
        ws.close();
    };
}

// Updates the Top Header HUD (Clock, Flag status, Race Control Ticker)
function updateHeaderHUD(frame) {

    // Clock
    const clockEl = document.getElementById('race-clock');
    if (clockEl && frame.t_sim_iso) {
        const timeStr = frame.t_sim_iso.split('T')[1]?.substring(0, 8) || '00:00:00';
        clockEl.textContent = timeStr;
    }

    // Flag Badge
    const flagEl = document.getElementById('flag-indicator');
    if (flagEl && frame.flag) {
        const flag = frame.flag.toUpperCase();
        flagEl.textContent = flag === 'SC' ? 'SAFETY CAR' : (flag === 'GREEN' ? 'TRACK CLEAR' : flag);

        // Apply color styling based on flag state
        if (flag === 'GREEN') {
            flagEl.style.color = '#00E599';
            flagEl.style.background = 'rgba(0, 229, 153, 0.15)';
            flagEl.style.borderColor = 'rgba(0, 229, 153, 0.3)';
        } else if (flag === 'YELLOW') {
            flagEl.style.color = '#FFD000';
            flagEl.style.background = 'rgba(255, 208, 0, 0.15)';
            flagEl.style.borderColor = 'rgba(255, 208, 0, 0.4)';
        } else if (flag === 'SC') {
            flagEl.style.color = '#FF8000';
            flagEl.style.background = 'rgba(255, 128, 0, 0.15)';
            flagEl.style.borderColor = 'rgba(255, 128, 0, 0.4)';
        } else if (flag === 'RED') {
            flagEl.style.color = '#FF2A55';
            flagEl.style.background = 'rgba(255, 42, 85, 0.20)';
            flagEl.style.borderColor = 'rgba(255, 42, 85, 0.5)';
        } else if (flag === 'CHEQUERED') {
            flagEl.style.color = '#FFFFFF';
            flagEl.style.background = 'rgba(255, 255, 255, 0.20)';
            flagEl.style.borderColor = 'rgba(255, 255, 255, 0.5)';
        }
    }

    // Race Control Ticker & 5-Message Log
    if (frame.race_control_messages && frame.race_control_messages.length > 0) {
        const latestMsg = frame.race_control_messages[0];
        if (latestMsg && latestMsg.message) {
            updateTicker(latestMsg.message);
        }
        updateRaceControlList(frame.race_control_messages);
    }
}

function updateTicker(messageText) {
    const tickerEl = document.getElementById('ticker-message');
    if (tickerEl) {
        tickerEl.innerHTML = messageText;
    }
}

function updateRaceControlList(messages) {
    const listEl = document.getElementById('rc-messages-list');
    if (!listEl) return;

    listEl.innerHTML = messages.slice(0, 5).map((m, idx) => {
        const timePart = m.date ? m.date.split('T')[1]?.substring(0, 8) : '--:--:--';
        const isLatest = idx === 0;
        const color = m.flag === 'YELLOW' || m.flag === 'DOUBLE YELLOW' ? '#FFD000'
            : m.flag === 'RED' ? '#FF2A55'
                : m.flag === 'CLEAR' ? '#00E599'
                    : 'var(--text-secondary)';

        return `
            <div style="display: flex; gap: 8px; align-items: baseline; opacity: ${isLatest ? 1 : 0.7};">
                <span style="color: var(--text-muted); font-size: 10px;">${timePart}</span>
                <span style="color: ${color}; flex: 1;">${m.message || ''}</span>
            </div>
        `;
    }).join('');
}

function initPlaybackControls() {
    const playBtn = document.getElementById('play-pause-btn');
    const playIcon = document.getElementById('play-icon');
    const scrubber = document.getElementById('scrubber');
    const scrubberPct = document.getElementById('scrubber-pct');
    const speedOpts = document.querySelectorAll('.speed-opt');

    if (playBtn) {
        playBtn.addEventListener('click', () => {
            sendAction({ action: 'toggle_play' });
        });
    }

    if (scrubber) {
        scrubber.addEventListener('input', (e) => {
            if (scrubberPct) scrubberPct.textContent = parseFloat(e.target.value).toFixed(1) + '%';
        });
        scrubber.addEventListener('change', (e) => {
            sendAction({ action: 'seek_percent', percent: parseFloat(e.target.value) / 100.0 });
        });
    }

    speedOpts.forEach(opt => {
        opt.addEventListener('click', (e) => {
            sendAction({ action: 'set_speed', speed: parseFloat(e.target.dataset.speed) });
        });
    });

    onFrame((frame) => {
        if (playIcon) {
            if (frame.is_playing) {
                playIcon.innerHTML = '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>';
            } else {
                playIcon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
            }
        }
        if (scrubber && frame.progress_pct !== undefined) {
            // Only update scrubber value if the user isn't actively dragging it
            if (document.activeElement !== scrubber) {
                scrubber.value = frame.progress_pct;
                if (scrubberPct) scrubberPct.textContent = frame.progress_pct.toFixed(1) + '%';
            }
        }

        speedOpts.forEach(opt => {
            if (parseFloat(opt.dataset.speed) === frame.playback_speed) {
                opt.classList.add('active');
            } else {
                opt.classList.remove('active');
            }
        });
    });
}

function initApp() {
    initTrackMap();
    initTimingTower();
    initCockpit();
    initPlaybackControls();
    connectWebSocket();

    // Wire Race Control Dropdown Toggle
    const rcBtn = document.getElementById('rc-dropdown-btn');
    const rcPanel = document.getElementById('rc-dropdown-panel');
    if (rcBtn && rcPanel) {
        rcBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            rcPanel.classList.toggle('collapsed');
        });

        // Close when clicking anywhere outside
        document.addEventListener('click', (e) => {
            if (!rcPanel.contains(e.target) && e.target !== rcBtn) {
                rcPanel.classList.add('collapsed');
            }
        });
    }

    // Wire Cockpit Drawer Collapse / Expand Toggle
    const drawer = document.getElementById('cockpit-drawer');
    const drawerHandle = document.getElementById('drawer-handle');
    const drawerBtn = document.getElementById('drawer-toggle-btn');
    if (drawer && drawerHandle) {
        drawerHandle.addEventListener('click', () => {
            const isCollapsed = drawer.classList.toggle('collapsed');
            if (drawerBtn) {
                drawerBtn.innerHTML = isCollapsed ? 'EXPAND &uarr;' : 'COLLAPSE &darr;';
            }
        });
    }

    // Wire Change Session Button
    const changeSessionBtn = document.getElementById('change-session-btn');
    if (changeSessionBtn) {
        changeSessionBtn.addEventListener('click', () => {
            const overlay = document.getElementById('mission-control-overlay');
            if (overlay) overlay.classList.remove('hidden');

            const closeBtn = document.getElementById('mc-close-btn');
            if (closeBtn && window.pitwallInitialized) {
                closeBtn.style.display = 'block';
            }

            const launchBtn = document.getElementById('mc-launch-btn');
            const yearSelect = document.getElementById('mc-year-select');
            const sessionSelect = document.getElementById('mc-session-select');
            if (launchBtn) {
                launchBtn.innerHTML = 'LAUNCH ENGINE';
                launchBtn.disabled = false;
            }
            if (yearSelect) yearSelect.disabled = false;
            if (sessionSelect) sessionSelect.disabled = false;
        });
    }
}

async function loadSessionsForYear(year) {
    const sessionSelect = document.getElementById('mc-session-select');
    const launchBtn = document.getElementById('mc-launch-btn');

    sessionSelect.disabled = true;
    sessionSelect.innerHTML = '<option>Fetching sessions...</option>';
    launchBtn.disabled = true;

    try {
        const response = await fetch(`/api/sessions?year=${year}`);
        let sessions = await response.json();

        // Filter out future races that have not started yet
        const now = new Date();
        sessions = sessions.filter(s => new Date(s.date_start) <= now);

        // Sort officially by FIA meeting_key rather than date_start to handle rescheduled races perfectly
        sessions.sort((a, b) => a.meeting_key - b.meeting_key);

        sessionSelect.innerHTML = '';
        if (sessions.length === 0) {
            sessionSelect.innerHTML = '<option>No past sessions found for this year</option>';
            return;
        }

        sessions.forEach((s, index) => {
            const opt = document.createElement('option');
            opt.value = s.session_key;

            // Format time dynamically to the user's local timezone
            const localDate = new Date(s.date_start);
            const timeStr = localDate.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' });

            // Use country_name + circuit_short_name to prevent "United States" or "Spain" duplicates
            opt.textContent = `Round ${index + 1} - ${s.country_name} GP (${s.circuit_short_name}) - ${timeStr}`;
            sessionSelect.appendChild(opt);
        });

        // Automatically pre-select the most recent race (bottom of the chronological list)
        sessionSelect.selectedIndex = sessions.length - 1;

        sessionSelect.disabled = false;
        launchBtn.disabled = false;
    } catch (err) {
        console.error('Failed to load sessions', err);
        sessionSelect.innerHTML = '<option>API Error - Please retry</option>';
    }
}

function initMissionControl() {
    const yearSelect = document.getElementById('mc-year-select');
    const sessionSelect = document.getElementById('mc-session-select');
    const launchBtn = document.getElementById('mc-launch-btn');
    const overlay = document.getElementById('mission-control-overlay');

    if (!overlay) {
        // If the DOM doesn't have the overlay, just fallback to 9472 and init
        state.sessionKey = 9472;
        initApp();
        return;
    }

    const closeBtn = document.getElementById('mc-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            overlay.classList.add('hidden');
        });
    }

    // Populate championship years from 2023 through current season
    const availableYears = [2026, 2025, 2024, 2023];
    yearSelect.innerHTML = '';
    availableYears.forEach(y => {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = `${y} Championship`;
        yearSelect.appendChild(opt);
    });

    // Initial load for default year
    loadSessionsForYear(yearSelect.value);

    // On year change
    yearSelect.addEventListener('change', (e) => {
        loadSessionsForYear(e.target.value);
    });

    // On Launch
    launchBtn.addEventListener('click', async () => {
        state.sessionKey = sessionSelect.value;
        const selectedOpt = sessionSelect.options[sessionSelect.selectedIndex];

        // Update header title dynamically
        document.getElementById('session-title').innerText = selectedOpt.textContent.toUpperCase();

        launchBtn.innerHTML = 'SYNCING TELEMETRY (THIS MAY TAKE 15 SECONDS)...';
        launchBtn.disabled = true;
        yearSelect.disabled = true;
        sessionSelect.disabled = true;

        if (!window.pitwallInitialized) {
            initApp();
            window.pitwallInitialized = true;
        } else {
            resetApp();

            // Hot-reload submodules without reloading the page
            const trackMap = await import('./track_map.js');
            trackMap.resetTrackMap();

            const timingTower = await import('./timing_tower.js');
            // Do not await this, it blocks the UI if OpenF1 API is slow!
            timingTower.resetTimingTower();

            connectWebSocket();
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMissionControl);
} else {
    initMissionControl();
}
