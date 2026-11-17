"""Interactive two-tank water-transfer simulator."""
from dataclasses import replace

import numpy as np
import streamlit as st

from biotech_foundry.hydraulics import HydraulicInputError, SystemConfiguration, calculate_hydraulics
from biotech_foundry.pumps import find_operating_point, pump_catalog
from biotech_foundry.simulation import CylindricalTank, TransferState, advance_transfer, operating_point_at_state

INCH_TO_M = 0.0254
FOOT_TO_M = 0.3048
PIPE_DIAMETERS_IN = {
    "1/4 in": 0.25, "1/2 in": 0.50, "3/4 in": 0.75, "1 in": 1.00,
    "1.5 in": 1.50, "1.8 in": 1.80, "2 in": 2.00, "Custom internal diameter…": None,
}

st.set_page_config(page_title="Biotech Foundry | Tank Transfer", layout="wide")
st.title("The Biotech Foundry — tank-transfer simulator")
st.caption("Set up two open tanks, choose a pump, then press Play. Tank levels and the pump operating point change as water moves.")

pumps = pump_catalog()
with st.sidebar:
    st.header("Source tank")
    source_capacity_l = st.number_input("Source tank capacity (L)", min_value=1.0, value=1000.0, key="source_capacity")
    source_start_l = st.number_input("Starting water in source (L)", min_value=0.0, value=500.0, key="source_start")
    source_diameter_m = st.number_input("Source tank diameter (m)", min_value=0.05, value=1.0, key="source_diameter")
    source_base_m = st.number_input("Source tank floor elevation (m)", value=0.0, key="source_base")
    st.header("Destination tank")
    destination_capacity_l = st.number_input("Destination tank capacity (L)", min_value=1.0, value=1000.0, key="destination_capacity")
    destination_start_l = st.number_input("Starting water in destination (L)", min_value=0.0, value=0.0, key="destination_start")
    destination_diameter_m = st.number_input("Destination tank diameter (m)", min_value=0.05, value=1.0, key="destination_diameter")
    destination_base_m = st.number_input("Destination tank floor elevation (m)", value=8.0, key="destination_base")
    st.header("Piping")
    pipe_choice = st.selectbox("Approximate pipe internal diameter", list(PIPE_DIAMETERS_IN), index=3, key="pipe_choice")
    diameter_in = PIPE_DIAMETERS_IN[pipe_choice]
    if diameter_in is None:
        diameter_in = st.number_input("Custom internal diameter (in)", min_value=0.01, value=1.00, format="%.3f", key="custom_diameter")
    st.caption("Pipe schedule and sanitary tubing have different true IDs; use Custom for a datasheet value.")
    length_ft = st.number_input("Pipe length (ft)", min_value=0.0, value=65.6, key="pipe_length")
    roughness_mm = st.number_input("Absolute roughness (mm)", min_value=0.0, value=0.045, format="%.4f", key="roughness")
    minor_k = st.number_input("Total fitting loss coefficient, ΣK", min_value=0.0, value=4.0, key="minor_k")
    temperature_c = st.number_input("Water temperature (°C)", min_value=0.0, max_value=100.0, value=20.0, key="temperature")
    st.header("Pump")
    pump_name = st.selectbox("Pump type", list(pumps), key="pump_name")
    simulation_step_s = st.slider("Simulation speed: seconds per update", min_value=1, max_value=30, value=5, key="simulation_step")

source_tank = CylindricalTank(source_diameter_m, source_capacity_l / 1000, source_base_m)
destination_tank = CylindricalTank(destination_diameter_m, destination_capacity_l / 1000, destination_base_m)
base_config = SystemConfiguration(diameter_in * INCH_TO_M, length_ft * FOOT_TO_M, roughness_mm / 1000,
                                  temperature_c, source_base_m, destination_base_m, minor_k)
pump = pumps[pump_name]
initial_state = TransferState(source_start_l / 1000, destination_start_l / 1000)
signature = (source_tank, destination_tank, base_config, pump_name, initial_state)

try:
    source_tank.surface_elevation_m(initial_state.source_volume_m3)
    destination_tank.surface_elevation_m(initial_state.destination_volume_m3)
except HydraulicInputError as exc:
    st.error(str(exc))
    st.stop()

if st.session_state.get("sim_signature") != signature:
    st.session_state.sim_signature = signature
    st.session_state.sim_state = initial_state
    st.session_state.sim_running = False

