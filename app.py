"""Streamlit dashboard for the iteration-1 water-transfer simulator."""
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

from biotech_foundry.hydraulics import HydraulicInputError, SystemConfiguration, calculate_hydraulics, transfer_time_seconds
from biotech_foundry.pumps import IllustrativeCentrifugalPump, find_operating_point

st.set_page_config(page_title="Biotech Foundry | Hydraulic Transfer", layout="wide")
st.title("The Biotech Foundry — Hydraulic Transfer Simulator")
st.caption("Iteration 1: steady water transfer between open atmospheric tanks. Pump curve is illustrative, not manufacturer data.")

with st.sidebar:
    st.header("Piping and tanks")
    diameter_mm = st.number_input("Pipe internal diameter (mm)", min_value=0.1, value=25.0)
    length_m = st.number_input("Pipe length (m)", min_value=0.0, value=20.0)
    roughness_mm = st.number_input("Absolute roughness (mm)", min_value=0.0, value=0.045, format="%.4f")
    temperature_c = st.number_input("Water temperature (°C)", min_value=0.0, max_value=100.0, value=20.0)
    source_m = st.number_input("Source water-surface elevation (m)", value=0.0)
    destination_m = st.number_input("Destination water-surface elevation (m)", value=8.0)
    minor_k = st.number_input("Total fitting loss coefficient, ΣK", min_value=0.0, value=4.0)
    st.header("Transfer")
    desired_lpm = st.number_input("Desired flow (L/min)", min_value=0.01, value=60.0)
    volume_l = st.number_input("Transfer volume (L)", min_value=0.01, value=500.0)
    st.selectbox("Pump selection", ["Illustrative centrifugal pump (synthetic)"])

config = SystemConfiguration(diameter_mm / 1000, length_m, roughness_mm / 1000, temperature_c, source_m, destination_m, minor_k)
pump = IllustrativeCentrifugalPump()
desired_q = desired_lpm / 1000 / 60

try:
    desired = calculate_hydraulics(config, desired_q)
    point = find_operating_point(pump, config)
except HydraulicInputError as exc:
    st.error(str(exc))
    st.stop()

if point is None:
    st.warning("No valid pump/system operating point exists inside the illustrative pump curve range.")
else:
    operating = calculate_hydraulics(config, point.flow_m3_s)
    if abs(point.flow_m3_s - desired_q) / desired_q > 0.05:
        st.info(f"The selected pump's operating flow is {point.flow_m3_s * 60_000:.1f} L/min, not the requested setpoint.")

cols = st.columns(4)
cols[0].metric("Desired velocity", f"{desired.velocity_m_s:.3f} m/s")
cols[1].metric("Desired Reynolds number", f"{desired.reynolds_number:,.0f}")
cols[2].metric("Desired friction factor (Darcy)", f"{desired.friction_factor:.4f}")
cols[3].metric("Desired TDH", f"{desired.total_dynamic_head_m:.2f} m")

st.subheader("Desired-flow calculation")
st.dataframe({"Quantity": ["Pipe friction loss", "Minor loss", "Static head", "Hydraulic power", "Ideal transfer time"],
              "Value": [f"{desired.pipe_head_loss_m:.3f} m", f"{desired.minor_head_loss_m:.3f} m", f"{desired.static_head_m:.3f} m", f"{desired.hydraulic_power_w:.1f} W", f"{transfer_time_seconds(volume_l / 1000, desired_q) / 60:.1f} min"]}, hide_index=True, use_container_width=True)

st.subheader("Pump and system curves")
flows = np.linspace(pump.min_flow_m3_s, pump.max_flow_m3_s, 200)
system_heads = [calculate_hydraulics(config, float(q)).total_dynamic_head_m for q in flows]
fig, ax = plt.subplots()
ax.plot(flows * 60_000, [pump.head_m(float(q)) for q in flows], label="Illustrative pump curve")
ax.plot(flows * 60_000, system_heads, label="System curve")
if point:
    ax.scatter([point.flow_m3_s * 60_000], [point.head_m], color="crimson", zorder=3, label="Operating point")
ax.set(xlabel="Flow (L/min)", ylabel="Head (m)", ylim=(0, None))
ax.grid(alpha=.3); ax.legend()
st.pyplot(fig, use_container_width=True)
st.caption("Limitations: constant tank elevations and flow; no pump efficiency, NPSH, transients, leaks, non-water fluids, or positive-displacement pump behavior.")
