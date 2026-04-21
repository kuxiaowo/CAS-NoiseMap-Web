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
const adminSensorListEl = document.getElementById('adminSensorList');
const adminSummaryEl = document.getElementById('adminSummary');
const adminSearchInput = document.getElementById('adminSearchInput');
const reloadAdminButton = document.getElementById('reloadAdminButton');
const addSensorButton = document.getElementById('addSensorButton');
const newSensorIdInput = document.getElementById('newSensorId');

const API_BASE = (window.CONFIG?.apiBase || `${location.origin}/api`).replace(/\/$/, '');
const ENDPOINTS = {
  points: `${API_BASE}/points`,
  status: `${API_BASE}/status`,
  devices: `${API_BASE}/devices`,
  config: `${API_BASE}/config`,
  sensors: `${API_BASE}/sensors`,
};

let sensorExpanded = false;
let frontendConfig = {
  poll_interval_ms: 1000,
  scale: 2,
  point_radius: 6,
  influence_radius: 90,
  influence_opacity: 0.26,
  map_image: 'map.png',
  map_anchor: { x: 0, y: 0 },
  map_scale: 1,
  outside_color: '#dcdcdc',
  axis_color: 'rgba(140, 154, 179, 0.45)',
  show_labels: true,
  glow_intensity: 1,
  grid_enabled: false,
  legend: [],
};
let pollTimer = null;
let mapLoaded = false;
let lastPoints = [];
let adminSensors = [];
let lastUpdated = null;
const expandedSensorIds = new Set();
let adminFilterText = '';

const mapImage = new Image();
mapImage.onload = () => {
  mapLoaded = true;
  render(lastPoints);
};

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

function createLayerCanvas() {
  return document.createElement('canvas');
}

const influenceLayer = createLayerCanvas();
const influenceCtx = influenceLayer.getContext('2d');

