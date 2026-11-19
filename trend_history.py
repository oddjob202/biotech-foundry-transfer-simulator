"""Samples of measured mass and temperatures on the simulation clock."""

from dataclasses import dataclass
from typing import Optional


TREND_SAMPLE_S = 30


@dataclass(frozen=True)
class TemperatureSample:
    time_s: float
    water_c: float
    inlet_c: float
    outlet_c: float
    reactor_target_c: Optional[float]
    batch_mass_kg: Optional[float] = None
    gross_mass_kg: Optional[float] = None


def record_temperature(
    history: list[TemperatureSample],
    sample: TemperatureSample,
    *,
    force: bool = False,
) -> list[TemperatureSample]:
    """Sample readings periodically and record command or weighing changes immediately."""
    if not history:
        return [sample]

    last = history[-1]
    if sample.time_s == last.time_s:
        # The clock is frozen while stopped, so only the last command at that time applies.
        return history if sample == last else [*history[:-1], sample]

    command_changed = (
        sample.inlet_c != last.inlet_c
        or sample.reactor_target_c != last.reactor_target_c
        or sample.batch_mass_kg != getattr(last, "batch_mass_kg", None)
        or sample.gross_mass_kg != getattr(last, "gross_mass_kg", None)
    )
    if not (force or command_changed or sample.time_s - last.time_s >= TREND_SAMPLE_S):
        return history

    return [*history, sample]
