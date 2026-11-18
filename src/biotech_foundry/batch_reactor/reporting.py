"""Format simulation results independently of integration."""

from .model import BatchReactor
from .solver import SimulationResult


def summarize(reactor: BatchReactor, result: SimulationResult) -> str:
    vessel = reactor.vessel
    equipment = reactor.equipment
    cutoff = equipment.heater_off_s
    cutoff_text = "none" if cutoff is None else f"{cutoff:g} s"
    lines = [
        "Theoretical water-batch simulation",
        f"Initial water temperature    {result.temperature_k[0] - 273.15:.3f} °C",
        f"Final water temperature      {result.temperature_k[-1] - 273.15:.3f} °C",
        f"Maximum water temperature    {result.temperature_k.max() - 273.15:.3f} °C",
        f"Duration                     {result.time_s[-1]:g} s",
        f"Thermal energy supplied      {result.heater_energy_j[-1]:.6g} J",
        f"Electrical energy supplied   {result.electrical_energy_j:.6g} J",
        f"Net heat lost to ambient     {result.heat_lost_j[-1]:.6g} J",
        f"Peak absolute residual       {abs(result.energy_residual_j).max():.6g} J",
        f"Working liquid volume        {vessel.working_volume_m3:g} m³",
        f"Vessel capacity              {vessel.capacity_m3:g} m³",
        f"Liquid height                {vessel.liquid_height_m:g} m",
        f"Wetted wall and bottom area  {vessel.wetted_area_m2:g} m²",
        f"Water mass                   {reactor.mass_kg:g} kg",
        f"Rated electrical heater      {equipment.heater_rated_w:g} W",
        f"Heater operating fraction    {equipment.heater_fraction:.1%}",
        f"Heater-to-water efficiency   {equipment.heater_efficiency:.1%}",
        f"Heater shutoff               {cutoff_text}",
        f"Agitation setpoint           {equipment.agitation_rpm:g} RPM",
        f"Ambient temperature          {reactor.ambient_temperature_k - 273.15:g} °C",
        f"Overall heat loss UA         {reactor.ua_w_k:g} W/K",
    ]
    if result.target_k is not None:
        target = f"Target {result.target_k - 273.15:g} °C"
        if result.target_time_s is None:
            lines.append(f"{target} was unreachable within the configured run.")
        else:
            lines.append(f"{target} reached at {result.target_time_s:.6g} s.")
    if result.temperature_k.min() <= 273.15 or result.temperature_k.max() >= 373.15:
        lines.append("The prediction reaches or exceeds the atmospheric liquid-water range. "
                     "The energy balance excludes freezing and boiling.")
    return "\n".join(lines)
