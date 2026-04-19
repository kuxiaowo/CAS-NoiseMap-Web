const canvas = document.getElementById('viz');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const subStatusEl = document.getElementById('subStatus');
const legendEl = document.getElementById('legend');
const liveDotEl = document.getElementById('liveDot');
const registeredCountEl = document.getElementById('registeredCount');
const renderedCountEl = document.getElementById('renderedCount');
const onlineCountEl = document.getElementById('onlineCount');
const updatedTimeEl = document.getElementById('updatedTime');
const sensorListEl = document.getElementById('sensorList');
const sensorCardHeaderEl = document.getElementById('sensorCardHeader');
const sensorCountEl = document.getElementById('sensorCount');
let sensorExpanded = false;

if (sensorCardHeaderEl) {
  const toggle = () => {
    sensorExpanded = !sensorExpanded;
    if (sensorExpanded) {
      sensorListEl.classList.add('expanded');
      sensorListEl.classList.remove('collapsed');
      sensorListEl.setAttribute('aria-hidden', 'false');
    } else {
      sensorListEl.classList.remove('expanded');
      sensorListEl.classList.add('collapsed');
      sensorListEl.setAttribute('aria-hidden', 'true');
    }
  };
  sensorCardHeaderEl.addEventListener('click', toggle);
  sensorCardHeaderEl.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ') {
      ev.preventDefault();
      toggle();
    }
  });
}

const ENDPOINT = window.CONFIG?.endpoint;
const STATUS_ENDPOINT = window.CONFIG?.statusEndpoint;
const DEVICES_ENDPOINT = window.CONFIG?.devicesEndpoint;
const POLL_INTERVAL_MS = Number(window.CONFIG?.pollIntervalMs ?? 2000);
const INFLUENCE_RADIUS = Number(window.CONFIG?.influenceRadius ?? 90);
const POINT_RADIUS = Number(window.CONFIG?.pointRadius ?? 6);
const SCALE = Number(window.CONFIG?.scale ?? 1);
const MAP_IMAGE_SRC = window.CONFIG?.mapImage ?? 'map.png';
const MAP_ANCHOR = window.CONFIG?.mapAnchor ?? { x: 0, y: 0 };
const MAP_SCALE = Number(window.CONFIG?.mapScale ?? 1);
const INFLUENCE_OPACITY = Number(window.CONFIG?.influenceOpacity ?? 0.25);
const OUTSIDE_COLOR = window.CONFIG?.outsideColor ?? '#dcdcdc';
const AXIS_COLOR = window.CONFIG?.axisColor ?? 'rgba(140, 154, 179, 0.45)';
const SHOW_LABELS = Boolean(window.CONFIG?.showLabels ?? true);
const GLOW_INTENSITY = Number(window.CONFIG?.glowIntensity ?? 1);
const GRID_ENABLED = Boolean(window.CONFIG?.gridEnabled ?? false);
const LEGEND_ITEMS = Array.isArray(window.CONFIG?.legend) ? window.CONFIG.legend : [];

let lastPoints = [];
let lastUpdated = null;
let mapLoaded = false;

const mapImage = new Image();
mapImage.onload = () => {
  mapLoaded = true;
  render(lastPoints);
};
mapImage.src = MAP_IMAGE_SRC;

function createLayerCanvas() {
  const layer = document.createElement('canvas');
  return layer;
}

const influenceLayer = createLayerCanvas();
const influenceCtx = influenceLayer.getContext('2d');

function resizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const width = window.innerWidth;
  const height = window.innerHeight;

  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  influenceLayer.width = Math.floor(width * dpr);
  influenceLayer.height = Math.floor(height * dpr);
  influenceCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

  render(lastPoints);
}

function normalizePoints(points) {
  if (!Array.isArray(points)) {
    return [];
  }

  return points
    .filter((point) => Number.isFinite(Number(point.x)) && Number.isFinite(Number(point.y)))
    .map((point) => {
      const rgb = Array.isArray(point.rgb) ? point.rgb.map((value) => Number(value)) : [120, 120, 120];
      return {
        id: Number(point.id),
        label: point.label || `Sensor ${point.id}`,
        x: Number(point.x),
        y: Number(point.y),
        noise: Number(point.noise ?? 0),
        rgb: rgb.length === 3 ? rgb : [120, 120, 120],
        level: String(point.level || 'unknown'),
        online: Boolean(point.online),
      };
    });
}

function rgbString(rgb, alpha = 1) {
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}

