"""Streamlit dashboard for the iteration-1 water-transfer simulator."""
import numpy as np
import streamlit as st

from biotech_foundry.hydraulics import HydraulicInputError, SystemConfiguration, calculate_hydraulics, transfer_time_seconds
from biotech_foundry.pumps import find_operating_point, pump_catalog

INCH_TO_M = 0.0254
FOOT_TO_M = 0.3048
PIPE_DIAMETERS_IN = {
    "1/4 in": 0.25, "1/2 in": 0.50, "3/4 in": 0.75, "1 in": 1.00,
    "1.5 in": 1.50, "1.8 in": 1.80, "2 in": 2.00, "Custom internal diameter…": None,
}

st.set_page_config(page_title="Biotech Foundry | Hydraulic Transfer", layout="wide")
st.title("The Biotech Foundry — Hydraulic Transfer Simulator")
st.caption("Iteration 1: steady water transfer between open atmospheric tanks. Built-in pump curves are illustrative—not manufacturer data.")

pumps = pump_catalog()
with st.sidebar:
    st.header("Piping and tanks")
    pipe_choice = st.selectbox("Approximate pipe internal diameter", list(PIPE_DIAMETERS_IN), index=3)
    if PIPE_DIAMETERS_IN[pipe_choice] is None:
        diameter_in = st.number_input("Custom internal diameter (in)", min_value=0.01, value=1.00, format="%.3f")
    else:
        diameter_in = PIPE_DIAMETERS_IN[pipe_choice]
    st.caption("Pipe schedules and sanitary tubing have different true internal diameters; use Custom for a datasheet value.")
    length_ft = st.number_input("Pipe length (ft)", min_value=0.0, value=65.6)
    roughness_mm = st.number_input("Absolute roughness (mm)", min_value=0.0, value=0.045, format="%.4f")
    temperature_c = st.number_input("Water temperature (°C)", min_value=0.0, max_value=100.0, value=20.0)
    source_m = st.number_input("Source water-surface elevation (m)", value=0.0)
    destination_m = st.number_input("Destination water-surface elevation (m)", value=8.0)
    minor_k = st.number_input("Total fitting loss coefficient, ΣK", min_value=0.0, value=4.0)
    st.header("Pump and transfer")
    pump_name = st.selectbox("Pump type", list(pumps))
    desired_lpm = st.number_input("Desired flow (L/min)", min_value=0.01, value=60.0)
    volume_l = st.number_input("Transfer volume (L)", min_value=0.01, value=500.0)

pump = pumps[pump_name]
config = SystemConfiguration(diameter_in * INCH_TO_M, length_ft * FOOT_TO_M, roughness_mm / 1000, temperature_c,
                             source_m, destination_m, minor_k)
desired_q = desired_lpm / 1000 / 60

try:
    desired = calculate_hydraulics(config, desired_q)
    point = find_operating_point(pump, config)
except HydraulicInputError as exc:
    st.error(str(exc))
    st.stop()

if desired_q > pump.max_flow_m3_s:
    st.warning(f"Requested flow is beyond this pump curve's {pump.max_flow_m3_s * 60_000:.1f} L/min range.")
if point is None:
    st.warning("No valid pump/system operating point exists inside this illustrative curve range.")
elif abs(point.flow_m3_s - desired_q) / desired_q > 0.05:
    st.info(f"Requested flow: {desired_lpm:.1f} L/min. This pump would naturally operate at "
            f"{point.flow_m3_s * 60_000:.1f} L/min in this system. A speed controller or valve would be needed to hold the requested flow.")

with st.container(horizontal=True):
    st.metric("Desired velocity", f"{desired.velocity_m_s:.3f} m/s", border=True)
    st.metric("Desired Reynolds number", f"{desired.reynolds_number:,.0f}", border=True)
    st.metric("Desired friction factor (Darcy)", f"{desired.friction_factor:.4f}", border=True)
    st.metric("Desired TDH", f"{desired.total_dynamic_head_m:.2f} m", border=True)

st.subheader("Desired-flow calculation")
st.dataframe({"Quantity": ["Pipe friction loss", "Minor loss", "Static head", "Hydraulic power", "Ideal transfer time"],
              "Value": [f"{desired.pipe_head_loss_m:.3f} m", f"{desired.minor_head_loss_m:.3f} m", f"{desired.static_head_m:.3f} m", f"{desired.hydraulic_power_w:.1f} W", f"{transfer_time_seconds(volume_l / 1000, desired_q) / 60:.1f} min"]},
             hide_index=True, width="stretch", alt="Hydraulic losses, head, power, and ideal transfer time at the requested flow")

st.subheader("Interactive pump and system curves")
st.caption("Hover for exact values; drag to zoom, use the slider below the chart to pan, and use the chart tools to reset. Changing desired flow moves the requested-condition point; changing pipe, elevation, fittings, or temperature changes the system curve.")
flows = np.linspace(pump.min_flow_m3_s, pump.max_flow_m3_s, 201)
curve_data = [{"Flow (L/min)": float(q * 60_000), "Pump head (m)": float(pump.head_m(float(q))),
               "System head (m)": float(calculate_hydraulics(config, float(q)).total_dynamic_head_m)} for q in flows]
series = [
    {"name": "Illustrative pump curve", "type": "line", "showSymbol": False, "encode": {"x": "Flow (L/min)", "y": "Pump head (m)"}},
    {"name": "System curve", "type": "line", "showSymbol": False, "encode": {"x": "Flow (L/min)", "y": "System head (m)"}},
]
if pump.min_flow_m3_s <= desired_q <= pump.max_flow_m3_s:
    series.append({"name": "Requested condition", "type": "scatter", "symbol": "diamond", "symbolSize": 11,
                   "data": [[float(desired_lpm), float(desired.total_dynamic_head_m)]]})
if point:
    series.append({"name": "Operating point", "type": "scatter", "symbolSize": 11,
                   "data": [[float(point.flow_m3_s * 60_000), float(point.head_m)]]})

st.echarts_chart({
    "dataset": {"source": curve_data}, "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
    "legend": {"top": 4}, "grid": {"left": 72, "right": 24, "top": 52, "bottom": 92},
    "xAxis": {"type": "value", "name": "Flow (L/min)", "nameLocation": "middle", "nameGap": 32},
    "yAxis": {"type": "value", "name": "Head (m)", "nameLocation": "middle", "nameGap": 48, "min": 0},
    "dataZoom": [{"type": "inside"}, {"type": "slider", "bottom": 15}],
    "toolbox": {"feature": {"dataZoom": {}, "restore": {}, "saveAsImage": {}}}, "series": series,
}, key="pump_system_curve", height=500, alt="Pump head and required system head versus flow, with requested and operating points")
st.caption("Pump-type caveat: these are synthetic teaching curves. Real diaphragm-pump performance depends on air supply, fluid properties, stroke settings, and the specific model. Import a manufacturer curve before equipment selection.")
st.caption("Model limitations: constant tank elevations and flow; no pump efficiency, NPSH, transients, leaks, or non-water fluids.")
