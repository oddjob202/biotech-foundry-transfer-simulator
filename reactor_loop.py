"""Educational sensible-only batch-reactor jacket model (SI units internally)."""
from dataclasses import dataclass
from math import expm1, isfinite
from typing import Optional

import numpy as np

from reactor_fluids import Fluid, fluid_properties
from reactor_utility import UtilitySettings


SUPPLY_RESERVOIR_L = 20.0


def _positive(name, value, *, zero=False):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or value < 0 or (not zero and value == 0):
        raise ValueError(f"{name} must be a finite {'non-negative' if zero else 'positive'} number.")


@dataclass(frozen=True)
class LoopInput:
    fluid: Fluid
    inlet_c: float = 38.0
    flow_l_min: float = 12.0
    hold_up_l: float = 8.0
    jacket_ua_w_k: float = 450.0
    ambient_c: float = 20.0
    ambient_ua_w_k: float = 12.0
    water_l: float = 60.0
    initial_water_c: float = 20.0
    setpoint_c: Optional[float] = 40.0
    supply_tau_s: float = 300.0
    utility: Optional[UtilitySettings] = None

    def __post_init__(self):
        for name in ("flow_l_min", "hold_up_l", "jacket_ua_w_k", "water_l"):
            _positive(name, getattr(self, name), zero=name in {"jacket_ua_w_k"})
        _positive("ambient_ua_w_k", self.ambient_ua_w_k, zero=True)
        _positive("supply_tau_s", self.supply_tau_s, zero=True)
        if not isfinite(self.inlet_c) or not self.fluid.minimum_liquid_c <= self.inlet_c <= 100:
            raise ValueError("Inlet command must be within the modeled liquid-fluid range.")
        if not isfinite(self.initial_water_c) or not 0 <= self.initial_water_c <= 100:
            raise ValueError("Initial batch water must be between 0 and 100 °C.")

    @property
    def flow_capacity_w_k(self): return self.flow_l_min / 60000 * self.fluid.density * self.fluid.cp
    @property
    def jacket_capacity_j_k(self): return self.hold_up_l / 1000 * self.fluid.density * self.fluid.cp
    @property
    def supply_capacity_j_k(self):
        return SUPPLY_RESERVOIR_L / 1000 * self.fluid.density * self.fluid.cp

    @property
    def batch_mass_kg(self):
        return self.water_l / 1000 * 997.0

    @property
    def batch_capacity_j_k(self):
        return self.batch_mass_kg * 4180.0


@dataclass(frozen=True)
class Result:
    time_s: np.ndarray; water_c: np.ndarray; jacket_c: np.ndarray; duty_w: np.ndarray; outlet_c: np.ndarray; heat_loss_w: np.ndarray; circulating: np.ndarray; jacket_energy_j: np.ndarray; loss_energy_j: np.ndarray; residual_j: np.ndarray


@dataclass(frozen=True)
class LoopState:
    time_s: float
    water_c: float
    jacket_c: float
    circulating: bool = False
    thermostat_direction: int = 0
    jacket_energy_j: float = 0.0
    loss_energy_j: float = 0.0
    inlet_c: Optional[float] = None
    phase_limit: Optional[str] = None
    utility_duty_w: float = 0.0
    utility_limited: bool = False
    utility_energy_j: float = 0.0


@dataclass(frozen=True)
class LoopReading:
    water_c: float
    outlet_c: float
    duty_w: float
    heat_loss_w: float
    circulating: bool
    inlet_c: float
    phase_limit: Optional[str]
    utility_duty_w: float = 0.0
    utility_limited: bool = False


def initial_state(config: LoopInput) -> LoopState:
    fluid_c = config.inlet_c
    if config.utility is not None:
        fluid_c = min(100.0, max(config.fluid.minimum_liquid_c, config.ambient_c))
    return LoopState(
        time_s=0.0, water_c=config.initial_water_c, jacket_c=fluid_c,
        inlet_c=fluid_c,
    )


def _actual_inlet(config, state):
    return config.inlet_c if state.inlet_c is None else state.inlet_c


def _jacket_ua(config, film_props):
    # An illustrative film correction at fixed volumetric flow. Scaling the
    # jacket film alone assumes it contributes half of nominal thermal resistance.
    # The powers reflect a turbulent-film trend, not a pump or jacket sizing model.
    ref = config.fluid
    film_factor = min(1.0, (film_props.density / ref.density) ** 0.8
                      * (film_props.cp / ref.cp) ** 0.4
                      * (film_props.conductivity / ref.conductivity) ** 0.6
                      * (ref.viscosity / film_props.viscosity) ** 0.4)
    return config.jacket_ua_w_k / (0.5 + 0.5 / film_factor)