function drawBackground(width, height, centerX, centerY) {
  ctx.fillStyle = OUTSIDE_COLOR;
  ctx.fillRect(0, 0, width, height);

  if (!mapLoaded) {
    return;
  }

  const anchorX = Number(MAP_ANCHOR?.x) || 0;
  const anchorY = Number(MAP_ANCHOR?.y) || 0;
  const drawX = centerX - anchorX * SCALE * MAP_SCALE;
  const drawY = centerY - anchorY * SCALE * MAP_SCALE;

  ctx.save();
  ctx.globalAlpha = 0.95;
  ctx.drawImage(
    mapImage,
    drawX,
    drawY,
    mapImage.width * SCALE * MAP_SCALE,
    mapImage.height * SCALE * MAP_SCALE,
  );
  ctx.restore();
}

function drawGrid(width, height, centerX, centerY) {
  if (!GRID_ENABLED) {
    return;
  }

  ctx.save();
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;

  const gap = 80;
  for (let x = centerX % gap; x < width; x += gap) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
    ctx.stroke();
  }

  for (let y = centerY % gap; y < height; y += gap) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  ctx.restore();
}

function drawInfluence(points, centerX, centerY, width, height) {
  influenceCtx.clearRect(0, 0, width, height);
  influenceCtx.save();
  influenceCtx.globalCompositeOperation = 'lighter';

  for (const point of points) {
    const screenX = centerX + point.x * SCALE;
    const screenY = centerY - point.y * SCALE;
    const radius = INFLUENCE_RADIUS * SCALE;

    const gradient = influenceCtx.createRadialGradient(screenX, screenY, 0, screenX, screenY, radius);
    gradient.addColorStop(0, rgbString(point.rgb, INFLUENCE_OPACITY * GLOW_INTENSITY));
    gradient.addColorStop(0.35, rgbString(point.rgb, INFLUENCE_OPACITY * 0.58 * GLOW_INTENSITY));
    gradient.addColorStop(0.7, rgbString(point.rgb, INFLUENCE_OPACITY * 0.18 * GLOW_INTENSITY));
    gradient.addColorStop(1, rgbString(point.rgb, 0));

    influenceCtx.fillStyle = gradient;
    influenceCtx.beginPath();
    influenceCtx.arc(screenX, screenY, radius, 0, Math.PI * 2);
    influenceCtx.fill();
  }

  influenceCtx.restore();
  ctx.drawImage(influenceLayer, 0, 0, width, height);
}

function drawAxes(width, height, centerX, centerY) {
  ctx.save();
  ctx.strokeStyle = AXIS_COLOR;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, centerY);
  ctx.lineTo(width, centerY);
  ctx.moveTo(centerX, 0);
  ctx.lineTo(centerX, height);
  ctx.stroke();
  ctx.restore();
}

function drawLabel(text, x, y) {
  const paddingX = 8;
  const paddingY = 5;
  ctx.font = '12px Inter, Arial, sans-serif';
  const textWidth = ctx.measureText(text).width;
  const boxWidth = textWidth + paddingX * 2;
  const boxHeight = 24;

  ctx.save();
  ctx.fillStyle = 'rgba(9, 14, 27, 0.82)';
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
  ctx.lineWidth = 1;
  roundRect(ctx, x, y - boxHeight, boxWidth, boxHeight, 12);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = '#eef4ff';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, x + paddingX, y - boxHeight / 2 + 1);
  ctx.restore();
}

function roundRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.closePath();
}

