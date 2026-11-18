"""Configuration and physical balances for a fully mixed water batch."""
from dataclasses import dataclass, field
from math import isfinite, pi


def bounded(name: str, value: float, low: float, high: float, *, strict=False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) or not low <= value <= high
            or (strict and value == low)):
        lower = "greater than" if strict else "at least"
        raise ValueError(f"{name} must be finite, {lower} {low}, and at most {high}.")


@dataclass(frozen=True)
class Vessel:
    diameter_m: float = 0.5
    height_m: float = 0.6
    working_volume_m3: float = 0.060
    maximum_capacity_m3: float | None = None

    def __post_init__(self):
        bounded("diameter_m", self.diameter_m, 0, float("inf"), strict=True)
        bounded("height_m", self.height_m, 0, float("inf"), strict=True)
        bounded("geometric capacity", self.geometric_capacity_m3, 0, float("inf"), strict=True)
        bounded("maximum_capacity_m3", self.capacity_m3, 0, self.geometric_capacity_m3, strict=True)
        bounded("working_volume_m3", self.working_volume_m3, 0, self.capacity_m3, strict=True)

    @property
    def cross_section_m2(self):
        return pi * self.diameter_m * (self.diameter_m / 4)

    @property
    def geometric_capacity_m3(self):
        return self.cross_section_m2 * self.height_m

    @property
    def capacity_m3(self):
        return self.geometric_capacity_m3 if self.maximum_capacity_m3 is None else self.maximum_capacity_m3

    @property
    def liquid_height_m(self):
        return self.working_volume_m3 / self.cross_section_m2

    @property
    def wetted_area_m2(self):
        return self.cross_section_m2 + pi * self.diameter_m * self.liquid_height_m


@dataclass(frozen=True)
class Water:
    density_kg_m3: float = 997.0
    specific_heat_j_kg_k: float = 4180.0
    initial_temperature_k: float = 293.15

    def __post_init__(self):
        bounded("density_kg_m3", self.density_kg_m3, 0, float("inf"), strict=True)
        bounded("specific_heat_j_kg_k", self.specific_heat_j_kg_k, 0, float("inf"), strict=True)
        bounded("initial_temperature_k", self.initial_temperature_k, 273.15, 373.15)


@dataclass(frozen=True)
class Equipment:
    heater_rated_w: float = 1500.0
    heater_fraction: float = 1.0
    heater_efficiency: float = 0.85
    agitation_rpm: float = 200.0
    heater_off_s: float | None = None

    def __post_init__(self):
        bounded("heater_rated_w", self.heater_rated_w, 0, float("inf"))
        bounded("heater_fraction", self.heater_fraction, 0, 1)
        bounded("heater_efficiency", self.heater_efficiency, 0, 1)
        bounded("agitation_rpm", self.agitation_rpm, 0, float("inf"))
        if self.heater_off_s is not None:
            bounded("heater_off_s", self.heater_off_s, 0, float("inf"), strict=True)

    @property
    def electrical_power_w(self):
        return self.heater_rated_w * self.heater_fraction

    @property
    def heating_power_w(self):
        return self.electrical_power_w * self.heater_efficiency


@dataclass(frozen=True)
class BatchReactor:
    vessel: Vessel = field(default_factory=Vessel)
    water: Water = field(default_factory=Water)
    equipment: Equipment = field(default_factory=Equipment)
    ambient_temperature_k: float = 293.15
    ua_w_k: float = 12.0

    def __post_init__(self):
        bounded("ambient_temperature_k", self.ambient_temperature_k, 0, float("inf"), strict=True)
        bounded("ua_w_k", self.ua_w_k, 0, float("inf"))
        bounded("water mass", self.mass_kg, 0, float("inf"), strict=True)
        bounded("thermal capacitance", self.thermal_capacitance_j_k, 0, float("inf"), strict=True)

    @property
    def mass_kg(self):
        return self.water.density_kg_m3 * self.vessel.working_volume_m3

    @property
    def thermal_capacitance_j_k(self):
        return self.mass_kg * self.water.specific_heat_j_kg_k

    def heat_loss_w(self, temperature_k):
        return self.ua_w_k * (temperature_k - self.ambient_temperature_k)

    def temperature_rate_k_s(self, heating_power_w, heat_loss_w):
        return (heating_power_w - heat_loss_w) / self.thermal_capacitance_j_k
