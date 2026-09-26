/**
 * PITWALL TELEMETRY ENGINE - MAIN APPLICATION CONDUCTOR
 * Manages WebSocket transport, state distribution, and HUD updates.
 */

import { initTrackMap } from './track_map.js';
import { initTimingTower } from './timing_tower.js';

export const state = {
    sessionKey: 9472,
    selectedDrivers: [1, 55],
    isPlaying: false,
    playbackSpeed: 1.0,
    latestFrame: null,
};

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
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/telemetry?session_key=${state.sessionKey}`;

    console.log(`[Pitwall] Connecting to live telemetry: ${wsUrl}`);
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('[Pitwall] Telemetry WebSocket connected.');
        updateTicker('TELEMETRY STREAM CONNECTED &bull; LIVE FEED ACTIVE');
        // Sync initial driver selection
        sendAction({ action: 'select_drivers', drivers: state.selectedDrivers });
    };

    ws.onmessage = (event) => {
        try {
            const frame = JSON.parse(event.data);
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

    ws.onclose = () => {
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

function initApp() {
    initTrackMap();
    initTimingTower();
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
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}
