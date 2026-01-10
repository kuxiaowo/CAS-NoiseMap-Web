const canvas = document.getElementById('viz');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');

const ENDPOINT = 'http://127.0.0.1:9770/post';
const POLL_INTERVAL_MS = 2000;
const INFLUENCE_RADIUS = window.CONFIG?.influenceRadius ?? 100; // custom units
const POINT_RADIUS = window.CONFIG?.pointRadius ?? 4; // pixels
const SCALE = window.CONFIG?.scale ?? 1; // 1 unit = 1 px
const MAP_IMAGE_SRC = window.CONFIG?.mapImage ?? 'map.png';
const MAP_ANCHOR = window.CONFIG?.mapAnchor ?? { x: 662, y: 668 };
const MAP_SCALE = Number(window.CONFIG?.mapScale ?? 1) || 1; // only affects background size
const INFLUENCE_OPACITY = Number(window.CONFIG?.influenceOpacity ?? 1) || 1;
const CELL_SIZE = 4; // pixels, smaller = higher quality, slower
const OUTSIDE_COLOR = '#dcdcdc';
const AXIS_COLOR = '#d6d6d6';

let lastPoints = [];
let lastUpdated = null;
let mapLoaded = false;
const mapImage = new Image();
mapImage.onload = () => {
  mapLoaded = true;
  render(lastPoints);
};
mapImage.src = MAP_IMAGE_SRC;

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const w = window.innerWidth;
  const h = window.innerHeight;
  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  canvas.style.width = w + 'px';
  canvas.style.height = h + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  render(lastPoints);
}

function normalizePoints(points) {
  return points
    .filter((p) => Number.isFinite(Number(p.x)) && Number.isFinite(Number(p.y)))
    .map((p) => {
      const rgb = Array.isArray(p.rgb) ? p.rgb.map((v) => Number(v)) : [];
      return {
        id: p.id,
        x: Number(p.x),
        y: Number(p.y),
        rgb: rgb.length === 3 ? rgb : [120, 120, 120],
      };
    });
}

function render(points) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const centerX = width / 2;
  const centerY = height / 2;

  ctx.clearRect(0, 0, width, height);

  // Base color for areas without influence
  ctx.fillStyle = OUTSIDE_COLOR;
  ctx.fillRect(0, 0, width, height);

  if (mapLoaded) {
    const anchorX = Number(MAP_ANCHOR?.x) || 0;
    const anchorY = Number(MAP_ANCHOR?.y) || 0;
    const drawX = centerX - anchorX * SCALE * MAP_SCALE;
    const drawY = centerY - anchorY * SCALE * MAP_SCALE;
    ctx.drawImage(
      mapImage,
      drawX,
      drawY,
      mapImage.width * SCALE * MAP_SCALE,
      mapImage.height * SCALE * MAP_SCALE
    );
  }

  // Influence rasterization (simple grid fill)
  const influenceAlpha = Math.min(Math.max(INFLUENCE_OPACITY, 0), 1);
  const originalAlpha = ctx.globalAlpha;
  for (let py = 0; py < height; py += CELL_SIZE) {
    for (let px = 0; px < width; px += CELL_SIZE) {
      const worldX = (px + CELL_SIZE / 2 - centerX) / SCALE;
      const worldY = (centerY - (py + CELL_SIZE / 2)) / SCALE;

      let sumWeight = 0;
      let mixR = 0;
      let mixG = 0;
      let mixB = 0;

      for (const p of points) {
        const dx = worldX - p.x;
        const dy = worldY - p.y;
        const dist = Math.hypot(dx, dy);
        if (dist <= INFLUENCE_RADIUS) {
          const weight = 1 - dist / INFLUENCE_RADIUS;
          sumWeight += weight;
          mixR += p.rgb[0] * weight;
          mixG += p.rgb[1] * weight;
          mixB += p.rgb[2] * weight;
        }
      }

      if (sumWeight > 0) {
        const r = Math.round(mixR / sumWeight);
        const g = Math.round(mixG / sumWeight);
        const b = Math.round(mixB / sumWeight);
        ctx.globalAlpha = influenceAlpha;
        ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
        ctx.fillRect(px, py, CELL_SIZE, CELL_SIZE);
      }
    }
  }
  ctx.globalAlpha = originalAlpha;

  // Axes
  ctx.strokeStyle = AXIS_COLOR;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, centerY);
  ctx.lineTo(width, centerY);
  ctx.moveTo(centerX, 0);
  ctx.lineTo(centerX, height);
  ctx.stroke();

  // Points on top
  for (const p of points) {
    const screenX = centerX + p.x * SCALE;
    const screenY = centerY - p.y * SCALE;
    const color = `rgb(${p.rgb[0]}, ${p.rgb[1]}, ${p.rgb[2]})`;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(screenX, screenY, POINT_RADIUS, 0, Math.PI * 2);
    ctx.stroke();
  }
}

async function fetchData() {
  try {
    const res = await fetch(ENDPOINT, { method: 'POST' });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    const json = await res.json();
    if (!Array.isArray(json)) {
      throw new Error('Response is not an array');
    }
    lastPoints = normalizePoints(json);
    lastUpdated = new Date();
    render(lastPoints);
    statusEl.textContent = `Updated: ${lastUpdated.toLocaleTimeString()} | Points: ${lastPoints.length}`;
  } catch (err) {
    statusEl.textContent = `Fetch failed: ${err.message}`;
  }
}

window.addEventListener('resize', resizeCanvas);
resizeCanvas();
fetchData();
setInterval(fetchData, POLL_INTERVAL_MS);
