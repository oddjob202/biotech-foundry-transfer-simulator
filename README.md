# The Biotech Foundry — Hydraulic Transfer Simulator

Iteration 1 is a modular simulator for clean-water transfer between two open, atmospheric tanks. The calculation engine is independent of Streamlit and uses SI units throughout.

## Setup (macOS Apple Silicon)

Install Python 3.13 (for example, `brew install python@3.13`), then from this project directory:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
streamlit run app.py
```

Run automated checks with `pytest`.

## Model

Inputs are two cylindrical tank sizes, starting volumes, tank-floor elevations, approximate common pipe internal diameters (¼, ½, ¾, 1, 1½, 1.8, and 2 in), pipe length in feet, absolute roughness, water temperature in °C, and aggregate fitting loss coefficient. Pipe sizes are treated as internal diameters; actual sanitary-tube and pipe IDs depend on schedule/wall thickness, so use the Custom option when a datasheet value is available. Water density follows the Kell correlation and dynamic viscosity an Andrade-type correlation, both restricted to 0–100 °C.

- Area: `A = πD²/4`; velocity: `v = Q/A`; Reynolds number: `Re = ρvD/μ`.
- Darcy friction factor is `64/Re` in laminar flow (≤2300), a linear blend from 2300–4000, and the Colebrook relation above 4000.
- Darcy–Weisbach loss: `h_f = f(L/D)v²/(2g)`; fitting loss: `h_m = ΣK v²/(2g)`.
- Required total dynamic head: `H = (z_destination − z_source) + h_f + h_m`.
- Hydraulic power: `P_h = ρgQH`.
- During the simulation, each tank surface is calculated from its current volume and cross-sectional area. At each time step, the app recomputes the pump/system intersection, then transfers `QΔt` while conserving volume. The run ends when the source is empty, the destination is full, or no valid pump operating point remains.

The bundled pump catalog is deliberately synthetic: centrifugal, hygienic diaphragm (AODD-style), and hygienic peristaltic teaching curves. The app searches for an intersection with the system curve using a bounded root finder and never extrapolates outside a curve. None are manufacturer data. This lets the dashboard compare common pump *types* while preserving the boundary between a training calculation and equipment selection. The interactive curve supports hover, pan/zoom, reset, and image export.

## Scope and limitations

This is a quasi-steady, incompressible, single-phase, fully filled-pipe water model. Both tanks are atmospheric and modeled as vertical cylinders; their levels change between discrete time steps. It excludes pump efficiency/NPSH, startup transients, water hammer, air entrainment, leaks, non-water media, networks, and detailed positive-displacement-pump physics. The built-in diaphragm and peristaltic curves are simplified envelopes, not sizing tools. Pump input power therefore cannot be inferred from hydraulic power alone.

Future work can add manufacturer curve imports, pump efficiency and NPSH, non-cylindrical tank geometry, additional fluid property models, and component/network models.