st.info("This is a simple dynamic simulation: both tanks are vertical cylinders; tank levels change, and the pump/system intersection is recalculated at each time step. The bundled pump curves remain illustrative.")


@st.fragment(run_every=0.5, key="transfer_animation")
def transfer_animation() -> None:
    state: TransferState = st.session_state.sim_state
    if st.session_state.sim_running:
        state = advance_transfer(base_config, source_tank, destination_tank, state, pump, simulation_step_s)
        st.session_state.sim_state = state
        if state.status != "Running":
            st.session_state.sim_running = False

    controls = st.container(horizontal=True, vertical_alignment="bottom")
    with controls:
        if st.button("Play", icon=":material/play_arrow:", key="play_transfer", disabled=st.session_state.sim_running):
            if state.status != "Running":
                st.session_state.sim_state = initial_state
                state = initial_state
            st.session_state.sim_running = True
        if st.button("Pause", icon=":material/pause:", key="pause_transfer", disabled=not st.session_state.sim_running):
            st.session_state.sim_running = False
        if st.button("Reset", icon=":material/restart_alt:", key="reset_transfer"):
            st.session_state.sim_state = initial_state
            st.session_state.sim_running = False
            state = initial_state

    state = st.session_state.sim_state
    point = operating_point_at_state(base_config, source_tank, destination_tank, state, pump)
    source_level = source_tank.surface_elevation_m(state.source_volume_m3)
    destination_level = destination_tank.surface_elevation_m(state.destination_volume_m3)
    current_config = replace(base_config, source_elevation_m=source_level, destination_elevation_m=destination_level)
    current_flow = point.flow_m3_s if point else 0.0
    current = calculate_hydraulics(current_config, current_flow)
    source_percent = 100 * state.source_volume_m3 / source_tank.capacity_m3
    destination_percent = 100 * state.destination_volume_m3 / destination_tank.capacity_m3
    remaining_s = state.source_volume_m3 / current_flow if current_flow > 0 else None

    with st.container(horizontal=True):
        st.metric("Source tank", f"{state.source_volume_m3 * 1000:.1f} L", f"{source_percent:.1f}% full", border=True)
        st.metric("Destination tank", f"{state.destination_volume_m3 * 1000:.1f} L", f"{destination_percent:.1f}% full", border=True)
        st.metric("Current pump flow", f"{current_flow * 60_000:.1f} L/min", border=True)
        st.metric("Elapsed simulated time", f"{state.elapsed_s / 60:.1f} min", border=True)
        st.metric("Remaining at current flow", "—" if remaining_s is None else f"{remaining_s / 60:.1f} min", border=True)

    flow_active = st.session_state.sim_running and current_flow > 0
    flow_color = "#16a34a" if flow_active else "#64748b"
    pump_color = "#22c55e" if flow_active else "#94a3b8"
    tank_glow = "#22c55e" if flow_active else "transparent"
    if point is None:
        flow_color = pump_color = "#dc2626"
    flow_status = "Flow active" if flow_active else ("Pump unavailable" if point is None else "Paused")
    with st.container(border=True):
        st.markdown(f"#### :material/account_tree: Process status — :green[{flow_status}]" if flow_active else f"#### :material/account_tree: Process status — {flow_status}")
        st.echarts_chart(
            {
                "animation": False,
                "tooltip": {"formatter": "{b}"},
                "series": [{
                    "type": "graph", "layout": "none", "roam": False, "draggable": False,
                    "edgeSymbol": ["none", "arrow"], "edgeSymbolSize": [0, 14],
                    "label": {"show": True, "position": "inside", "color": "#ffffff", "fontSize": 13},
                    "edgeLabel": {"show": True, "formatter": "{c}", "color": flow_color},
                    "lineStyle": {"color": flow_color, "width": 4, "type": "dashed" if flow_active else "solid", "opacity": 0.9,
                                  "shadowBlur": 10 if flow_active else 0, "shadowColor": flow_color},
                    "data": [
                        {"name": "Source tank", "x": 40, "y": 55, "symbol": "roundRect", "symbolSize": [155, 78],
                         "itemStyle": {"color": "#2563eb", "shadowBlur": 18 if flow_active else 0, "shadowColor": tank_glow}},
                        {"name": "Outlet", "x": 120, "y": 145, "symbol": "circle", "symbolSize": 18,
                         "label": {"show": True, "position": "bottom", "formatter": "Bottom outlet", "color": flow_color}, "itemStyle": {"color": flow_color}},
                        {"name": "Transfer pump", "x": 265, "y": 145, "symbol": "circle", "symbolSize": 90,
                         "itemStyle": {"color": pump_color, "shadowBlur": 20 if flow_active else 0, "shadowColor": flow_color}},
                        {"name": "Inlet", "x": 420, "y": 25, "symbol": "circle", "symbolSize": 18,
                         "label": {"show": True, "position": "top", "formatter": "Top inlet", "color": flow_color}, "itemStyle": {"color": flow_color}},
                        {"name": "Destination tank", "x": 500, "y": 75, "symbol": "roundRect", "symbolSize": [165, 78],
                         "itemStyle": {"color": "#2563eb", "shadowBlur": 18 if flow_active else 0, "shadowColor": tank_glow}},
                    ],
                    "links": [
                        {"source": "Source tank", "target": "Outlet", "value": ""},
                        {"source": "Outlet", "target": "Transfer pump", "value": f"{current_flow * 60_000:.1f} L/min"},
                        {"source": "Transfer pump", "target": "Inlet", "value": f"{length_ft:.0f} ft · {diameter_in:g} in pipe"},
                        {"source": "Inlet", "target": "Destination tank", "value": ""},
                    ],
                }],
            },
            key="scada_flow_path",
            height=220,
            alt="SCADA-style process display of source tank, running pump, pipe, and destination tank",
        )
        st.caption(f"Selected pump: {pump.name}. Water exits the source through its bottom outlet, passes through the pump and pipe, then enters the destination at its top inlet. When flow is active, the tank and pump have a soft green aura and the transfer pipe becomes a glowing dashed line. Gray means paused; red means no valid operating point.")

    st.echarts_chart(
        {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": 60, "right": 28, "top": 30, "bottom": 48},
            "xAxis": {"type": "category", "data": ["Source tank", "Destination tank"]},
            "yAxis": {"type": "value", "name": "Filled (%)", "min": 0, "max": 100},
            "series": [{"name": "Tank fill", "type": "bar", "data": [float(source_percent), float(destination_percent)], "label": {"show": True, "formatter": "{c}%"}}],
        },
        key="tank_levels",
        height=270,
        alt="Source tank draining and destination tank filling as the transfer simulation runs",
    )

    st.caption(f"Status: {state.status}. Current water surfaces: source {source_level:.2f} m; destination {destination_level:.2f} m. Current TDH: {current.total_dynamic_head_m:.2f} m.")
    if point is None:
        st.warning("No valid operating point exists for the current liquid levels and selected illustrative pump.")

    flows = np.linspace(pump.min_flow_m3_s, pump.max_flow_m3_s, 151)
    curve_data = [{"Flow (L/min)": float(q * 60_000), "Pump head (m)": float(pump.head_m(float(q))),
                   "System head (m)": float(calculate_hydraulics(current_config, float(q)).total_dynamic_head_m)} for q in flows]
    series = [
        {"name": "Illustrative pump curve", "type": "line", "showSymbol": False, "encode": {"x": "Flow (L/min)", "y": "Pump head (m)"}},
        {"name": "Current system curve", "type": "line", "showSymbol": False, "encode": {"x": "Flow (L/min)", "y": "System head (m)"}},
    ]
    if point:
        series.append({"name": "Current operating point", "type": "scatter", "symbolSize": 11,
                       "data": [[float(point.flow_m3_s * 60_000), float(point.head_m)]]})
    st.echarts_chart(
        {"dataset": {"source": curve_data}, "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
         "legend": {"top": 4}, "grid": {"left": 72, "right": 24, "top": 52, "bottom": 92},
         "xAxis": {"type": "value", "name": "Flow (L/min)", "nameLocation": "middle", "nameGap": 32},
         "yAxis": {"type": "value", "name": "Head (m)", "nameLocation": "middle", "nameGap": 48, "min": 0},
         "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 15}],
         "toolbox": {"feature": {"dataZoom": {}, "restore": {}, "saveAsImage": {}}}, "series": series},
        key="dynamic_pump_system_curve", height=420,
        alt="Pump and changing system curves during transfer, with current operating point",
    )


transfer_animation()
st.caption("Limitations: water only; no pump efficiency/NPSH, startup transients, air entrainment, leaks, changing liquid properties, or detailed positive-displacement-pump behavior. This is a physically grounded first-pass simulator, not equipment-selection approval.")
