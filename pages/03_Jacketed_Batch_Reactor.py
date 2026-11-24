from html import escape
from math import ceil
from pathlib import Path
from time import monotonic, sleep

import pandas as pd
import streamlit as st

from phone_layout import phone_view, settings_panel, thermal_display
from reactor_diagram import render_reactor_diagram
from reactor_loop import LoopInput, advance, fluid_properties, initial_state, reading
from reactor_trend import build_temperature_trend
from reactor_utility import UtilitySettings
from trend_history import TemperatureSample, record_temperature

st.set_page_config(page_title="Batch Reactor Sim 02", layout="wide", initial_sidebar_state="auto")
st.html(Path(__file__).with_name("operator_view.css"))

compact = phone_view()
if compact:
    st.title("Jacketed batch reactor")
with settings_panel("Jacket and batch settings", compact):
    st.header("Jacket fluid")
    name = st.selectbox(
        "Jacket fluid",
        ["Propylene glycol / water", "Ethylene glycol / water", "Polydimethylsiloxane (PDMS) thermal fluid"],
        label_visibility="collapsed",
    )
    concentration = None if name.startswith("Poly") else st.selectbox("Glycol concentration (% v/v)", [20, 30, 40, 50, 60], index=1, help="Concentration changes properties and freeze protection.")
    fluid = fluid_properties(name, concentration)
    fluid_panel = st.expander("Fluid properties", expanded=False)
    st.header("Jacket loop")
    flow_col, hold_col = st.columns(2)
    flow = flow_col.number_input("Flow (L/min)", .1, 200., 12.)
    hold = hold_col.number_input("Hold-up (L)", .1, 100., 8.)
    ua_col, mode_col = st.columns(2)
    jua = ua_col.number_input(
        "Jacket UA (W/K)", 0., 10000., 450.,
        help="Reference value at 20 °C. The model reduces jacket heat transfer as the coolant properties change.",
    )
    jacket_control = mode_col.selectbox(
        "Jacket control", ("Manual", "Thermostat"),
        help="Manual circulates at the TIC-201 inlet command while running. Thermostat uses the reactor setpoint to gate circulation.",
    )
    with st.expander("Jacket temperature limits"):
        lo_col, hi_col = st.columns(2)
        lo_lo = lo_col.number_input("Lo Lo (°C)", -50., 99.5, -20., step=.5)
        hi_hi = hi_col.number_input("Hi Hi (°C)", -49.5, 100., 100., step=.5)
        st.caption("The selected fluid can raise the minimum inlet command.")
    utility_panel = st.expander("Heater and chiller")
    with utility_panel:
        heating_kw = st.number_input(
            "Heater maximum (kW)", 0., 100., 3., step=.1,
            help="Maximum thermal power delivered to the jacket coolant.",
        )
        st.markdown("**Chiller capacity points**")
        rating_temp_col, rating_kw_col = st.columns(2)
        rated_temp_c = rating_temp_col.number_input("Rated at (°C)", -49., 100., 20., step=1.)
        rated_cooling_kw = rating_kw_col.number_input("Rated cooling (kW)", 0., 100., 2., step=.1)
        cold_temp_col, cold_kw_col = st.columns(2)
        cold_temp_c = cold_temp_col.number_input("Cold point (°C)", -50., 99., -20., step=1.)
        cold_cooling_kw = cold_kw_col.number_input(
            "Cold capacity (kW)", 0., 100., .8, step=.1,
            help="Cooling capacity at the cold temperature, at or below rated cooling capacity.",
        )
    st.header("Batch and ambient")
    volume_col, initial_col = st.columns(2)
    water = volume_col.number_input("Water volume (L)", 1., 1000., 60.)
    initial = initial_col.number_input("Initial water (°C)", 0., 100., 20.)
    ambient_col, loss_col = st.columns(2)
    ambient = ambient_col.number_input("Ambient (°C)", -40., 100., 20.)
    aua = loss_col.number_input("Loss UA (W/K)", 0., 1000., 12.)
    setpoint = st.number_input(
        "Reactor setpoint (°C)", -20., 150., 40.,
        help="Used in Thermostat mode.",
    )
    with st.expander("Load cells"):
        tare_kg = st.number_input(
            "Vessel tare (kg)", 0., 2000., 40., step=1., format="%.1f",
            help="Illustrative empty-batch baseline for the vessel, mounted hardware and charged jacket.",
        )

try:
    utility = UtilitySettings(
        heating_kw=heating_kw, rated_temp_c=rated_temp_c, rated_cooling_kw=rated_cooling_kw,
        cold_temp_c=cold_temp_c, cold_cooling_kw=cold_cooling_kw,
    )
