/**
 * PITWALL TELEMETRY ENGINE - 2D CIRCUIT TRACK MAP (track_map.js)
 * High-performance HTML5 Canvas renderer with 60-120 FPS sub-frame gliding
 */

import { onFrame, state } from './app.js';

// 
let canvas = null;
let ctx = null;

// Circuit geometry points [{x, y}, ...]
let trackPoints = [];
let bounds = { minX: 0, maxX: 1, minY: 0, maxY: 1, scale: 1, offsetX: 0, offsetY: 0 };
let cachedTrackPath = null;

// driver_number : { currentX, currentY, targetX, targetY, acronym, color }
const driverPositions = new Map();

// Active battles from latest frame
let activeBattles = [];
let activeCautionSectors = [];

// Helper: Converts OpenF1 coordinates to Canvas coordinates. Preserves ratio and Y inversion and coordinate normalization
function toCanvasX(x) {
  return bounds.offsetX + (x - bounds.minX) * bounds.scale;
}
function toCanvasY(y) {
  return bounds.offsetY - (y - bounds.minY) * bounds.scale;
}

// Helper: Updates bounding box and scaling factors to fit circuit on HTML canvas with padding for a Mac Retina display.
function updateBounds() {
  if (!canvas || trackPoints.length === 0) return;

  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio;
  canvas.height = rect.height * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

  const w = rect.width;
  const h = rect.height;
  const padding = 48; // margin around the circuit

  const trackWidth = Math.max(1, bounds.maxX - bounds.minX);
  const trackHeight = Math.max(1, bounds.maxY - bounds.minY);

  const scaleX = (w - padding * 2) / trackWidth;
  const scaleY = (h - padding * 2) / trackHeight;
  bounds.scale = Math.min(scaleX, scaleY);

  // Center track within canvas
  const renderedW = trackWidth * bounds.scale;
  const renderedH = trackHeight * bounds.scale;
  bounds.offsetX = (w - renderedW) / 2;
  bounds.offsetY = h - (h - renderedH) / 2;

  // Pre-build and cache the Path2D spline once so renderLoop doesn't loop 300 times at 60 FPS
  cachedTrackPath = new Path2D();
  for (let i = 0; i < trackPoints.length; i++) {
    const cx = toCanvasX(trackPoints[i].x);
    const cy = toCanvasY(trackPoints[i].y);
    if (i === 0) cachedTrackPath.moveTo(cx, cy);
    else cachedTrackPath.lineTo(cx, cy);
  }
  cachedTrackPath.closePath();
}

// Helper: Fetches circuit geometry once from backend REST API
async function loadTrackGeometry() {
  try {
    const res = await fetch(`/api/track-geometry?session_key=${state.sessionKey}`);
    const data = await res.json();

    const points = data.points || data.geometry || (Array.isArray(data) ? data : []);

    if (Array.isArray(points) && points.length > 0) {
      trackPoints = points;
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

      for (const pt of points) {
        if (pt.x < minX) minX = pt.x;
        if (pt.x > maxX) maxX = pt.x;
        if (pt.y < minY) minY = pt.y;
        if (pt.y > maxY) maxY = pt.y;
      }

      bounds.minX = minX;
      bounds.maxX = maxX;
      bounds.minY = minY;
      bounds.maxY = maxY;

      updateBounds();
      console.log(`[Pitwall] Circuit geometry loaded: ${points.length} points.`);
    }
  } catch (err) {
    console.error('[Pitwall] Failed to load track geometry:', err);
  }
}

// Helper: Accepts a telemetry frame and updates driver positions
function handleFrame(frame) {
  activeCautionSectors = frame.caution_sectors || [];
  activeBattles = frame.battles || [];

  if (!frame.positions) return;

  for (const pos of frame.positions) {
    const dNum = pos.driver_number;
    const existing = driverPositions.get(dNum);

    if (existing) {
      existing.targetX = pos.x;
      existing.targetY = pos.y;
      existing.acronym = pos.acronym || existing.acronym;
      existing.color = pos.team_color ? `#${pos.team_color}` : existing.color;
    } else {
      // First frame for this driver: initialize both current and target
      driverPositions.set(dNum, {
        currentX: pos.x,
        currentY: pos.y,
        targetX: pos.x,
        targetY: pos.y,
        acronym: pos.acronym || `#${dNum}`,
        color: pos.team_color ? `#${pos.team_color}` : '#FFFFFF',
      });
    }
  }
}

