"""Export four time-series plots as a single static figure."""
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .solver import SimulationResult


def save_plots(result: SimulationResult, path: Path) -> None:
    figure = Figure(figsize=(10, 7), layout="constrained")
    FigureCanvasAgg(figure)
    water, heater, loss, sensor = figure.subplots(2, 2, sharex=True).flat
    time_s = result.time_s
    water.plot(time_s, result.temperature_k - 273.15)
    water.set(title="Water temperature", ylabel="Temperature (°C)")
    heater.step(time_s, result.heater_power_w, where="post", color="tab:orange")
    heater.set(title="Heater power delivered to water", ylabel="Power (W)")
    loss.plot(time_s, result.heat_loss_w, color="tab:red")
    loss.set(title="Net heat loss to ambient", ylabel="Heat loss (W)", xlabel="Time (s)")
    sensor.plot(time_s, result.temperature_k - 273.15, label="True")
    sensor.plot(time_s, result.measured_k - 273.15, "--", label="Virtual sensor")
    sensor.set(title="True and measured temperature", ylabel="Temperature (°C)", xlabel="Time (s)")
    sensor.legend()
    for axis in (water, heater, loss, sensor):
        axis.grid(alpha=0.25)
    figure.savefig(path, dpi=150)