except ValueError as exc:
    st.session_state.playing, st.session_state.player_clock = False, None
    st.error(f"Check the heater and chiller settings. {exc}")
    st.stop()

with utility_panel:
    curve = pd.DataFrame({
        "Coolant (°C)": [cold_temp_c, rated_temp_c],
        "Capacity (kW)": [cold_cooling_kw, rated_cooling_kw],
    })
    st.line_chart(curve, x="Coolant (°C)", y="Capacity (kW)", height=150)
    st.caption("The model interpolates between these points and uses the nearest rating outside them.")

fluid_floor = ceil(fluid.minimum_liquid_c * 2) / 2
inlet_floor = max(lo_lo, fluid_floor)
if inlet_floor >= hi_hi:
    st.session_state.playing, st.session_state.player_clock = False, None
    st.error(f"Hi Hi must be above the effective jacket minimum of {inlet_floor:g} °C.")
    st.stop()

for key, value in (("tic_201_setpoint", 38.0), ("m_201_setpoint", 200)):
    if key not in st.session_state:
        st.session_state[key] = value
inlet = min(hi_hi, max(inlet_floor, float(st.session_state.tic_201_setpoint)))
if inlet != st.session_state.tic_201_setpoint:
    st.session_state.tic_201_setpoint = inlet
rpm = int(st.session_state.m_201_setpoint)
cfg = LoopInput(
    fluid=fluid, inlet_c=inlet, flow_l_min=flow, hold_up_l=hold, jacket_ua_w_k=jua,
    ambient_c=ambient, ambient_ua_w_k=aua, water_l=water, initial_water_c=initial,
    setpoint_c=setpoint if jacket_control == "Thermostat" else None,
    utility=utility,
)
SIM_SECONDS_PER_SECOND = 180


def reset_process():
    st.session_state.loop_state = initial_state(cfg)
    st.session_state.loop_config = cfg
    st.session_state.temperature_history = []
    st.session_state.trend_full_run = False
    st.session_state.playing, st.session_state.player_clock = False, None


def toggle_trend_view():
    st.session_state.trend_full_run = not st.session_state.get("trend_full_run", False)


# Physical configuration changes start a fresh batch. Control commands act on the live temperatures.
static_key = ("capacity_limited_supply", fluid, flow, hold, jua, ambient, aua, water, initial)
if st.session_state.get("plant_config") != static_key or "loop_state" not in st.session_state:
    st.session_state.plant_config = static_key
    reset_process()
if st.session_state.playing:
    now = monotonic()
    # Limit catch-up after a browser suspension. The elapsed interval belongs to the prior command.
    elapsed = min(now - st.session_state.player_clock, 5.0) * SIM_SECONDS_PER_SECOND
    previous_config = st.session_state.loop_config
    state = advance(previous_config, st.session_state.loop_state, elapsed)
    st.session_state.loop_state = state
    st.session_state.player_clock = now
st.session_state.loop_config = cfg
snapshot = reading(cfg, st.session_state.loop_state)
fluid_label = name + (f" · {concentration}%" if concentration is not None else "")
phase_limit = snapshot.phase_limit
if phase_limit:
    st.session_state.playing, st.session_state.player_clock = False, None

with st.container(key="run_controls"):
    controls = st.columns([1, 1, 1, 4])
    if controls[0].button("Start", disabled=bool(phase_limit) or st.session_state.playing, use_container_width=True):
        st.session_state.playing, st.session_state.player_clock = True, monotonic()
    stopped = controls[1].button("Stop", disabled=not st.session_state.playing, use_container_width=True)
    if stopped:
        st.session_state.playing, st.session_state.player_clock = False, None
    if controls[2].button("Reset", use_container_width=True):
        reset_process()
        snapshot = reading(cfg, st.session_state.loop_state)
        phase_limit = snapshot.phase_limit
    status = f"Stopped at water {phase_limit} limit" if phase_limit else (
        "Process running" if st.session_state.playing else "Process stopped"
    )
    controls[3].html(
        '<div class="run-context">'
        f'<p class="run-state" data-limit="{str(bool(phase_limit)).lower()}">{status}</p>'
        f'<p class="run-fluid">{escape(fluid_label)}</p>'
        '</div>'
    )

