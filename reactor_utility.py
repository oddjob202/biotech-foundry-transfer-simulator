"""Illustrative thermal ratings for a recirculating heater and chiller."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class UtilitySettings:
    heating_kw: float = 3.0
    rated_temp_c: float = 20.0
    rated_cooling_kw: float = 2.0
    cold_temp_c: float = -20.0
    cold_cooling_kw: float = 0.8

    def __post_init__(self):
        values = (self.heating_kw, self.rated_temp_c, self.rated_cooling_kw,
                  self.cold_temp_c, self.cold_cooling_kw)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not isfinite(value) for value in values):
            raise ValueError("Utility ratings and rating temperatures must be finite numbers.")
        if min(self.heating_kw, self.rated_cooling_kw, self.cold_cooling_kw) < 0:
            raise ValueError("Heating and cooling capacities must be non-negative.")
        if self.cold_temp_c >= self.rated_temp_c:
            raise ValueError("Cold-point temperature must be below the rated temperature.")
        if self.cold_cooling_kw > self.rated_cooling_kw:
            raise ValueError("Cold-point cooling capacity must not exceed the rated capacity.")

    def cooling_capacity_kw(self, temp_c: float) -> float:
        """Interpolate between rated temperatures and hold both endpoints flat."""
        fraction = (temp_c - self.cold_temp_c) / (self.rated_temp_c - self.cold_temp_c)
        fraction = min(1.0, max(0.0, fraction))
        return self.cold_cooling_kw + fraction * (self.rated_cooling_kw - self.cold_cooling_kw)

    def limit_duty_w(self, requested_w: float, passive_inlet_c: float, gain_c_w: float) -> float:
        """Limit signed utility duty at the resulting coolant temperature."""
        if requested_w >= 0:
            return min(requested_w, self.heating_kw * 1000)

        cold_w = self.cold_cooling_kw * 1000
        rated_w = self.rated_cooling_kw * 1000
        if passive_inlet_c - gain_c_w * cold_w <= self.cold_temp_c:
            available_w = cold_w
        elif passive_inlet_c - gain_c_w * rated_w >= self.rated_temp_c:
            available_w = rated_w
        else:
            slope = (rated_w - cold_w) / (self.rated_temp_c - self.cold_temp_c)
            # At saturation, solve P = capacity(T_passive - gain * P).
            available_w = (
                (cold_w + slope * (passive_inlet_c - self.cold_temp_c))
                / (1 + gain_c_w * slope)
            )
        return max(requested_w, -available_w)