function rgbString(rgb, alpha = 1) {
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`;
}

function normalizePoints(points) {
  if (!Array.isArray(points)) return [];
  return points
    .filter((point) => Number.isFinite(Number(point.x)) && Number.isFinite(Number(point.y)))
    .map((point) => ({
      id: Number(point.id),
      label: point.label || `Sensor ${point.id}`,
      x: Number(point.x),
      y: Number(point.y),
      noise: Number(point.noise ?? 0),
      rgb: Array.isArray(point.rgb) ? point.rgb.map((value) => Number(value)) : [120, 120, 120],
      level: String(point.level || 'unknown'),
      online: Boolean(point.online),
    }));
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

function drawBackground(width, height, centerX, centerY) {
  ctx.fillStyle = frontendConfig.outside_color || '#dcdcdc';
  ctx.fillRect(0, 0, width, height);

  if (!mapLoaded) return;

  const anchorX = Number(frontendConfig.map_anchor?.x) || 0;
  const anchorY = Number(frontendConfig.map_anchor?.y) || 0;
  const scale = Number(frontendConfig.scale ?? 1) * Number(frontendConfig.map_scale ?? 1);
  const drawX = centerX - anchorX * scale;
  const drawY = centerY - anchorY * scale;

  ctx.save();
  ctx.globalAlpha = 0.95;
  ctx.drawImage(mapImage, drawX, drawY, mapImage.width * scale, mapImage.height * scale);
  ctx.restore();
}

function drawGrid(width, height, centerX, centerY) {
  if (!frontendConfig.grid_enabled) return;

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

  const scale = Number(frontendConfig.scale ?? 1);
  const radius = Number(frontendConfig.influence_radius ?? 90) * scale;
  const opacity = Number(frontendConfig.influence_opacity ?? 0.25);
  const glowIntensity = Number(frontendConfig.glow_intensity ?? 1);

  for (const point of points) {
    const screenX = centerX + point.x * scale;
    const screenY = centerY - point.y * scale;
    const gradient = influenceCtx.createRadialGradient(screenX, screenY, 0, screenX, screenY, radius);
    gradient.addColorStop(0, rgbString(point.rgb, opacity * glowIntensity));
    gradient.addColorStop(0.35, rgbString(point.rgb, opacity * 0.58 * glowIntensity));
    gradient.addColorStop(0.7, rgbString(point.rgb, opacity * 0.18 * glowIntensity));
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
  ctx.strokeStyle = frontendConfig.axis_color || 'rgba(140, 154, 179, 0.45)';
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
  const boxHeight = 24;
  ctx.font = '12px Inter, Arial, sans-serif';
  const textWidth = ctx.measureText(text).width;
  const boxWidth = textWidth + paddingX * 2;

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

function drawPoints(points, centerX, centerY) {
  const scale = Number(frontendConfig.scale ?? 1);
  const pointRadius = Number(frontendConfig.point_radius ?? 6);
  const showLabels = Boolean(frontendConfig.show_labels ?? true);

  for (const point of points) {
    const screenX = centerX + point.x * scale;
    const screenY = centerY - point.y * scale;
    const color = rgbString(point.rgb, 1);

    ctx.save();
    ctx.shadowColor = rgbString(point.rgb, 0.65);
    ctx.shadowBlur = 18;
    ctx.fillStyle = rgbString(point.rgb, 0.2);
    ctx.beginPath();
    ctx.arc(screenX, screenY, pointRadius + 6, 0, Math.PI * 2);
    ctx.fill();

    ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(8, 17, 31, 0.92)';
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(screenX, screenY, pointRadius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(screenX, screenY, 2.8, 0, Math.PI * 2);
    ctx.fill();

    if (showLabels) {
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

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

function renderLegend() {
  legendEl.innerHTML = '';
  const items = Array.isArray(frontendConfig.legend) ? frontendConfig.legend : [];
  for (const item of items) {
    const row = document.createElement('div');
    row.className = 'legend-item';

    const left = document.createElement('div');
    left.className = 'legend-left';

    const swatch = document.createElement('span');
    swatch.className = 'legend-swatch';
    swatch.style.background = rgbString(item.color || [120, 120, 120], 1);

    const label = document.createElement('span');
    label.textContent = item.label || '未命名';

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

function formatDateTime(timestampSeconds) {
  if (!timestampSeconds) return '暂无';
  return new Date(timestampSeconds * 1000).toLocaleString();
}

function renderSensorList(sensors) {
  if (!sensorListEl) return;
  if (sensorCountEl) sensorCountEl.textContent = String(Array.isArray(sensors) ? sensors.length : 0);
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

  for (const sensor of sensors) {
    const row = document.createElement('div');
    row.className = 'sensor-row';

    const left = document.createElement('div');
    left.className = 'sensor-left';
    left.innerHTML = `<div><strong>${sensor.label || `传感器 ${sensor.id}`}</strong>${sensor.enabled ? '' : ' <span style="color:#f59e0b">(已禁用)</span>'}</div>`;

    const ip = document.createElement('div');
    ip.className = 'sensor-ip';
    ip.textContent = sensor.device_ip ? `${sensor.device_ip}:${sensor.device_port || 8000}` : '-';
    left.appendChild(ip);

    const right = document.createElement('div');
    right.className = 'sensor-right';

    const onlineDot = document.createElement('span');
    onlineDot.style.display = 'inline-block';
    onlineDot.style.width = '10px';
    onlineDot.style.height = '10px';
    onlineDot.style.borderRadius = '50%';
    onlineDot.style.marginRight = '8px';
    onlineDot.style.background = sensor.enabled ? (sensor.online ? '#4ade80' : '#ef4444') : '#f59e0b';

    const noiseText = document.createElement('span');
    noiseText.textContent = sensor.last_noise != null ? `噪音 ${Number(sensor.last_noise).toFixed(1)}` : '暂无数据';

    const lastSeen = document.createElement('div');
    lastSeen.className = 'sensor-lastseen';
    lastSeen.textContent = formatDateTime(sensor.last_seen);

    right.appendChild(onlineDot);
    right.appendChild(noiseText);
    right.appendChild(lastSeen);

    row.appendChild(left);
    row.appendChild(right);
    list.appendChild(row);
  }

  sensorListEl.appendChild(list);
}

function createNumberField(labelText, name, value, step = '1', disabled = false) {
  const field = document.createElement('div');
  field.className = 'field';

  const label = document.createElement('label');
  label.textContent = labelText;

  const input = document.createElement('input');
  input.type = 'number';
  input.name = name;
  input.step = step;
  input.value = value ?? '';
  input.disabled = disabled;

  field.appendChild(label);
  field.appendChild(input);
  return field;
}

function createTextField(labelText, name, value, disabled = false) {
  const field = document.createElement('div');
  field.className = 'field wide';

  const label = document.createElement('label');
  label.textContent = labelText;

  const input = document.createElement('input');
  input.type = 'text';
  input.name = name;
  input.value = value ?? '';
  input.disabled = disabled;

  field.appendChild(label);
  field.appendChild(input);
  return field;
}

function renderAdminSummary(sensors) {
  if (!adminSummaryEl) return;
  const total = sensors.length;
  const enabled = sensors.filter((sensor) => sensor.enabled).length;
  const online = sensors.filter((sensor) => sensor.online).length;
  const rest = total - online;
  adminSummaryEl.innerHTML = `
    <div class="summary-chip"><span>总数</span><strong>${total}</strong></div>
    <div class="summary-chip"><span>启用</span><strong>${enabled}</strong></div>
    <div class="summary-chip"><span>在线</span><strong>${online}</strong></div>
    <div class="summary-chip"><span>离线/禁用</span><strong>${rest}</strong></div>
  `;
}

function renderAdminSensors(sensors) {
  adminSensorListEl.innerHTML = '';

  if (!Array.isArray(sensors) || sensors.length === 0) {
    adminSensorListEl.innerHTML = '<div class="admin-sensor-list-empty">当前无传感器配置</div>';
    return;
  }

  const normalizedFilter = adminFilterText.trim().toLowerCase();
  const visibleSensors = sensors.filter((sensor) => {
    if (!normalizedFilter) return true;
    return String(sensor.id).includes(normalizedFilter) || String(sensor.label || '').toLowerCase().includes(normalizedFilter);
  });

  if (visibleSensors.length === 0) {
    adminSensorListEl.innerHTML = '<div class="admin-sensor-list-empty">没有匹配的传感器</div>';
    return;
  }

  for (const sensor of visibleSensors) {
    const item = document.createElement('div');
    const expanded = expandedSensorIds.has(sensor.id);
    item.className = `admin-sensor-item ${expanded ? 'expanded' : 'collapsed'}`;

    const header = document.createElement('div');
    header.className = 'admin-sensor-header';

    const left = document.createElement('div');
    left.className = 'admin-sensor-title';
    left.setAttribute('role', 'button');
    left.tabIndex = 0;

    const topline = document.createElement('div');
    topline.className = 'admin-sensor-topline';
    const title = document.createElement('strong');
    title.textContent = `${sensor.label || `传感器 ${sensor.id}`} (#${sensor.id})`;
    const fold = document.createElement('span');
    fold.className = 'fold-indicator';
    fold.textContent = expanded ? '收起' : '展开';
    topline.appendChild(title);
    topline.appendChild(fold);

    const meta = document.createElement('div');
    meta.className = 'admin-meta';
    meta.textContent = `最后上报: ${formatDateTime(sensor.last_seen)}，最近值: ${sensor.last_noise != null ? Number(sensor.last_noise).toFixed(1) : '暂无'}`;
    left.appendChild(topline);
    left.appendChild(meta);

    const badge = document.createElement('span');
    badge.className = 'status-badge';
    badge.innerHTML = `<span class="dot ${sensor.enabled ? (sensor.online ? 'online' : 'offline') : 'disabled'}"></span>${sensor.enabled ? (sensor.online ? '在线' : '离线') : '已禁用'}`;

    const toggleExpanded = () => {
      if (expandedSensorIds.has(sensor.id)) {
        expandedSensorIds.delete(sensor.id);
      } else {
        expandedSensorIds.add(sensor.id);
      }
      renderAdminSensors(adminSensors);
    };
    left.addEventListener('click', toggleExpanded);
    left.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleExpanded();
      }
    });

    header.appendChild(left);
    header.appendChild(badge);

    const form = document.createElement('form');
    form.className = 'admin-sensor-content';
    form.dataset.sensorId = String(sensor.id);

    const row1 = document.createElement('div');
    row1.className = 'form-grid';
    row1.appendChild(createTextField('标签', 'label', sensor.label));

    const enabledField = document.createElement('div');
    enabledField.className = 'field';
    const enabledLabel = document.createElement('label');
    enabledLabel.textContent = '启用状态';
    const toggleLabel = document.createElement('label');
    toggleLabel.className = 'toggle-label';
    const enabledInput = document.createElement('input');
    enabledInput.type = 'checkbox';
    enabledInput.name = 'enabled';
    enabledInput.checked = Boolean(sensor.enabled);
    toggleLabel.appendChild(enabledInput);
    toggleLabel.appendChild(document.createTextNode('启用该传感器'));
    enabledField.appendChild(enabledLabel);
    enabledField.appendChild(toggleLabel);
    row1.appendChild(enabledField);

    const row2 = document.createElement('div');
    row2.className = 'form-grid';
    row2.appendChild(createNumberField('X 坐标', 'x', sensor.x, '0.1'));
    row2.appendChild(createNumberField('Y 坐标', 'y', sensor.y, '0.1'));
    row2.appendChild(createNumberField('上报频率(ms)', 'report_interval_ms', sensor.report_interval_ms, '100'));

    const calibrationPoints = Array.isArray(sensor.calibration_points) ? sensor.calibration_points.slice(0, 3) : [];
    while (calibrationPoints.length < 3) {
      calibrationPoints.push({ db: '', raw_rms: '' });
    }

    const row3 = document.createElement('div');
    row3.className = 'form-grid';
    row3.appendChild(createNumberField('校准点1 dB', 'calibration_point_1_db', calibrationPoints[0].db, '0.1'));
    row3.appendChild(createNumberField('校准点1 RMS', 'calibration_point_1_raw_rms', calibrationPoints[0].raw_rms, '0.1'));

    const row4 = document.createElement('div');
    row4.className = 'form-grid';
    row4.appendChild(createNumberField('校准点2 dB', 'calibration_point_2_db', calibrationPoints[1].db, '0.1'));
    row4.appendChild(createNumberField('校准点2 RMS', 'calibration_point_2_raw_rms', calibrationPoints[1].raw_rms, '0.1'));

    const row5 = document.createElement('div');
    row5.className = 'form-grid';
    row5.appendChild(createNumberField('校准点3 dB', 'calibration_point_3_db', calibrationPoints[2].db, '0.1'));
    row5.appendChild(createNumberField('校准点3 RMS', 'calibration_point_3_raw_rms', calibrationPoints[2].raw_rms, '0.1'));

    const row6 = document.createElement('div');
    row6.className = 'form-grid';
    row6.appendChild(createNumberField('最小 dB', 'min_db', sensor.min_db, '0.1'));
    row6.appendChild(createNumberField('最大 dB', 'max_db', sensor.max_db, '0.1'));

    const actions = document.createElement('div');
    actions.className = 'admin-actions';

    const saveButton = document.createElement('button');
    saveButton.type = 'submit';
    saveButton.textContent = '保存';

    const manageButton = document.createElement('button');
    manageButton.type = 'button';
    manageButton.className = 'secondary-button';
    manageButton.textContent = '打开设备管理页';
    const devicePort = Number(sensor.device_port || 80);
    const manageUrl = sensor.device_ip ? `http://${sensor.device_ip}:${devicePort}/admin?password=187geufo` : '';
    if (!sensor.device_ip || !sensor.online) {
      manageButton.disabled = true;
      manageButton.title = '设备离线或暂无 IP，无法打开管理页';
    } else {
      manageButton.title = manageUrl;
      manageButton.addEventListener('click', () => {
        window.open(manageUrl, '_blank', 'noopener,noreferrer');
      });
    }

    const deleteButton = document.createElement('button');
    deleteButton.type = 'button';
    deleteButton.className = 'danger-button';
    deleteButton.textContent = '删除';
    deleteButton.addEventListener('click', async () => {
      if (!window.confirm(`确认删除传感器 #${sensor.id} 吗？`)) return;
      deleteButton.disabled = true;
      try {
        await fetchJson(`${ENDPOINTS.sensors}/${sensor.id}`, { method: 'DELETE' });
        await reloadAdmin();
      } catch (error) {
        alert(`删除失败: ${error.message}`);
      } finally {
        deleteButton.disabled = false;
      }
    });

    actions.appendChild(saveButton);
    actions.appendChild(manageButton);
    actions.appendChild(deleteButton);

    const saveHint = document.createElement('div');
    saveHint.className = 'save-hint';
    saveHint.textContent = sensor.device_ip
      ? `设备管理页地址: http://${sensor.device_ip}:${Number(sensor.device_port || 80)}/admin`
      : '保存后立即写入后端配置文件，并在下一轮刷新中生效。';

    const message = document.createElement('div');
    message.className = 'admin-message';

    form.appendChild(row1);
    form.appendChild(row2);
    form.appendChild(row3);
    form.appendChild(row4);
    form.appendChild(row5);
    form.appendChild(row6);
    form.appendChild(actions);
    form.appendChild(saveHint);
    form.appendChild(message);

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      saveButton.disabled = true;
      message.textContent = '保存中...';
      const formData = new FormData(form);
      const calibrationPayload = [1, 2, 3].map((index) => ({
        db: Number(formData.get(`calibration_point_${index}_db`) || 0),
        raw_rms: Number(formData.get(`calibration_point_${index}_raw_rms`) || 0),
      }));

      if (calibrationPayload.some((point) => !Number.isFinite(point.db) || !Number.isFinite(point.raw_rms) || point.raw_rms <= 0)) {
        message.textContent = '保存失败: 三个校准点都要填写有效的 dB 和大于 0 的 RMS';
        saveButton.disabled = false;
        return;
      }

      const payload = {
        label: String(formData.get('label') || '').trim(),
        enabled: enabledInput.checked,
        x: Number(formData.get('x') || 0),
        y: Number(formData.get('y') || 0),
        report_interval_ms: Number(formData.get('report_interval_ms') || 1000),
        calibration_points: calibrationPayload,
        min_db: Number(formData.get('min_db') || 30),
        max_db: Number(formData.get('max_db') || 130),
      };

      try {
        await fetchJson(`${ENDPOINTS.sensors}/${sensor.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        message.textContent = '已保存';
        await reloadAdmin();
      } catch (error) {
        message.textContent = `保存失败: ${error.message}`;
      } finally {
        saveButton.disabled = false;
      }
    });

    item.appendChild(header);
    item.appendChild(form);
    adminSensorListEl.appendChild(item);
  }
}

async function loadAdminConfig() {
  const config = await fetchJson(ENDPOINTS.config);
  frontendConfig = { ...frontendConfig, ...(config.frontend || {}) };
  adminSensors = Array.isArray(config.sensors) ? config.sensors : [];
  renderLegend();
  renderAdminSummary(adminSensors);
  renderAdminSensors(adminSensors);
  mapLoaded = false;
  mapImage.src = frontendConfig.map_image || 'map.png';
  restartPolling();
}

function restartPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
  }
  const interval = Math.max(300, Number(frontendConfig.poll_interval_ms || 1000));
  pollTimer = setInterval(refreshRuntime, interval);
}

async function refreshRuntime() {
  try {
    const [pointsJson, devicesJson] = await Promise.all([
      fetchJson(ENDPOINTS.points),
      fetchJson(ENDPOINTS.devices),
    ]);

    lastPoints = normalizePoints(pointsJson);
    lastUpdated = new Date();
    render(lastPoints);

    const sensors = Array.isArray(devicesJson.sensors) ? devicesJson.sensors : [];
    adminSensors = sensors;
    const registeredCount = Number(devicesJson.count ?? sensors.length ?? 0);
    const onlineCount = sensors.filter((sensor) => sensor.online).length;

    renderSensorList(sensors);
    renderAdminSummary(sensors);
    renderAdminSensors(sensors);

    registeredCountEl.textContent = String(registeredCount);
    renderedCountEl.textContent = String(lastPoints.length);
    onlineCountEl.textContent = String(onlineCount);
    updatedTimeEl.textContent = lastUpdated.toLocaleTimeString();

    statusEl.textContent = `系统运行正常，当前已渲染 ${lastPoints.length} 个启用中的传感器点位`;
    subStatusEl.textContent = '网页端可直接修改传感器配置，保存后会立刻写入后端配置文件';
    liveDotEl.style.background = onlineCount > 0 ? '#4ade80' : '#f59e0b';
  } catch (error) {
    statusEl.textContent = `获取失败: ${error.message}`;
    subStatusEl.textContent = '请确认 mock_server.py 已启动，且传感器正在主动上报';
    liveDotEl.style.background = '#ef4444';
  }
}

async function reloadAdmin() {
  reloadAdminButton.disabled = true;
  try {
    await loadAdminConfig();
    await refreshRuntime();
  } finally {
    reloadAdminButton.disabled = false;
  }
}

reloadAdminButton?.addEventListener('click', () => {
  reloadAdmin();
});

adminSearchInput?.addEventListener('input', (event) => {
  adminFilterText = String(event.target.value || '');
  renderAdminSensors(adminSensors);
});

addSensorButton?.addEventListener('click', async () => {
  const sensorId = Number(newSensorIdInput.value);
  if (!Number.isInteger(sensorId) || sensorId < 0 || sensorId > 100) {
    alert('请输入 0 到 100 的整数传感器 ID');
    return;
  }
  addSensorButton.disabled = true;
  try {
    await fetchJson(ENDPOINTS.sensors, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: sensorId }),
    });
    newSensorIdInput.value = '';
    await reloadAdmin();
  } catch (error) {
    alert(`新增失败: ${error.message}`);
  } finally {
    addSensorButton.disabled = false;
  }
});

window.addEventListener('resize', resizeCanvas);
resizeCanvas();
loadAdminConfig().then(refreshRuntime);
