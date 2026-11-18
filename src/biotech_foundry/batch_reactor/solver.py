"""Integrate the thermal balance and cumulative energy over heater phases."""
from dataclasses import dataclass
from math import log, log1p

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from .instrumentation import IdealTemperatureSensor, TemperatureSensor
from .model import BatchReactor, bounded


@dataclass(frozen=True)
class SolverSettings:
    duration_s: float = 7200.0
    sample_interval_s: float = 30.0
    rtol: float = 1e-8
    atol: float = 1e-8

    def __post_init__(self):
        bounded("duration_s", self.duration_s, 0, float("inf"), strict=True)
        bounded("sample_interval_s", self.sample_interval_s, 0, float("inf"), strict=True)
        if self.duration_s / self.sample_interval_s > 1_000_000:
            raise ValueError("Use a larger sample_interval_s to keep output within one million intervals.")
        bounded("rtol", self.rtol, 100 * np.finfo(float).eps, 1)
        bounded("atol", self.atol, 0, float("inf"), strict=True)


@dataclass(frozen=True)
class SimulationResult:
    time_s: NDArray
    temperature_k: NDArray
    measured_k: NDArray
    heater_power_w: NDArray
    heat_loss_w: NDArray
    heater_energy_j: NDArray
    heat_lost_j: NDArray
    energy_residual_j: NDArray
    electrical_energy_j: float
    target_k: float | None
    target_time_s: float | None


def _phase_target_time(reactor, initial_k, target_k, power_w):
    delta_k = target_k - initial_k
    if delta_k == 0:
        return 0.0
    net_w = power_w - reactor.heat_loss_w(initial_k)
    if net_w == 0 or (delta_k > 0) != (net_w > 0):
        return None

    capacitance = reactor.thermal_capacitance_j_k
    ua = reactor.ua_w_k
    linear_time = (delta_k / net_w) * capacitance
    if ua == 0:
        return linear_time
    remaining_w = power_w - reactor.heat_loss_w(target_k)
    if remaining_w == 0 or (remaining_w > 0) != (net_w > 0):
        return None
    fraction = ua * (delta_k / net_w)
    if fraction < 0.5:
        return linear_time if fraction == 0 else linear_time * (-log1p(-fraction) / fraction)
    return (capacitance / ua) * (log(abs(net_w)) - log(abs(remaining_w)))


def simulate(
    reactor: BatchReactor,
    settings: SolverSettings = SolverSettings(),
    *,
    sensor: TemperatureSensor | None = None,
    target_k: float | None = None,
) -> SimulationResult:
    if target_k is not None:
        bounded("target_k", target_k, 273.15, 373.15)
    duration = settings.duration_s
    equipment = reactor.equipment
    times = np.arange(0, duration, settings.sample_interval_s, dtype=float)
    times = np.append(times[times < duration], duration)
    cutoff = equipment.heater_off_s if equipment.heater_off_s is not None else float("inf")
    band = equipment.thermostat_band_k
    initial_k = reactor.water.initial_temperature_k
    heating = equipment.heating_power_w > 0 and (band is None or initial_k < band[1])
    state = [0.0, 0.0]
    samples = []
    target_time = None
    active_s = 0.0
    start = 0.0
    sample_start = 0
    while start < duration:
        if len(samples) >= 100_000:
            raise RuntimeError("Too many heater switches. Check the heater sizing and thermal settings.")
        power = equipment.heating_power_w if heating else 0.0
        end = min(duration, cutoff) if start < cutoff else duration
        switching = False
        if band is not None and start < cutoff and equipment.heating_power_w > 0:
            threshold = band[1] if heating else band[0]
            crossing = _phase_target_time(reactor, initial_k + state[0], threshold, power)
            if crossing is not None and crossing <= end - start:
                end = start + crossing
                switching = True
        if end <= start:
            raise RuntimeError("Heater switching exceeds numerical time resolution.")
        next_heating = end < cutoff and (not heating if switching else heating)
        if target_k is not None and target_time is None:
            hit = _phase_target_time(reactor, initial_k + state[0], target_k, power)
            if hit is not None and hit <= end - start:
                target_time = start + hit

        def rhs(_time, values):
            loss = reactor.heat_loss_w(initial_k + values[0])
            return [reactor.temperature_rate_k_s(power, loss), loss]

        solution = solve_ivp(
            rhs, (start, end), state, dense_output=True,
            rtol=settings.rtol, atol=settings.atol,
        )
        if not solution.success:
            raise RuntimeError(f"Thermal integration failed: {solution.message}")
        final_phase = end == duration
        sample_end = np.searchsorted(times, end, side="right" if final_phase else "left")
        phase_times = times[sample_start:sample_end]
        if phase_times.size == 0 or phase_times[0] != start:
            phase_times = np.insert(phase_times, 0, start)
        temperature_change, phase_loss = solution.sol(phase_times)
        phase_power = np.full_like(phase_times, power)
        if final_phase:
            phase_power[-1] = equipment.heating_power_w if next_heating else 0.0
        phase_active_s = active_s + (phase_times - start) * heating
        samples.append(np.stack((
            phase_times, initial_k + temperature_change, phase_loss, phase_power,
            equipment.heating_power_w * phase_active_s,
        )))
        active_s += (end - start) * heating
        state = solution.y[:, -1]
        start = end
        sample_start = sample_end
        heating = next_heating

    times, temperature, heat_lost, power, heater_energy = np.concatenate(samples, axis=1)
    stored_energy = reactor.thermal_capacitance_j_k * (temperature - initial_k)
    sensor = IdealTemperatureSensor() if sensor is None else sensor
    measured = np.asarray(sensor.measure(times.copy(), temperature.copy()), dtype=float)
    if measured.shape != temperature.shape or not np.all(np.isfinite(measured)):
        raise ValueError("Temperature sensor must return one finite value per sample.")
    return SimulationResult(
        times, temperature, measured, power, reactor.heat_loss_w(temperature),
        heater_energy, heat_lost, heater_energy - heat_lost - stored_energy,
        equipment.electrical_power_w * active_s, target_k, target_time,
    )
