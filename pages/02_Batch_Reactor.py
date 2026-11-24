"""Operator view for Simulator 002."""
from time import monotonic

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from phone_layout import phone_view, settings_panel, thermal_display
from biotech_foundry.batch_reactor.model import BatchReactor, Equipment, Vessel, Water
from biotech_foundry.batch_reactor.schematic import reactor_schematic
from biotech_foundry.batch_reactor.solver import SolverSettings, simulate


st.set_page_config(page_title="Biotech Foundry | Batch Reactor", layout="wide")
compact = phone_view()
st.title("Water heating" if compact else "Water Heating Simulation - Batch Reactor")

TANK_SIZES = {
    "Current tank — 118 L": {"diameter_m": 0.50, "height_m": 0.60},
    "Wide production tank — 265 L": {"diameter_m": 0.75, "height_m": 0.60},
    "Tall pilot tank — 147 L": {"diameter_m": 0.50, "height_m": 0.75},
}


@st.cache_data(show_spinner=False)
def run_batch(reactor, settings):
    return simulate(reactor, settings)


with settings_panel("Batch settings", compact):
    if not compact:
        st.header("Batch settings")
    with st.form("batch_settings"):
        tank_name = st.selectbox("Tank size", list(TANK_SIZES))
        tank = TANK_SIZES[tank_name]
        geometric_capacity_l = np.pi * (tank["diameter_m"] / 2) ** 2 * tank["height_m"] * 1000
        st.caption(f"Vessel capacity: {geometric_capacity_l:.0f} L · {tank['diameter_m']:.2f} m diameter × {tank['height_m']:.2f} m straight side")
        volume_l = st.number_input("Working water volume (L)", 1.0, 1_000.0, 60.0, step=1.0)
        initial_c = st.number_input("Initial water temperature (°C)", 0.0, 100.0, 20.0)
        ambient_c = st.number_input("Ambient temperature (°C)", -40.0, 100.0, 20.0)
        ua = st.number_input("Ambient heat loss UA (W/K)", min_value=0.0, value=12.0)
        rated_w = st.number_input("Rated electrical heater (W)", min_value=0.0, value=1500.0)
        heater_pct = st.slider("Heater output (%)", 0, 100, 100)
        efficiency_pct = st.slider("Heater efficiency (%)", 0, 100, 85)
        rpm = st.number_input("Agitation setpoint (RPM)", min_value=0, value=200, step=25)
        duration_min = st.number_input("Batch duration (min)", 1, 1440, 180)
        setpoint_c = st.number_input("Temperature setpoint (°C)", 2.0, 98.0, 40.0, step=0.5)
        st.caption("The heater restarts 2 °C below the setpoint and stops 2 °C above it.")
        shutoff = st.checkbox("Schedule final heater shutoff")
        cutoff_min = st.number_input("Shutoff time (min)", 1, 1440, 90)
        st.form_submit_button("Apply settings", width="stretch")

if volume_l > geometric_capacity_l:
    st.error(
        f"{volume_l:g} L of working water does not fit the selected {tank_name} "
        f"({geometric_capacity_l:.0f} L capacity). Select a larger tank or reduce the working water volume."
    )
    st.stop()

reactor = BatchReactor(
    vessel=Vessel(diameter_m=tank["diameter_m"], height_m=tank["height_m"], working_volume_m3=volume_l / 1000),
    water=Water(initial_temperature_k=initial_c + 273.15),
    equipment=Equipment(
        heater_rated_w=rated_w,
        heater_fraction=heater_pct / 100,
        heater_efficiency=efficiency_pct / 100,
        agitation_rpm=rpm,
        heater_off_s=cutoff_min * 60 if shutoff else None,
        temperature_setpoint_k=setpoint_c + 273.15,
    ),
    ambient_temperature_k=ambient_c + 273.15,
    ua_w_k=ua,
)
settings = SolverSettings(duration_s=duration_min * 60)
try:
    result = run_batch(reactor, settings)
except (RuntimeError, ValueError) as error:
    st.error(f"Unable to run this batch: {error} Select a larger tank or reduce the working water volume.")
    st.stop()

state = st.session_state
if state.get("reactor_config") != (reactor, settings):
    state.reactor_config = (reactor, settings)
    state.reactor_elapsed = 0.0
    state.reactor_clock = None

