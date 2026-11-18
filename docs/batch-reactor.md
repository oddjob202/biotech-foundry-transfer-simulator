# Simulator 002 — Water-filled batch reactor

Estimate water heat-up, passive cooldown, energy demand, and time to a temperature target in a mechanically agitated batch vessel. The heater can run at fixed output or cycle around a temperature setpoint. An optional scheduled shutoff ends heating for the rest of the batch. A virtual sensor reports a separate measurement series. The simulator produces four time-series plots and a numerical summary.

## Run on macOS Apple Silicon

Use the repository's Python 3.13 environment. From the repository root:

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m biotech_foundry.batch_reactor --config examples/batch-reactor.json --plot /tmp/batch-reactor.png
python -m pytest
```

Omit `--config` for a two-hour heat-up demonstration. The JSON example heats a 60 L batch for 90 minutes and then allows 90 minutes of passive cooldown. The example's target is 40 °C. The four plot panels show water temperature, effective heater power, signed ambient loss, and true versus measured temperature. The terminal summary includes temperatures, geometry, equipment settings, energy totals, the peak energy-balance residual, and the first target crossing if it occurs during the configured run. The default plot path is `batch-reactor.png` in the current directory.

## Operator view

With the same environment active, run `python -m streamlit run app.py` and select **Batch Reactor** in the sidebar. The **Apply settings** button loads the scenario at time zero. Use **Play**, **Pause**, and **Reset**, or drag **Batch position** while paused. Playback runs at 120× simulated time.

The vessel fill follows the working volume. Green identifies the energized heater and agitator. The dashed blue line links the virtual temperature probe to TT-201. Amber arrows show the direction of modeled ambient heat exchange. The trend shows the run trajectory with a cursor at the current playback time. The impeller animation illustrates the RPM setpoint. The default temperature setpoint is 40 °C, with heater shutoff at 42 °C and restart at 38 °C. Apply a new setpoint to start a fresh run. The trend marks the setpoint and both switching thresholds.

## Parameters and units

JSON fields may be omitted to use defaults. The model uses SI units, with RPM retained as the operator-facing agitation setpoint. Use kelvins in the input file and add 273.15 to a temperature given in °C. Use cubic meters for volume and divide liters by 1,000.

| Group | Field | Meaning |
| --- | --- | --- |
| Vessel | `diameter_m`, `height_m` | Internal cylinder dimensions in m |
| Vessel | `working_volume_m3`, `maximum_capacity_m3` | Fixed liquid volume and optional capacity in m³. The geometric capacity applies when the configured capacity is omitted or null. |
| Water | `density_kg_m3`, `specific_heat_j_kg_k`, `initial_temperature_k` | Constant density, constant heat capacity, and initial liquid temperature |
| Equipment | `heater_rated_w`, `heater_fraction`, `heater_efficiency` | Rated electrical power in W, operating fraction from 0 to 1, and fraction of electrical input transferred to water from 0 to 1 |
| Equipment | `agitation_rpm`, `heater_off_s` | Recorded agitation setpoint and optional shutoff time in s. A shutoff at the end or later removes no energy during the run. |
| Equipment | `temperature_setpoint_k` | Optional thermostat setpoint in K. Heating switches off at setpoint +2 K and restarts at setpoint −2 K. |
| Thermal | `ambient_temperature_k`, `ua_w_k` | Fixed ambient temperature in K and effective total heat-loss conductance in W/K |
| Target | `target_k` | Optional exact temperature to cross in either direction, in K. An initial match counts at 0 s. An equilibrium approached asymptotically has no finite crossing. |
| Solver | `duration_s`, `sample_interval_s`, `rtol`, `atol` | Run duration and requested output interval in s, with relative and absolute integration tolerances. Absolute tolerance applies to the numeric state values in K and J. |

## Physical model

The rigid, vertical cylinder has cross-sectional area `A = πD²/4`, geometric capacity `AH`, liquid height `h = V/A`, and wetted wall plus bottom area `A + πDh`. Working volume must be positive and within the configured vessel capacity, which must fit inside the cylinder. The liquid mass is `m = ρV`.

The water is well mixed with a uniform temperature and constant properties. The surroundings have a fixed temperature. The liquid energy balance is

```text
m Cp dT/dt = Qheater - Qloss
Qelectrical = rated power × operating fraction
Qheater = Qelectrical × heater efficiency
Qloss = UA × (T - Tambient)
```

UA is the effective conductance of all modeled paths between the water and ambient. It is an aggregate fixed input for the specified fill and insulation. The reported wetted area is geometric information. Changing the fill or dimensions requires reviewing the configured UA. When ambient is warmer than water, signed loss is negative and represents heat entering the batch. With UA above zero and fixed heater power, the equilibrium is `Tambient + Qheater/UA` and the time constant is `m Cp/UA`. At UA zero, constant power produces a linear temperature rise.

SciPy `solve_ivp` uses adaptive RK45 over each constant-power phase and integrates temperature change and cumulative signed heat loss. Output includes the initial time, final time, and any in-run heater shutoff. Output samples do not set integration steps. Heater power at the shutoff sample is zero. Delivered heater energy is computed from active time and power. The residual is delivered energy minus signed ambient loss minus the change in stored energy. Target times use the constant-power analytical crossing equation within each phase, with the integrated state providing the initial temperature of the cooldown phase.

With a setpoint configured, the thermostat uses the modeled water temperature. At startup the heater is enabled below the upper threshold. After a switch, it holds that state until the opposite threshold is reached. Threshold times are computed from the constant-power thermal balance, and each switch starts a new integration phase. The scheduled shutoff takes priority. Cooldown is passive and depends on the ambient temperature and UA. If the water never cools to the lower threshold, the heater stays off.

## Verification and physical limits

Automated checks cover geometry, mass, invalid inputs, adiabatic heating and no-change cases, ambient heat gain and cooldown, equilibrium, target timing, shutoff, energy closure, tolerance stability, and the temperature sensor interface. The shutoff benchmark checks a peak residual below 1 µJ and agreement with tighter solver tolerances within 1 µK and 0.1 J for temperature and cumulative loss. These thresholds apply to the software benchmark.

The results are theoretical predictions. This model has no experimental validation. The default water properties, heater efficiency, and UA are illustrative assumptions. Agitation is a recorded setpoint and the model assumes ideal mixing even at zero RPM. Equipment thermal mass, stratification, evaporation, freezing, boiling, reactions, and biological processes are outside this model. A run reaching the atmospheric water phase boundaries is flagged in the summary. Heat transfer, efficiency, and material limits require measurements before using these predictions for equipment selection.

## Engineering decisions

| Decision | Basis |
| --- | --- |
| Place the batch model in a sibling package under `biotech_foundry`. | Preserve the Hydraulic Transfer entry point and keep reactor physics, instrumentation, plotting, and reporting independently callable. |
| Specify UA and heater efficiency independently. | Aggregate ambient loss and effective heater input require different measurements. The hydraulic tank geometry uses capacity and base elevation, while the batch model needs cylinder height and wetted area. |
| Integrate each heater phase separately. | Preserve the exact shutoff time and continuity of temperature and energy across the power step. |
| Use an ideal sensor behind a measurement interface. | Keep predictions and instrument readings distinct and leave room for later sensor response. |

The next engineering decision is how to identify UA and heater efficiency separately on a water-only prototype. Plan a passive cooldown trial at known fill and measured ambient temperature to estimate UA, then use a measured electrical heat-up trial at the same fill to estimate heater efficiency. Compare predicted and measured temperature trajectories before adding active cooling or temperature control. Later work can add vessel thermal mass, geometry-dependent heat transfer, sensor dynamics, mixing correlations, and inlet and outlet balances for water-based continuous flow. Simulator 001 can supply hydraulic calculations where its assumptions apply.