# Reserve the phone diagram next to playback before rendering the setpoint controls.
phone_overview = st.container(key="phone_overview") if compact else None
with st.container(border=True, key="scada_commands"):
    tic_col, motor_col, signal_col = st.columns([3, 3, 2])
    tic_col.html(
        '<span class="command-label">TIC-201 · Jacket inlet setpoint</span>'
        f'<strong class="command-value">{inlet:.1f} °C</strong>'
    )
    tic_col.slider(
        "Jacket inlet setpoint (°C)", inlet_floor, hi_hi,
        step=.5, key="tic_201_setpoint", label_visibility="collapsed",
    )
    motor_col.html(
        '<span class="command-label">M-201 · Agitator setpoint</span>'
        f'<strong class="command-value">{rpm} RPM</strong>'
    )
    motor_col.slider(
        "Agitator setpoint (RPM)", 0, 600, step=25,
        key="m_201_setpoint", label_visibility="collapsed",
    )
    command_ma = 4 + 16 * (inlet - lo_lo) / (hi_hi - lo_lo)
    band = "LOW" if inlet < 10 else "HIGH" if inlet > 45 else "NORMAL"
    signal_col.html(
        '<span class="command-label">AO-201 · Simulated output</span>'
        f'<strong class="command-value">{command_ma:.1f} mA</strong>'
        f'<span class="operating-band" data-band="{band.lower()}">{band.title()} command band</span>'
    )
    limits = f"Jacket limits · LL {lo_lo:g} °C · HH {hi_hi:g} °C"
    if inlet_floor > lo_lo:
        limits += f" · Fluid minimum {inlet_floor:g} °C"
    active = st.session_state.playing
    utility_duty_kw = snapshot.utility_duty_w / 1000 if active else 0.0
    cooling_available_kw = utility.cooling_capacity_kw(snapshot.inlet_c)
    if utility_duty_kw >= .005:
        utility_status = f"Heater {utility_duty_kw:.2f} kW"
    elif utility_duty_kw <= -.005:
        utility_status = f"Chiller {-utility_duty_kw:.2f} kW"
    else:
        utility_status = "Utility idle"
    if active and snapshot.utility_limited:
        utility_status += " · At capacity"
    utility_status += f" · Cooling available {cooling_available_kw:.2f} kW"
    st.html(
        '<div class="operating-summary">'
        f'<p class="operating-envelope">{limits}</p>'
        f'<p class="operating-envelope">{utility_status}</p></div>'
    )

with fluid_panel:
    properties = fluid.at_temperature(snapshot.outlet_c)
    st.write(
        f"At jacket bulk temperature **{snapshot.outlet_c:.1f} °C**\n\n"
        f"Density: {properties.density:.1f} kg/m³\n\n"
        f"Specific heat: {properties.cp:,.0f} J/kg·K\n\n"
        f"Conductivity: {properties.conductivity:.3f} W/m·K\n\n"
        f"Dynamic viscosity: {properties.viscosity * 1000:.2f} mPa·s "
        f"({fluid.viscosity * 1000:.2f} mPa·s at 20 °C)\n\n"
        f"Lowest liquid-model inlet command: {fluid_floor:g} °C."
    )
    st.caption(fluid.note)

batch_mass_kg = cfg.batch_mass_kg
gross_mass_kg = tare_kg + batch_mass_kg
sample = TemperatureSample(
    time_s=st.session_state.loop_state.time_s,
    water_c=snapshot.water_c,
    inlet_c=inlet,
    outlet_c=snapshot.outlet_c,
    reactor_target_c=cfg.setpoint_c,
    batch_mass_kg=batch_mass_kg,
    gross_mass_kg=gross_mass_kg,
)
history = record_temperature(
    st.session_state.get("temperature_history", []), sample, force=stopped or bool(phase_limit),
)
st.session_state.temperature_history = history

duty_w = snapshot.duty_w if st.session_state.playing else 0.0
direction = "Heating" if duty_w > 1 else "Cooling" if duty_w < -1 else "Idle"
narrow_readings = (
    ("Jacket inlet", f"{snapshot.inlet_c:.1f} °C"),
    ("Jacket outlet", f"{snapshot.outlet_c:.1f} °C"),
    ("TT-201 · Water", f"{snapshot.water_c:.1f} °C"),
    ("Batch duty", f"{duty_w:+.0f} W" if direction != "Idle" else "0 W"),
    ("Net batch mass", f"{batch_mass_kg:,.1f} kg"),
    ("Gross vessel mass", f"{gross_mass_kg:,.1f} kg"),
)

# The liquid level uses the prior simulator's 118 L vessel capacity as a visual basis.
VESSEL_CAPACITY_L = 118.0
if compact:
    with phone_overview:
        thermal_display(water_l=water, capacity_l=VESSEL_CAPACITY_L, temp_c=snapshot.water_c,
                        first=("Jacket inlet", f"{snapshot.inlet_c:.1f} °C"),
                        second=("Jacket outlet", f"{snapshot.outlet_c:.1f} °C"))
