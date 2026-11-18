"""Virtual instrumentation receives sampled process states."""
from typing import Protocol

from numpy.typing import NDArray


class TemperatureSensor(Protocol):
    def measure(self, time_s: NDArray, true_temperature_k: NDArray) -> NDArray: ...


class IdealTemperatureSensor:
    def measure(self, time_s: NDArray, true_temperature_k: NDArray) -> NDArray:
        return true_temperature_k.copy()
