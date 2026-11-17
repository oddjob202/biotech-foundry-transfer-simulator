"""Pure hydraulic calculations using SI units internally."""
from __future__ import annotations

from dataclasses import dataclass
from math import exp, pi

GRAVITY_M_S2 = 9.80665


class HydraulicInputError(ValueError):
    """Raised when input lies outside this iteration's physical model."""


@dataclass(frozen=True)
class SystemConfiguration:
    diameter_m: float
    length_m: float
    roughness_m: float
    temperature_c: float
    source_elevation_m: float
    destination_elevation_m: float
    minor_loss_k: float = 0.0

    def validate(self) -> None:
        if self.diameter_m <= 0 or self.length_m < 0 or self.roughness_m < 0:
            raise HydraulicInputError("Diameter must be positive; length and roughness cannot be negative.")
        if not 0.0 <= self.temperature_c <= 100.0:
            raise HydraulicInputError("Water-property approximation is supported only from 0 to 100 °C.")
        if self.minor_loss_k < 0:
            raise HydraulicInputError("The summed minor-loss coefficient cannot be negative.")


@dataclass(frozen=True)
class HydraulicResult:
    flow_m3_s: float
    area_m2: float
    velocity_m_s: float
    density_kg_m3: float
    viscosity_pa_s: float
    reynolds_number: float
    friction_factor: float
    pipe_head_loss_m: float
    minor_head_loss_m: float
    static_head_m: float
    total_dynamic_head_m: float
    hydraulic_power_w: float


def water_properties(temperature_c: float) -> tuple[float, float]:
    """Return density (kg/m³) and dynamic viscosity (Pa·s), valid 0–100 °C.

    Density is the Kell pure-water correlation; viscosity uses the common
    Andrade-type correlation (temperature in kelvin). Both are adequate for
    engineering estimates of clean liquid water, not aqueous media or slurries.
    """
    if not 0.0 <= temperature_c <= 100.0:
        raise HydraulicInputError("Water-property approximation is supported only from 0 to 100 °C.")
    t = temperature_c
    density = 1000.0 * (1 - ((t + 288.9414) / (508929.2 * (t + 68.12963))) * (t - 3.9863) ** 2)
    viscosity = 2.414e-5 * 10 ** (247.8 / (t + 133.15))
    return density, viscosity


def pipe_area(diameter_m: float) -> float:
    if diameter_m <= 0:
        raise HydraulicInputError("Pipe diameter must be positive.")
    return pi * diameter_m**2 / 4.0


def flow_to_velocity(flow_m3_s: float, diameter_m: float) -> float:
    if flow_m3_s < 0:
        raise HydraulicInputError("Reverse flow is outside the iteration-1 model.")
    return flow_m3_s / pipe_area(diameter_m)


def reynolds_number(density_kg_m3: float, velocity_m_s: float, diameter_m: float, viscosity_pa_s: float) -> float:
    return density_kg_m3 * velocity_m_s * diameter_m / viscosity_pa_s


def friction_factor(reynolds: float, relative_roughness: float) -> float:
    """Darcy friction factor: laminar, linearly blended transition, Colebrook turbulent."""
    if reynolds < 0 or relative_roughness < 0:
        raise HydraulicInputError("Reynolds number and relative roughness cannot be negative.")
    if reynolds == 0:
        return 0.0
    laminar = 64.0 / reynolds
    if reynolds <= 2300.0:
        return laminar

    # Fixed-point form of Colebrook; converges quickly over this water-piping range.
    f = 0.02
    # Avoid a scipy dependency in the numerical engine for this scalar iteration.
    from math import log10
    for _ in range(50):
        next_f = 1.0 / (-2.0 * log10(relative_roughness / 3.7 + 2.51 / (reynolds * f**0.5))) ** 2
        if abs(next_f - f) < 1e-12:
            f = next_f
            break
        f = next_f
    if reynolds >= 4000.0:
        return f
    turbulent_at_4000 = friction_factor(4000.0, relative_roughness)
    blend = (reynolds - 2300.0) / 1700.0
    return laminar * (1.0 - blend) + turbulent_at_4000 * blend


def calculate_hydraulics(config: SystemConfiguration, flow_m3_s: float) -> HydraulicResult:
    config.validate()
    velocity = flow_to_velocity(flow_m3_s, config.diameter_m)
    density, viscosity = water_properties(config.temperature_c)
    reynolds = reynolds_number(density, velocity, config.diameter_m, viscosity)
    ff = friction_factor(reynolds, config.roughness_m / config.diameter_m)
    velocity_head = velocity**2 / (2.0 * GRAVITY_M_S2)
    pipe_loss = ff * (config.length_m / config.diameter_m) * velocity_head
    minor_loss = config.minor_loss_k * velocity_head
    static_head = config.destination_elevation_m - config.source_elevation_m
    total_head = static_head + pipe_loss + minor_loss
    return HydraulicResult(flow_m3_s, pipe_area(config.diameter_m), velocity, density, viscosity, reynolds, ff,
                           pipe_loss, minor_loss, static_head, total_head,
                           density * GRAVITY_M_S2 * flow_m3_s * total_head)


def transfer_time_seconds(volume_m3: float, flow_m3_s: float) -> float:
    if volume_m3 <= 0 or flow_m3_s <= 0:
        raise HydraulicInputError("Transfer volume and flow must be positive.")
    return volume_m3 / flow_m3_s
