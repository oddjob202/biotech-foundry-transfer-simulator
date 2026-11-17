"""Pump interface and operating-point solver."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy.optimize import brentq

from .hydraulics import HydraulicInputError, SystemConfiguration, calculate_hydraulics


class PumpModel(Protocol):
    name: str
    min_flow_m3_s: float
    max_flow_m3_s: float

    def head_m(self, flow_m3_s: float) -> float: ...


@dataclass(frozen=True)
class IllustrativeCentrifugalPump:
    """Synthetic 30 m shutoff / 180 L/min zero-head curve; not manufacturer data."""
    name: str = "Illustrative centrifugal pump (synthetic)"
    min_flow_m3_s: float = 0.0
    max_flow_m3_s: float = 180.0 / 1000.0 / 60.0
    shutoff_head_m: float = 30.0

    def head_m(self, flow_m3_s: float) -> float:
        if not self.min_flow_m3_s <= flow_m3_s <= self.max_flow_m3_s:
            raise HydraulicInputError("Flow is outside the documented illustrative pump curve range.")
        return self.shutoff_head_m * (1.0 - (flow_m3_s / self.max_flow_m3_s) ** 2)


@dataclass(frozen=True)
class IllustrativeDiaphragmPump:
    """Synthetic AODD-style curve; a real AODD curve also depends on air supply.

    This represents the broad behavior of a hygienic air-operated double-diaphragm
    transfer pump, not a specific manufacturer's product or performance curve.
    """
    name: str = "Illustrative hygienic diaphragm pump (synthetic)"
    min_flow_m3_s: float = 0.0
    max_flow_m3_s: float = 120.0 / 1000.0 / 60.0
    shutoff_head_m: float = 42.0

    def head_m(self, flow_m3_s: float) -> float:
        if not self.min_flow_m3_s <= flow_m3_s <= self.max_flow_m3_s:
            raise HydraulicInputError("Flow is outside the documented illustrative pump curve range.")
        return self.shutoff_head_m * (1.0 - (flow_m3_s / self.max_flow_m3_s) ** 1.35)


@dataclass(frozen=True)
class IllustrativePeristalticPump:
    """Synthetic peristaltic-pump envelope; not a manufacturer performance curve."""
    name: str = "Illustrative hygienic peristaltic pump (synthetic)"
    min_flow_m3_s: float = 0.0
    max_flow_m3_s: float = 35.0 / 1000.0 / 60.0
    shutoff_head_m: float = 35.0

    def head_m(self, flow_m3_s: float) -> float:
        if not self.min_flow_m3_s <= flow_m3_s <= self.max_flow_m3_s:
            raise HydraulicInputError("Flow is outside the documented illustrative pump curve range.")
        return self.shutoff_head_m * (1.0 - (flow_m3_s / self.max_flow_m3_s) ** 2.2)


def pump_catalog() -> dict[str, PumpModel]:
    """Return the built-in illustrative pump options keyed by UI label."""
    pumps: list[PumpModel] = [
        IllustrativeCentrifugalPump(),
        IllustrativeDiaphragmPump(),
        IllustrativePeristalticPump(),
    ]
    return {pump.name: pump for pump in pumps}


@dataclass(frozen=True)
class OperatingPoint:
    flow_m3_s: float
    head_m: float


def find_operating_point(pump: PumpModel, config: SystemConfiguration) -> OperatingPoint | None:
    """Find a pump/system intersection, without extrapolating either curve."""
    config.validate()
    def residual(q: float) -> float:
        return pump.head_m(q) - calculate_hydraulics(config, q).total_dynamic_head_m

    grid = np.linspace(pump.min_flow_m3_s, pump.max_flow_m3_s, 301)
    values = [residual(float(q)) for q in grid]
    for left, right, f_left, f_right in zip(grid[:-1], grid[1:], values[:-1], values[1:]):
        if f_left == 0:
            root = float(left)
        elif f_left * f_right <= 0:
            root = float(brentq(residual, float(left), float(right)))
        else:
            continue
        head = pump.head_m(root)
        if head >= 0:
            return OperatingPoint(root, head)
    if values[-1] == 0:
        return OperatingPoint(float(grid[-1]), pump.head_m(float(grid[-1])))
    return None
