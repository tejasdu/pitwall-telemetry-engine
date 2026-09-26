/**
 * PITWALL TELEMETRY ENGINE - TIMING TOWER (timing_tower.js)
 * High-performance 20-driver live leaderboard with interval deltas,
 * tire compound badges, team livery pills, and interactive duel selection.
 */

import { onFrame, sendAction, state } from './app.js';

let towerContainer = null;
let driverMetadata = new Map(); // driver_number -> { acronym, teamColor, fullName, compound }
const rowElements = new Map();  // driver_number -> DOM element
let initialLoaded = false;

// Tire compound map (e.g. "SOFT" -> "S", "MEDIUM" -> "M", "HARD" -> "H")
function formatCompound(compoundName) {
    if (!compoundName) return 'S';
    const c = String(compoundName).toUpperCase();
    if (c.startsWith('SOFT')) return 'S';
    if (c.startsWith('MED')) return 'M';
    if (c.startsWith('HARD')) return 'H';
    if (c.startsWith('INTER')) return 'I';
    if (c.startsWith('WET')) return 'W';
    return c.charAt(0);
}

/**
 * Loads static drivers registry and initial tire stints for the session.
 */
async function loadMetadata() {
    try {
        const [driversRes, stintsRes] = await Promise.all([
            fetch(`/api/drivers?session_key=${state.sessionKey}`),
            fetch(`/api/stints?session_key=${state.sessionKey}`)
        ]);

        const driversData = await driversRes.json();
        const stintsData = await stintsRes.json();

        // Map initial stint compound per driver (stint 1)
        const stintsMap = new Map();
        if (Array.isArray(stintsData)) {
            for (const s of stintsData) {
                if (s.stint_number === 1 && !stintsMap.has(s.driver_number)) {
                    stintsMap.set(s.driver_number, formatCompound(s.compound));
                }
            }
        }

        // Populate driverMetadata map
        for (const [key, d] of Object.entries(driversData)) {
            const dNum = Number(key);
            driverMetadata.set(dNum, {
                driverNumber: dNum,
                acronym: d.name_acronym || `#${dNum}`,
                teamColor: d.team_colour ? `#${d.team_colour}` : '#FFFFFF',
                fullName: d.full_name || d.name_acronym,
                teamName: d.team_name || 'Formula 1',
                compound: stintsMap.get(dNum) || 'S',
            });
        }

        console.log(`[Pitwall] Timing tower metadata loaded for ${driverMetadata.size} drivers.`);
    } catch (err) {
        console.error('[Pitwall] Failed to load timing tower metadata:', err);
    }
}

/**
 * Creates a DOM element for a driver row if it doesn't already exist.
 */
function getOrCreateRow(driverNumber, initialMeta) {
    let row = rowElements.get(driverNumber);
    if (row) return row;

    row = document.createElement('div');
    row.className = 'tower-row';
    row.setAttribute('data-driver', String(driverNumber));

    const color = initialMeta.teamColor || '#FFFFFF';

    row.innerHTML = `
        <span class="pos-badge" data-slot="pos">--</span>
        <span class="team-pill" data-slot="pill" style="background: ${color};"></span>
        <span class="driver-tag" data-slot="tag">${initialMeta.acronym || '#' + driverNumber}</span>
        <span class="tire-badge ${initialMeta.compound || 'S'}" data-slot="tire">${initialMeta.compound || 'S'}</span>
        <span class="gap-delta" data-slot="gap">--</span>
        <span class="battle-indicator" data-slot="battle" style="display: none; margin-left: 6px; font-size: 11px; cursor: pointer;" title="Active Battle &bull; Click to Compare">⚔️</span>
    `;

    // Row click handler: selects this driver for head-to-head cockpit comparison
    row.addEventListener('click', (e) => {
        handleDriverSelect(driverNumber, e);
    });

    rowElements.set(driverNumber, row);
    return row;
}

/**
 * Handles user clicking a driver row to toggle selection for cockpit telemetry comparison.
 */
function handleDriverSelect(driverNumber, e) {
    e.stopPropagation();

    // Toggle logic: keep max 2 drivers (Driver 1 and Driver 2 for comparison)
    let selected = [...state.selectedDrivers];

    if (selected.includes(driverNumber)) {
        // If clicking an already selected driver, don't deselect if it's the only one left
        if (selected.length > 1) {
            selected = selected.filter(num => num !== driverNumber);
        }
    } else {
        if (selected.length >= 2) {
            // Replace the second driver
            selected = [selected[0], driverNumber];
        } else {
            selected.push(driverNumber);
        }
    }

    state.selectedDrivers = selected;

    // Send selection update over WebSocket to backend
    sendAction({ action: 'select_drivers', drivers: selected });

    // Update active duel label in cockpit header
    updateDuelLabel();

    // Refresh selected classes on rows
    updateSelectedRowClasses();
}

/**
 * Updates the text description in the Cockpit drawer header.
 */