function drawPoints(points, centerX, centerY) {
  ctx.font = '12px Inter, Arial, sans-serif';

  for (const point of points) {
    const screenX = centerX + point.x * SCALE;
    const screenY = centerY - point.y * SCALE;
    const color = rgbString(point.rgb, 1);

    ctx.save();

    ctx.shadowColor = rgbString(point.rgb, 0.65);
    ctx.shadowBlur = 18;
    ctx.fillStyle = rgbString(point.rgb, 0.2);
    ctx.beginPath();
    ctx.arc(screenX, screenY, POINT_RADIUS + 6, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(8, 17, 31, 0.92)';
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(screenX, screenY, POINT_RADIUS, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(screenX, screenY, 2.8, 0, Math.PI * 2);
    ctx.fill();

    if (SHOW_LABELS) {
      drawLabel(`${point.label}  ${point.noise.toFixed(1)}`, screenX + 10, screenY - 10);
    }

    ctx.restore();
  }
}

function render(points) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const centerX = width / 2;
  const centerY = height / 2;

  ctx.clearRect(0, 0, width, height);
  drawBackground(width, height, centerX, centerY);
  drawGrid(width, height, centerX, centerY);
  drawInfluence(points, centerX, centerY, width, height);
  drawAxes(width, height, centerX, centerY);
  drawPoints(points, centerX, centerY);
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function renderLegend() {
  legendEl.innerHTML = '';
  for (const item of LEGEND_ITEMS) {
    const row = document.createElement('div');
    row.className = 'legend-item';

    const left = document.createElement('div');
    left.className = 'legend-left';

    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch';
    swatch.style.background = rgbString(item.color, 1);

    const label = document.createElement('span');
    label.textContent = item.label;

    left.appendChild(swatch);
    left.appendChild(label);

    const desc = document.createElement('span');
    desc.className = 'legend-desc';
    desc.textContent = item.desc || '';

    row.appendChild(left);
    row.appendChild(desc);
    legendEl.appendChild(row);
  }
}

function renderSensorList(sensors) {
  if (!sensorListEl) return;
  // always update count
  if (sensorCountEl) sensorCountEl.textContent = String(Array.isArray(sensors) ? sensors.length : 0);

  // only populate full list when expanded
  if (!sensorExpanded) {
    sensorListEl.innerHTML = '';
    return;
  }

  sensorListEl.innerHTML = '';
  if (!Array.isArray(sensors) || sensors.length === 0) {
    sensorListEl.textContent = '当前无已注册设备';
    return;
  }

  const list = document.createElement('div');
  list.className = 'sensor-list-rows';

  for (const s of sensors) {
    const row = document.createElement('div');
    row.className = 'sensor-row';

    const left = document.createElement('div');
    left.className = 'sensor-left';
    left.innerHTML = `<div><strong>传感器 ${String(s.id)}</strong> ${s.has_position ? '' : '<span style="color:#f59e0b">(无坐标)</span>'}</div>`;

    const ip = document.createElement('div');
    ip.className = 'sensor-ip';
    ip.textContent = s.ip ? `${s.ip}:${s.port}` : '-';
    left.appendChild(ip);

    const right = document.createElement('div');
    right.className = 'sensor-right';
    const onlineDot = document.createElement('span');
    onlineDot.style.display = 'inline-block';
    onlineDot.style.width = '10px';
    onlineDot.style.height = '10px';
    onlineDot.style.borderRadius = '50%';
    onlineDot.style.marginRight = '8px';
    onlineDot.style.background = s.online ? '#4ade80' : '#ef4444';

    const noiseText = document.createElement('span');
    noiseText.textContent = s.last_noise != null ? `噪音 ${Number(s.last_noise).toFixed(1)}` : '';

    const lastSeen = document.createElement('div');
    lastSeen.className = 'sensor-lastseen';
    lastSeen.style.fontSize = '11px';
    lastSeen.style.color = 'rgba(220,220,220,0.7)';
    lastSeen.textContent = s.last_seen ? new Date(s.last_seen * 1000).toLocaleString() : '';

    right.appendChild(onlineDot);
    right.appendChild(noiseText);
    right.appendChild(lastSeen);

    row.appendChild(left);
    row.appendChild(right);
    list.appendChild(row);
  }

  sensorListEl.appendChild(list);
}

async function refresh() {
  try {
    const [pointsJson, devicesJson] = await Promise.all([
      fetchJson(ENDPOINT),
      fetchJson(DEVICES_ENDPOINT ?? STATUS_ENDPOINT),
    ]);

    lastPoints = normalizePoints(pointsJson);
    lastUpdated = new Date();
    render(lastPoints);

    const sensors = Array.isArray(devicesJson.sensors) ? devicesJson.sensors : [];
    const registeredCount = Number(devicesJson.count ?? devicesJson.registered_count ?? sensors.length ?? 0);
    const onlineCount = sensors.filter((sensor) => sensor.online).length;

    renderSensorList(sensors);

    registeredCountEl.textContent = String(registeredCount);
    renderedCountEl.textContent = String(lastPoints.length);
    onlineCountEl.textContent = String(onlineCount);
    updatedTimeEl.textContent = lastUpdated.toLocaleTimeString();

    statusEl.textContent = `系统运行正常，当前已渲染 ${lastPoints.length} 个传感器点位`;
    subStatusEl.textContent = '坐标由后端按传感器 ID 映射，颜色与等级也由后端统一判断';
    liveDotEl.style.background = onlineCount > 0 ? '#4ade80' : '#f59e0b';
  } catch (error) {
    statusEl.textContent = `获取失败: ${error.message}`;
    subStatusEl.textContent = '请确认 mock_server.py 与传感器服务是否已启动';
    liveDotEl.style.background = '#ef4444';
  }
}

window.addEventListener('resize', resizeCanvas);
renderLegend();
resizeCanvas();
refresh();
setInterval(refresh, POLL_INTERVAL_MS);
