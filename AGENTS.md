# Repository Guidelines

## Project Structure
- `index.html`, `style.css`, `config.js`, `app.js` are the frontend entry files.
- `mock_server.py` is the backend for sensor registration, polling, coordinate mapping, and point output.
- `serve_web.py` serves static files for browser access.
- `sensor_simulator.py` emulates hardware sensors for local development.
- `sensor_positions.json` stores sensor `id -> coordinate` mapping.
- `map.png` is the background map image.

## Design Rules
- Keep frontend focused on rendering only.
- Keep sensor color logic in backend only.
- Keep `id -> coordinate` mapping in backend config, not in frontend.
- Do not change ESP protocol unless explicitly requested.

## Development Commands
- `python mock_server.py`
- `python serve_web.py`
- `python sensor_simulator.py --id 1 --backend http://127.0.0.1:9880`

## Style
- JavaScript: 2 spaces, camelCase, constants in upper snake case when appropriate.
- Python: 4 spaces, snake_case, keep route logic small and explicit.
- Prefer editing `sensor_positions.json` and `config.js` rather than hardcoding values.

## Manual Test Checklist
- Sensor can register successfully.
- Backend can poll `/noise` successfully.
- `/api/points` returns points with `x`, `y`, `rgb`.
- Frontend can render map, points, and influence zones.
- Missing sensor coordinate config does not crash the backend.
