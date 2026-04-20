const CONFIG = {
  endpoint: `http://${location.hostname}:9880/api/points`,
  statusEndpoint: `http://${location.hostname}:9880/api/status`,
  devicesEndpoint: `http://${location.hostname}:9880/api/devices`,
  pollIntervalMs: 200,
  scale: 2,
  pointRadius: 6,
  influenceRadius: 90,
  influenceOpacity: 0.26,
  mapImage: 'map.png',
  mapAnchor: { x: 800, y: 780 },
  mapScale: 0.5,
  outsideColor: '#d7dde7',
  axisColor: 'rgba(140, 154, 179, 0.45)',
  showLabels: true,
  glowIntensity: 1,
  gridEnabled: false,
  legend: [
    { label: '低噪音', color: [0, 200, 0], desc: '< 55' },
    { label: '中噪音', color: [255, 200, 0], desc: '55 - 75' },
    { label: '高噪音', color: [255, 0, 0], desc: '>= 75' },
  ],
};

window.CONFIG = CONFIG;