function updateDuelLabel() {
    const label = document.getElementById('active-duel-label');
    if (!label) return;

    if (state.selectedDrivers.length === 2) {
        const d1 = driverMetadata.get(state.selectedDrivers[0])?.acronym || `#${state.selectedDrivers[0]}`;
        const d2 = driverMetadata.get(state.selectedDrivers[1])?.acronym || `#${state.selectedDrivers[1]}`;
        label.textContent = `COMPARING ${d1} VS ${d2}`;
    } else if (state.selectedDrivers.length === 1) {
        const d1 = driverMetadata.get(state.selectedDrivers[0])?.acronym || `#${state.selectedDrivers[0]}`;
        label.textContent = `TELEMETRY FOR ${d1} (CLICK ANOTHER TO DUEL)`;
    }
}

/**
 * Synchronizes the visual `.selected` CSS class across all rows.
 */
function updateSelectedRowClasses() {
    for (const [dNum, row] of rowElements.entries()) {
        if (state.selectedDrivers.includes(dNum)) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    }
}

/**
 * Handles incoming 30 FPS telemetry frames and updates the Timing Tower.
 */
function handleTowerFrame(frame) {
    if (!towerContainer) return;

    const positions = frame.positions || [];
    const intervals = frame.intervals || {};
    const battles = frame.battles || [];

    if (positions.length === 0) return;

    // Build sortable standings array
    const standings = [];

    for (const pos of positions) {
        const dNum = pos.driver_number;
        let meta = driverMetadata.get(dNum);

        if (!meta) {
            meta = {
                driverNumber: dNum,
                acronym: pos.acronym || `#${dNum}`,
                teamColor: pos.team_color ? `#${pos.team_color}` : '#FFFFFF',
                fullName: pos.acronym,
                teamName: '',
                compound: 'S',
            };
            driverMetadata.set(dNum, meta);
        } else if (pos.team_color) {
            meta.teamColor = `#${pos.team_color}`;
        }

        const intData = intervals[String(dNum)] || intervals[dNum] || {};
        const gapVal = intData.gap_to_leader !== undefined ? intData.gap_to_leader : null;
        const intervalVal = intData.interval !== undefined ? intData.interval : null;

        standings.push({
            driverNumber: dNum,
            meta,
            gapToLeader: (typeof gapVal === 'number') ? gapVal : 999.0,
            interval: (typeof intervalVal === 'number') ? intervalVal : null,
        });
    }

    // Sort by gap_to_leader ascending (P1 has gap = 0.0, P2 has gap = 1.2, etc.)
    standings.sort((a, b) => a.gapToLeader - b.gapToLeader);

    // Build quick lookup for active battles keyed by attacker
    const battleMap = new Map();
    for (const b of battles) {
        battleMap.set(b.attacker, b);
    }

    // Clear initial loading message on first frame
    if (!initialLoaded) {
        towerContainer.innerHTML = '';
        initialLoaded = true;
    }

    // Update or append rows in sorted position order
    const fragment = document.createDocumentFragment();

    for (let i = 0; i < standings.length; i++) {
        const item = standings[i];
        const pos = i + 1;
        const row = getOrCreateRow(item.driverNumber, item.meta);

        // Slot 1: Position
        const posEl = row.querySelector('[data-slot="pos"]');
        if (posEl && posEl.textContent !== String(pos)) {
            posEl.textContent = pos;
        }

        // Slot 2: Team Pill Color
        const pillEl = row.querySelector('[data-slot="pill"]');
        if (pillEl && item.meta.teamColor) {
            pillEl.style.background = item.meta.teamColor;
        }

        // Slot 3: Gap / Interval Text
        const gapEl = row.querySelector('[data-slot="gap"]');
        if (gapEl) {
            if (pos === 1) {
                gapEl.textContent = 'LEADER';
                gapEl.style.color = 'var(--text-muted)';
            } else if (item.gapToLeader < 900) {
                // Show gap to leader, e.g. "+1.428s"
                gapEl.textContent = `+${item.gapToLeader.toFixed(3)}s`;
                gapEl.style.color = 'var(--text-secondary)';
            } else {
                gapEl.textContent = '--';
                gapEl.style.color = 'var(--text-muted)';
            }
        }

        // Slot 4: Battle ⚔️ Indicator
        const battleEl = row.querySelector('[data-slot="battle"]');
        const activeBattle = battleMap.get(item.driverNumber);
        if (battleEl) {
            if (activeBattle && activeBattle.gap <= 1.000) {
                battleEl.style.display = 'inline';
                battleEl.title = `Battling ahead: ${activeBattle.gap.toFixed(3)}s gap`;
            } else {
                battleEl.style.display = 'none';
            }
        }

        fragment.appendChild(row);
    }

    // Re-append fragment to preserve sorted DOM order
    towerContainer.appendChild(fragment);

    // Keep selected row classes synced
    updateSelectedRowClasses();
}

/**
 * Initializes the Timing Tower module.
 */
export async function initTimingTower() {
    towerContainer = document.getElementById('tower-rows');
    if (!towerContainer) return;

    await loadMetadata();
    updateDuelLabel();

    // Register 30 FPS frame callback
    onFrame(handleTowerFrame);
}
