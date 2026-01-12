const CONFIG = {
  scale: 2, // 1 unit = 1 px
  pointRadius: 4, // pixels
  influenceRadius: 50, // custom units
  influenceOpacity: 0.5, // 0-1, transparency for influence raster
  mapImage: 'map.png',
  // Anchor (image pixel) that should coincide with the world origin (0, 0)
  mapAnchor: { x: 800, y: 780 },
  mapScale: 0.5, // background map scaling factor (1 = original pixel size)
};

window.CONFIG = CONFIG;