def reading(config: LoopInput, state: LoopState) -> LoopReading:
    inlet_c = _actual_inlet(config, state)
    film_props = config.fluid.at_temperature((inlet_c + state.jacket_c) / 2.0)
    return LoopReading(
        water_c=state.water_c,
        outlet_c=state.jacket_c,
        duty_w=_jacket_ua(config, film_props) * (state.jacket_c - state.water_c) if state.circulating else 0.0,
        heat_loss_w=config.ambient_ua_w_k * (state.water_c - config.ambient_c),
        circulating=state.circulating,
        inlet_c=inlet_c,
        phase_limit=state.phase_limit,
        utility_duty_w=state.utility_duty_w,
        utility_limited=state.utility_limited,
    )


def _thermostat_direction(config: LoopInput, water_c: float, inlet_c: float, previous_direction: int) -> int:
    low = config.setpoint_c - 2
    high = config.setpoint_c + 2
    if min(config.inlet_c, inlet_c) > water_c and (water_c <= low or (previous_direction == 1 and water_c < high)):
        return 1
    if max(config.inlet_c, inlet_c) < water_c and (water_c >= high or (previous_direction == -1 and water_c > low)):
        return -1
    return 0


def advance(config: LoopInput, state: LoopState, elapsed_s: float) -> LoopState:
    """Advance the current temperatures under the supplied inlet command.

    Manual mode (no reactor setpoint) circulates throughout the advance.
    Thermostat mode uses a ±2 °C band and only calls for circulation if the
    selected inlet can heat or cool the batch in the requested direction.
    The supply follows its command with a first-order lag subject to the
    selected heater and chiller ratings. The model stops at a liquid-water
    phase boundary.
    """
    _positive("elapsed_s", elapsed_s, zero=True)
    if elapsed_s == 0 or state.phase_limit is not None:
        return state

    water_c, jacket_c = state.water_c, state.jacket_c
    inlet_c = _actual_inlet(config, state)
    jacket_energy, lost_energy = state.jacket_energy_j, state.loss_energy_j
    utility_energy = state.utility_energy_j
    direction = state.thermostat_direction
    batch_capacity = config.batch_capacity_j_k
    volume_flow = config.flow_l_min / 60000
    jacket_volume = config.hold_up_l / 1000
    supply_capacity = config.supply_capacity_j_k
    utility = config.utility
    ambient_ua = config.ambient_ua_w_k
    manual = config.setpoint_c is None
    remaining = elapsed_s
    phase_limit = None
    utility_duty = 0.0
    utility_limited = False

    while remaining > 0:
        dt = min(1.0, remaining)
        old_water, old_jacket, old_inlet = water_c, jacket_c, inlet_c
        response = 1.0 if config.supply_tau_s == 0 else -expm1(-dt / config.supply_tau_s)
        requested_inlet_c = inlet_c + (config.inlet_c - inlet_c) * response
        if utility is None:
            inlet_c = requested_inlet_c
        direction = 0 if manual else _thermostat_direction(config, water_c, inlet_c, direction)
        circulating = manual or direction != 0
        duty = 0.0
        ua, flow_capacity, jacket_capacity = 0.0, 0.0, config.jacket_capacity_j_k
        if circulating:
            film_props = config.fluid.at_temperature((inlet_c + jacket_c) / 2.0)
            bulk_props = config.fluid.at_temperature(jacket_c)
            ua = _jacket_ua(config, film_props)
            jacket_capacity = jacket_volume * bulk_props.density * bulk_props.cp
            flow_capacity = volume_flow * film_props.density * film_props.cp

        # Backward Euler keeps the coupled heat exchange stable for small hold-up.
        # With a utility, coolant leaves the supply reservoir and returns from the
        # jacket. Both balances use the same flow-capacity term.
        jacket_duty = ua * (jacket_c - water_c)
        a = 1 + dt * (ua + ambient_ua) / batch_capacity
        b = dt * ua / batch_capacity
        c = dt * ua / jacket_capacity
        d = 1 + dt * (ua + flow_capacity) / jacket_capacity
        water_rhs = dt * (jacket_duty - ambient_ua * (water_c - config.ambient_c)) / batch_capacity
        jacket_rhs = dt * (flow_capacity * (inlet_c - jacket_c) - jacket_duty) / jacket_capacity
        if utility is not None:
            # Solve first for the passive supply response and the gain from each
            # applied watt. Demand offsets return load and moves toward the setpoint.
            e = dt * flow_capacity / jacket_capacity
            f = dt * flow_capacity / supply_capacity
            jacket_pivot = d - c * b / a
            passive_jacket_delta = (jacket_rhs + c * water_rhs / a) / jacket_pivot
            supply_pivot = 1 + f - f * e / jacket_pivot
            passive_inlet_delta = f * (jacket_c - inlet_c + passive_jacket_delta) / supply_pivot
            inlet_gain = dt / supply_capacity / supply_pivot
            passive_inlet_c = inlet_c + passive_inlet_delta
            demand = (requested_inlet_c - passive_inlet_c) / inlet_gain
            utility_duty = utility.limit_duty_w(demand, passive_inlet_c, inlet_gain)
            utility_limited = abs(demand - utility_duty) > 1e-6
            inlet_delta = passive_inlet_delta + inlet_gain * utility_duty
            inlet_c += inlet_delta
            jacket_rhs += e * inlet_delta

        if circulating:
            determinant = a * d - b * c
            water_c += (d * water_rhs + b * jacket_rhs) / determinant
            jacket_c += (c * water_rhs + a * jacket_rhs) / determinant
            duty = ua * (jacket_c - water_c)
        else:
            ambient_fraction = dt * ambient_ua / batch_capacity
            water_c += (config.ambient_c - water_c) * ambient_fraction / (1 + ambient_fraction)
        loss = ambient_ua * (water_c - config.ambient_c)
        if not 0 <= water_c <= 100:
            boundary = 0.0 if water_c < 0 else 100.0
            fraction = (boundary - old_water) / (water_c - old_water)
            dt *= fraction
            water_c = boundary
            jacket_c = old_jacket + fraction * (jacket_c - old_jacket)
            inlet_c = old_inlet + fraction * (inlet_c - old_inlet)
            phase_limit = "freezing" if boundary == 0 else "boiling"
            circulating = False
        jacket_energy += dt * duty
        lost_energy += dt * loss
        utility_energy += dt * utility_duty
        remaining -= dt
        if phase_limit is not None:
            break

    return LoopState(
        time_s=state.time_s + elapsed_s - remaining,
        water_c=water_c,
        jacket_c=jacket_c,
        circulating=circulating,
        thermostat_direction=direction,
        jacket_energy_j=jacket_energy,
        loss_energy_j=lost_energy,
        inlet_c=inlet_c,
        phase_limit=phase_limit,
        utility_duty_w=utility_duty if phase_limit is None else 0.0,
        utility_limited=utility_limited if phase_limit is None else False,
        utility_energy_j=utility_energy,
    )


