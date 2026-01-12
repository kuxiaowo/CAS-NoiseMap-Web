# Repository Guidelines

## Project Structure & Module Organization
- Frontend entry points live at `index.html`, `style.css`, `app.js`, and `config.js`.
- Static assets (background map) are stored in `map.png`.
- Local tooling scripts are in the repo root: `serve_web.py` (static web server), `mock_server.py` (FastAPI backend), and `sensor_simulator.py` (sensor data generator).

## Build, Test, and Development Commands
- `python serve_web.py` starts a simple static server at `http://127.0.0.1:8080`.
- `python mock_server.py` runs the FastAPI backend on `:9880`.
- Sensors register with `POST http://127.0.0.1:9880/api/regiter` using `{"id": 1, "ip": "192.168.1.10"}`.
- The backend polls each registered sensor at `http://<ip>:8000/noise` every 2 seconds.
- If dependencies are missing, install with `pip install fastapi uvicorn requests`.

## Coding Style & Naming Conventions
- JavaScript uses 2-space indentation; prefer `camelCase` for variables/functions and `UPPER_SNAKE_CASE` for constants.
- Python uses 4-space indentation; prefer `snake_case` for functions/variables and `UPPER_SNAKE_CASE` for constants.
- Keep configuration in `config.js` (e.g., `mapAnchor`, `scale`, `influenceRadius`) rather than hardcoding values.

## Testing Guidelines
- No automated tests are present. If you add tests, document the runner and command in this file.
- If introducing new Python modules, consider `pytest` and name tests like `test_<module>.py`.

## Commit & Pull Request Guidelines
- Commit message conventions are not documented here and git history is not available in this environment. Keep messages short and descriptive (e.g., "Adjust map anchor defaults").
- PRs should include a clear description, linked issue (if any), and a screenshot or screen recording for UI changes.
- Mention any new ports, config keys, or external dependencies in the PR description.

## Configuration Tips
- `config.js` controls the map background and rendering scale; adjust `mapAnchor` to align world origin with the map image.
- The frontend polls `http://<host>:9880/api/points` every 2 seconds; ensure `mock_server.py` is running for live data.
