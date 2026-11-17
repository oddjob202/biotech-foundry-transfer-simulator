"""Time-stepped transfer simulation for two open cylindrical tanks."""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import pi

from .hydraulics import HydraulicInputError, SystemConfiguration
from .pumps import OperatingPoint, PumpModel, find_operating_point


@dataclass(frozen=True)
class CylindricalTank:
    """A vertical, open cylindrical tank with a fixed base elevation."""
    diameter_m: float
    capacity_m3: float
    base_elevation_m: float

    def validate(self) -> None:
        if self.diameter_m <= 0 or self.capacity_m3 <= 0:
            raise HydraulicInputError("Tank diameter and capacity must be positive.")

    @property
    def cross_section_area_m2(self) -> float:
        self.validate()
        return pi * self.diameter_m**2 / 4.0

    def surface_elevation_m(self, volume_m3: float) -> float:
        self.validate()
        if not 0 <= volume_m3 <= self.capacity_m3:
            raise HydraulicInputError("Tank volume must stay between zero and tank capacity.")
        return self.base_elevation_m + volume_m3 / self.cross_section_area_m2


@dataclass(frozen=True)
class TransferState:
    source_volume_m3: float
    destination_volume_m3: float
    elapsed_s: float = 0.0
    last_flow_m3_s: float = 0.0
    status: str = "Ready"


def operating_point_at_state(
    base_config: SystemConfiguration,
    source_tank: CylindricalTank,
    destination_tank: CylindricalTank,
    state: TransferState,
    pump: PumpModel,
) -> OperatingPoint | None:
    """Return the pump operating point after updating water-surface elevations."""
    dynamic_config = replace(
        base_config,
        source_elevation_m=source_tank.surface_elevation_m(state.source_volume_m3),
        destination_elevation_m=destination_tank.surface_elevation_m(state.destination_volume_m3),
    )
    return find_operating_point(pump, dynamic_config)


def advance_transfer(
    base_config: SystemConfiguration,
    source_tank: CylindricalTank,
    destination_tank: CylindricalTank,
    state: TransferState,
    pump: PumpModel,
    step_s: float,
) -> TransferState:
    """Advance a pump-driven transfer one explicit time step, conserving volume."""
    if step_s <= 0:
        raise HydraulicInputError("Simulation time step must be positive.")
    if state.source_volume_m3 <= 0:
        return replace(state, status="Source tank empty", last_flow_m3_s=0.0)
    if state.destination_volume_m3 >= destination_tank.capacity_m3:
        return replace(state, status="Destination tank full", last_flow_m3_s=0.0)
    point = operating_point_at_state(base_config, source_tank, destination_tank, state, pump)
    if point is None or point.flow_m3_s <= 0:
        return replace(state, status="No valid pump operating point", last_flow_m3_s=0.0)

    transferable = min(
        point.flow_m3_s * step_s,
        state.source_volume_m3,
        destination_tank.capacity_m3 - state.destination_volume_m3,
    )
    return TransferState(
        source_volume_m3=state.source_volume_m3 - transferable,
        destination_volume_m3=state.destination_volume_m3 + transferable,
        elapsed_s=state.elapsed_s + step_s,
        last_flow_m3_s=point.flow_m3_s,
        status="Running",
    )


def estimate_completion_time_s(
    base_config: SystemConfiguration,
    source_tank: CylindricalTank,
    destination_tank: CylindricalTank,
    initial_state: TransferState,
    pump: PumpModel,
    step_s: float = 1.0,
    max_steps: int = 100_000,
) -> float | None:
    """Estimate completion time using the same changing-level model as animation."""
    state = initial_state
    for _ in range(max_steps):
        next_state = advance_transfer(base_config, source_tank, destination_tank, state, pump, step_s)
        if next_state.status != "Running":
            return next_state.elapsed_s if next_state.status in {"Source tank empty", "Destination tank full"} else None
        state = next_state
    return None