def simulate(config: LoopInput, duration_min=180, sample_s=30) -> Result:
    """Sample a constant-command run of the perfectly mixed jacket and batch."""
    _positive("duration_min", duration_min)
    _positive("sample_s", sample_s)
    duration_s = duration_min * 60
    times = np.append(np.arange(0, duration_s, sample_s, dtype=float), duration_s)
    water = np.empty(len(times))
    jacket = np.empty_like(water)
    duty = np.empty_like(water)
    loss = np.empty_like(water)
    circulating = np.empty(len(times), dtype=bool)
    jacket_energy = np.empty_like(water)
    lost_energy = np.empty_like(water)
    state = initial_state(config)
    for i, target in enumerate(times):
        elapsed_s = float(target - times[i - 1]) if i > 0 else 0.0
        state = advance(config, state, elapsed_s)
        sample = reading(config, state)
        water[i] = sample.water_c
        jacket[i] = sample.outlet_c
        duty[i] = sample.duty_w
        loss[i] = sample.heat_loss_w
        circulating[i] = sample.circulating
        jacket_energy[i] = state.jacket_energy_j
        lost_energy[i] = state.loss_energy_j
        if state.phase_limit is not None:
            times[i] = state.time_s
            break

    sample_slice = slice(i + 1)
    times, water, jacket, duty, loss, circulating, jacket_energy, lost_energy = (
        values[sample_slice] for values in (
            times, water, jacket, duty, loss, circulating, jacket_energy, lost_energy,
        )
    )
    stored = config.batch_capacity_j_k * (water - config.initial_water_c)
    return Result(
        time_s=times,
        water_c=water,
        jacket_c=jacket,
        duty_w=duty,
        outlet_c=jacket.copy(),
        heat_loss_w=loss,
        circulating=circulating,
        jacket_energy_j=jacket_energy,
        loss_energy_j=lost_energy,
        residual_j=jacket_energy - lost_energy - stored,
    )