trend_data = pd.DataFrame({
    "Batch time (min)": result.time_s / 60,
    "Temperature (°C)": result.temperature_k - 273.15,
})
trend_line = alt.Chart(trend_data).mark_line(color="#38bdf8").encode(
    x="Batch time (min):Q", y=alt.Y("Temperature (°C):Q", scale=alt.Scale(zero=False)),
    tooltip=["Batch time (min):Q", "Temperature (°C):Q"],
)


def play():
    if state.reactor_elapsed >= settings.duration_s:
        state.reactor_elapsed = 0.0
    state.reactor_clock = monotonic()


def pause():
    state.reactor_clock = None


def reset():
    pause()
    state.reactor_elapsed = 0.0


def seek():
    pause()
    state.reactor_elapsed = state.reactor_seek_min * 60


@st.fragment(run_every=0.5)
def operator_view():
    if state.reactor_clock is not None:
        now = monotonic()
        state.reactor_elapsed = min(
            settings.duration_s, state.reactor_elapsed + (now - state.reactor_clock) * 120
        )
        state.reactor_clock = now if state.reactor_elapsed < settings.duration_s else None
    playing = state.reactor_clock is not None
    index = int(np.searchsorted(result.time_s, state.reactor_elapsed, side="right") - 1)
    batch_min = result.time_s[index] / 60
    measured_c = result.measured_k[index] - 273.15
    heater_w = result.heater_power_w[index]
    loss_w = result.heat_loss_w[index]
    phase = "Batch complete" if state.reactor_elapsed >= settings.duration_s else (
        "Heating" if heater_w > 0 else "Heater off"
    )

    with st.container(key="phone_transport"):
        play_col, pause_col, reset_col, status_col = st.columns([1, 1, 1, 5], vertical_alignment="center")
        play_col.button("Play", icon=":material/play_arrow:", on_click=play, disabled=playing)
        pause_col.button("Pause", icon=":material/pause:", on_click=pause, disabled=not playing)
        reset_col.button("Reset", icon=":material/restart_alt:", on_click=reset)
        status_col.caption(f"{phase} · {batch_min:.1f} / {duration_min} min · playback 120×")

    state.reactor_seek_min = int(state.reactor_elapsed / 30) / 2
    st.slider("Batch position (min)", 0.0, float(duration_min), step=0.5,
              key="reactor_seek_min", on_change=seek, disabled=playing)

    if compact:
        thermal_display(water_l=volume_l, capacity_l=geometric_capacity_l, temp_c=measured_c,
                        first=("Heat to water", f"{heater_w:,.0f} W"),
                        second=("Ambient heat loss", f"{loss_w:,.0f} W"))
    else:
        # An iframe isolates SVG/CSS from host-page sanitization and renders across hosted Streamlit runtimes.
        components.html(reactor_schematic(reactor, measured_c, heater_w, loss_w, playing=playing), height=420, scrolling=False)
        st.caption("Green marks energized equipment. Blue dashes show the instrument signal. Amber dashes show modeled heat exchange. Impeller motion illustrates the RPM setpoint.")
    with st.container(key="phone_metrics"):
        metrics = st.columns(4)
        metrics[0].metric("TT-201 · Water", f"{measured_c:.1f} °C", border=True)
        metrics[1].metric("EH-201 · Delivered heat", f"{heater_w:,.0f} W", border=True)
        metrics[2].metric("M-201 · Setpoint", f"{rpm:,.0f} RPM", border=True)
        metrics[3].metric("Heater energy to water", f"{result.heater_energy_j[index] / 3.6e6:.2f} kWh", border=True)

    st.subheader("Temperature trend")
    st.caption(f"Setpoint {setpoint_c:g} °C · Heater on at {setpoint_c - 2:g} °C · "
               f"Heater off at {setpoint_c + 2:g} °C")
    band_lines = alt.Chart(pd.DataFrame({
        "Temperature (°C)": [setpoint_c - 2, setpoint_c, setpoint_c + 2],
    })).mark_rule(color="#64748b", strokeDash=[4, 4], opacity=0.65).encode(y="Temperature (°C):Q")
    cursor = alt.Chart(pd.DataFrame({"Batch time (min)": [batch_min]})).mark_rule(
        color="#fbbf68", strokeDash=[4, 4],
    ).encode(x="Batch time (min):Q")
    st.altair_chart((band_lines + trend_line + cursor).properties(height=215), width="stretch")
    if measured_c <= 0 or measured_c >= 100:
        st.warning("The prediction has reached the atmospheric liquid-water boundary. The model excludes freezing and boiling.")


operator_view()
