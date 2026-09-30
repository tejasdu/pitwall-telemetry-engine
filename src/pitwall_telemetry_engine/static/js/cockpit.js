import { onFrame, state } from './app.js';
import { driverMetadata } from './timing_tower.js';

// Helpers to get DOM elements for a specific cockpit slot (1 or 2)
function getCockpitElements(idx) {
    return {
        card: document.getElementById(`cockpit-driver-${idx}`),
        pill: document.getElementById(`d${idx}-pill`),
        headshot: document.getElementById(`d${idx}-headshot`),
        tag: document.getElementById(`d${idx}-tag`),
        num: document.getElementById(`d${idx}-num`),
        drs: document.getElementById(`d${idx}-drs-badge`),
        shiftLights: document.getElementById(`d${idx}-shift-lights`),
        gear: document.getElementById(`d${idx}-gear`),
        speed: document.getElementById(`d${idx}-speed`),
        throttleFill: document.getElementById(`d${idx}-throttle-fill`),
        throttleVal: document.getElementById(`d${idx}-throttle-val`),
        brakeFill: document.getElementById(`d${idx}-brake-fill`),
        brakeVal: document.getElementById(`d${idx}-brake-val`),
    };
}

let ui1, ui2;

function initShiftLights(ui) {
    if (!ui.shiftLights) return;
    ui.shiftLights.innerHTML = '';
    // 15 LEDs: 5 green, 5 red, 5 blue
    for (let i = 0; i < 15; i++) {
        const led = document.createElement('div');
        led.className = 'shift-led';
        if (i < 5) led.classList.add('green');
        else if (i < 10) led.classList.add('red');
        else led.classList.add('blue');
        ui.shiftLights.appendChild(led);
    }
}

function updateShiftLights(ui, rpm) {
    if (!ui.shiftLights) return;
    // Estimated max RPM for F1 cars where lights activate (10500 - 12000 RPM)
    const startRpm = 10500;
    const maxRpm = 11800;

    let activeCount = 0;
    if (rpm > startRpm) {
        const pct = Math.min(1.0, (rpm - startRpm) / (maxRpm - startRpm));
        activeCount = Math.floor(pct * 15);
    }

    const leds = ui.shiftLights.children;
    for (let i = 0; i < 15; i++) {
        if (i < activeCount) {
            leds[i].classList.add('active');
        } else {
            leds[i].classList.remove('active');
        }
    }
}

function updateCockpitUI(ui, driverNumber, telData) {
    if (!ui.card) return;

    if (!driverNumber || !telData) {
        ui.card.style.display = 'none';
        return;
    }
    ui.card.style.display = 'flex';

    // Update Identity from Timing Tower metadata
    const meta = driverMetadata.get(driverNumber);
    if (meta) {
        ui.pill.style.background = meta.teamColor;
        ui.tag.textContent = meta.acronym;
        ui.num.textContent = `#${driverNumber}`;
        if (ui.headshot) {
            if (meta.headshotUrl) {
                // Strip the .transform segment from OpenF1 URLs to fetch the original high-resolution image
                let url = meta.headshotUrl.split('.transform')[0];
                ui.headshot.src = url;
                ui.headshot.style.display = 'block';
            } else {
                ui.headshot.style.display = 'none';
            }
        }
    }

    // Gear
    let gearStr = telData.gear;
    if (gearStr === 0) gearStr = 'N';
    else if (gearStr === -1) gearStr = 'R';
    ui.gear.textContent = gearStr;

    // Speed
    ui.speed.textContent = Math.round(telData.speed || 0);

    // Pedals
    const thr = Math.min(100, Math.max(0, telData.throttle || 0));
    const brk = Math.min(100, Math.max(0, telData.brake || 0));
    ui.throttleFill.style.width = `${thr}%`;
    ui.throttleVal.textContent = `${Math.round(thr)}%`;
    ui.brakeFill.style.width = `${brk}%`;
    ui.brakeVal.textContent = `${Math.round(brk)}%`;

    // DRS Status (values 10-14 usually indicate DRS active)
    if (telData.drs >= 10 && telData.drs <= 14) {
        ui.drs.textContent = 'DRS OPEN';
        ui.drs.style.background = 'rgba(0, 229, 153, 0.2)';
        ui.drs.style.color = '#00E599';
    } else {
        ui.drs.textContent = 'DRS OFF';
        ui.drs.style.background = 'rgba(155, 81, 224, 0.2)';
        ui.drs.style.color = '#C084FC';
    }

    // RPM Shift Lights
    updateShiftLights(ui, telData.rpm || 0);
}

export function initCockpit() {
    ui1 = getCockpitElements(1);
    ui2 = getCockpitElements(2);

    initShiftLights(ui1);
    initShiftLights(ui2);

    onFrame((frame) => {
        const drivers = state.selectedDrivers || [];
        const tel = frame.telemetry || {};

        // Update Driver 1
        updateCockpitUI(ui1, drivers[0], tel[drivers[0]]);

        // Update Driver 2
        updateCockpitUI(ui2, drivers[1], tel[drivers[1]]);
    });
}