with st.container(key="process_overview"):
    if not compact:
        diagram = render_reactor_diagram(
            inlet_c=snapshot.inlet_c,
            outlet_c=snapshot.outlet_c,
            water_c=snapshot.water_c,
            water_l=water,
            capacity_l=VESSEL_CAPACITY_L,
            duty_w=duty_w,
            ambient_w=snapshot.heat_loss_w,
            rpm=rpm,
            playing=st.session_state.playing,
            circulating=snapshot.circulating,
            batch_mass_kg=batch_mass_kg,
            gross_mass_kg=gross_mass_kg,
        )
        st.markdown(f'<div>{" ".join(line.strip() for line in diagram.splitlines())}</div>', unsafe_allow_html=True)
    entries = "".join(
        f"<div><dt>{label}</dt><dd>{escape(value)}</dd></div>" for label, value in (narrow_readings[3:] if compact else narrow_readings)
    )
    st.html(f'<dl class="operator-readings" aria-label="Live readings">{entries}</dl>')

with st.container(key="temperature_trend"):
    heading_col, zoom_col, trace_col = st.columns([4, 1, 1], vertical_alignment="center")
    heading_col.markdown("#### Batch trend")
    full_run = st.session_state.get("trend_full_run", False)
    zoom_col.button(
        "Recent view" if full_run else "Full run",
        key="trend_zoom", on_click=toggle_trend_view,
    )
    with trace_col.popover("Traces"):
        show_outlet = st.checkbox(
            "Show jacket outlet", help="Include the jacket outlet temperature in the trend.",
        )
        show_mass = st.checkbox(
            "Show batch mass", value=True, help="Plot net water mass on the right-hand kg scale.",
        )
    displayed = history if history[-1] == sample else [*history, sample]
    chart = build_temperature_trend(
        pd.DataFrame(displayed), show_outlet=show_outlet, full_run=full_run, show_mass=show_mass, compact=compact,
    )
    st.vega_lite_chart(spec=chart, use_container_width=True)

with st.expander("Model notes and future scope", expanded=False):
    st.write("WT-201 represents the summed load cells. Gross mass includes the configured vessel tare. "
             "Net batch mass stays constant throughout a closed heating or cooling run.")
    st.write("This educational simulator models sensible heat transfer. "
             "TIC-201 commands the jacket supply. The heater or chiller conditions the coolant, "
             "and its thermal capacity and the jacket return load affect how quickly the inlet responds. "
             "The model assumes a 20 L supply buffer and starts the coolant at ambient within the fluid limits. "
             "The 4–20 mA output is simulated. The 118 L vessel basis is illustrative.")
    st.markdown("Heater capacity is thermal power added to the coolant. Chiller capacity is thermal "
                "power removed at the current coolant supply temperature. Batch duty measures the "
                "heat crossing the jacket wall. The editable default curve is illustrative. "
                "[Example of published ratings at several coolant temperatures](https://www.julabo.com/en-gb/products/recirculating-coolers/fl-recirculating-coolers/fl4006)")
    st.write("The glycol/water command floor includes a 3 °C freeze margin and stays within "
             "the property table. The run halts at 0 °C or 100 °C if the next step would cross "
             "the liquid-water boundary. The model uses a coolant-film correction for heat transfer "
             "at the commanded flow rate.")
    st.markdown("Dow lists about −18 °C as the lower end of its typical DOWFROST use range. "
                "The simulator can represent tabulated liquid properties at −20 °C where the mixture permits. "
                "[Dow product specifications](https://www.dow.com/en-us/pdp.dowfrost-heat-transfer-fluid.23545z.html)")
    st.markdown("[Dow DOWFROST engineering data](https://ingredi.com/content/pdfs/DOWFROST_Manual.pdf) "
                "· [Dow DOWTHERM SR-1 engineering data](https://www.magnumsolvent.com/productdata/Product%20Literature/Heat%20Transfer%20Fluids/Engineering%20%26%20Operating%20Guide%20-%20DOWTHERM%20SR-1.pdf)")
    st.write("Moving dashes show circulation. Green means the actual jacket inlet is warmer than the reactor "
             "water, and blue means it is cooler. Batch duty shows the heat transfer from the jacket "
             "fluid already in the jacket, which takes time to respond to a new inlet command.")
    st.write("Future scope includes utility valves, probes, PLC hardware, "
             "pump head/transfers, boiling/freezing, and latent heat.")
if st.session_state.playing:
    sleep(.35)
    (st.rerun if hasattr(st, "rerun") else st.experimental_rerun)()