// Helper: 60-120 FPS Animation Loop using requestAnimationFrame
function renderLoop() {
  if (ctx && canvas) {
    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;

    ctx.clearRect(0, 0, w, h);

    // 1. Draw Circuit Ribbon using cached Path2D (Option A: Multi-layer broadcast asphalt)
    if (cachedTrackPath) {
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';

      // Layer 1: Outer Track Bed & Runoff Margin (16px)
      ctx.lineWidth = 16;
      ctx.strokeStyle = 'rgba(32, 44, 64, 0.65)';
      ctx.stroke(cachedTrackPath);

      // Layer 2: Main Asphalt Driving Surface (12px)
      ctx.lineWidth = 11;
      ctx.strokeStyle = '#141C28';
      ctx.stroke(cachedTrackPath);

      // Layer 3: Rubbered-in Racing Groove (6px)
      ctx.lineWidth = 6;
      ctx.strokeStyle = '#0D131C';
      ctx.stroke(cachedTrackPath);

      // Layer 4: Crisp Centerline Guide (1.5px)
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
      ctx.stroke(cachedTrackPath);
    }

    // 2. Draw Battle Tethers (glowing brackets between dueling cars)
    for (const b of activeBattles) {
      if (b.gap <= 0.500) {
        // Find attacker position
        const attacker = driverPositions.get(b.attacker);
        if (attacker) {
          const ax = toCanvasX(attacker.currentX);
          const ay = toCanvasY(attacker.currentY);

          // Glowing pulse ring on attacker
          ctx.beginPath();
          ctx.arc(ax, ay, 12, 0, Math.PI * 2);
          ctx.strokeStyle = 'rgba(155, 81, 224, 0.6)';
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }
    }

    // 3. Draw 20 Car Dots with Smooth Sub-Frame Lerp Gliding
    const lerpAlpha = 0.22; // Interpolation smoothing factor

    for (const [dNum, car] of driverPositions.entries()) {
      // Lerp current towards target
      car.currentX += (car.targetX - car.currentX) * lerpAlpha;
      car.currentY += (car.targetY - car.currentY) * lerpAlpha;

      const cx = toCanvasX(car.currentX);
      const cy = toCanvasY(car.currentY);

      // Check if driver is selected in cockpit drawer
      const isSelected = state.selectedDrivers.includes(dNum);

      // Outer Halo for selected cars
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(cx, cy, 10, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
        ctx.fill();
        ctx.strokeStyle = '#FFFFFF';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Car Livery Dot
      ctx.beginPath();
      ctx.arc(cx, cy, isSelected ? 6.5 : 5.5, 0, Math.PI * 2);
      ctx.fillStyle = car.color;
      ctx.shadowColor = car.color;
      ctx.shadowBlur = isSelected ? 12 : 6;
      ctx.fill();
      ctx.shadowBlur = 0; // Reset shadow

      // White inner core
      ctx.beginPath();
      ctx.arc(cx, cy, 2, 0, Math.PI * 2);
      ctx.fillStyle = '#FFFFFF';
      ctx.fill();

      // Driver Acronym Tag (e.g. "VER", "SAI")
      ctx.font = isSelected ? 'bold 11px Inter, sans-serif' : '10px Inter, sans-serif';
      ctx.fillStyle = isSelected ? '#FFFFFF' : 'rgba(240, 244, 248, 0.8)';
      ctx.fillText(car.acronym, cx + 8, cy + 3);
    }
  }

  requestAnimationFrame(renderLoop);
}

// Initialize the Track Map module
export function initTrackMap() {
  canvas = document.getElementById('track-canvas');
  if (!canvas) return;

  ctx = canvas.getContext('2d');

  window.addEventListener('resize', updateBounds);
  loadTrackGeometry();

  // Register frame consumer
  onFrame(handleFrame);

  // Start 60-120 FPS animation loop
  requestAnimationFrame(renderLoop);
}

