from dataclasses import replace
from math import exp, log

import numpy as np
import pytest

from biotech_foundry.batch_reactor.model import BatchReactor, Equipment, Vessel, Water
from biotech_foundry.batch_reactor.solver import SolverSettings, simulate


def test_water_mass_and_geometry():
    reactor = BatchReactor(vessel=Vessel(working_volume_m3=0.05), water=Water(density_kg_m3=1000))
    assert reactor.mass_kg == pytest.approx(50)
    vessel = reactor.vessel
    assert vessel.liquid_height_m * vessel.cross_section_m2 == pytest.approx(0.05)
    assert vessel.wetted_area_m2 == pytest.approx(vessel.cross_section_m2 + 4 * 0.05 / vessel.diameter_m)


@pytest.mark.parametrize(("factory", "kwargs", "field"), [
    (Vessel, {"maximum_capacity_m3": 0.01}, "working_volume_m3"),
    (Vessel, {"maximum_capacity_m3": 1}, "maximum_capacity_m3"),
    (Vessel, {"diameter_m": 0}, "diameter_m"),
    (Water, {"density_kg_m3": float("nan")}, "density_kg_m3"),
    (Water, {"specific_heat_j_kg_k": 0}, "specific_heat_j_kg_k"),
    (Water, {"initial_temperature_k": 20}, "initial_temperature_k"),
    (Equipment, {"heater_rated_w": -1}, "heater_rated_w"),
    (Equipment, {"heater_fraction": 1.1}, "heater_fraction"),
    (Equipment, {"heater_efficiency": -0.1}, "heater_efficiency"),
    (Equipment, {"agitation_rpm": -1}, "agitation_rpm"),
    (Equipment, {"heater_off_s": -1}, "heater_off_s"),
    (BatchReactor, {"ua_w_k": -1}, "ua_w_k"),
    (SolverSettings, {"duration_s": 0}, "duration_s"),
    (SolverSettings, {"sample_interval_s": 0}, "sample_interval_s"),
    (SolverSettings, {"rtol": 0}, "rtol"),
    (SolverSettings, {"atol": 0}, "atol"),
])
def test_invalid_parameter(factory, kwargs, field):
    with pytest.raises(ValueError, match=field):
        factory(**kwargs)


def test_unheated_adiabatic_batch_stays_constant():
    reactor = BatchReactor(equipment=Equipment(heater_fraction=0), ua_w_k=0)
    result = simulate(reactor)
    np.testing.assert_array_equal(result.temperature_k, reactor.water.initial_temperature_k)
    np.testing.assert_array_equal(result.measured_k, result.temperature_k)
    np.testing.assert_array_equal(result.energy_residual_j, 0)


def test_adiabatic_heating_and_target_between_samples():
    reactor = BatchReactor(equipment=Equipment(heater_rated_w=2000, heater_fraction=0.5,
                                              heater_efficiency=0.8), ua_w_k=0)
    initial = reactor.water.initial_temperature_k
    result = simulate(reactor, SolverSettings(duration_s=1201, sample_interval_s=100),
                      target_k=initial + 2)
    expected_rise = 800 * result.time_s / reactor.thermal_capacitance_j_k
    np.testing.assert_allclose(result.temperature_k, initial + expected_rise, rtol=0, atol=1e-10)
    assert result.time_s[-1] == 1201
    assert result.heater_energy_j[-1] == 800 * 1201
    assert result.electrical_energy_j == 1000 * 1201
    assert result.target_time_s == pytest.approx(2 * reactor.thermal_capacitance_j_k / 800)


@pytest.mark.parametrize("initial_k", [333.15, 283.15])
def test_unheated_batch_approaches_ambient_from_either_side(initial_k):
    reactor = BatchReactor(water=Water(initial_temperature_k=initial_k),
                           equipment=Equipment(heater_fraction=0))
    result = simulate(reactor)
    ambient = reactor.ambient_temperature_k
    expected = ambient + (initial_k - ambient) * np.exp(
        -reactor.ua_w_k * result.time_s / reactor.thermal_capacitance_j_k
    )
    np.testing.assert_allclose(result.temperature_k, expected, rtol=0, atol=1e-6)
    assert np.sign(result.heat_lost_j[-1]) == np.sign(initial_k - ambient)


def test_heated_equilibrium_and_unreachable_targets():
    reactor = BatchReactor(equipment=Equipment(heater_rated_w=600, heater_efficiency=0.8))
    equilibrium = reactor.ambient_temperature_k + 40
    settings = SolverSettings(duration_s=400_000, sample_interval_s=500)
    result = simulate(reactor, settings, target_k=equilibrium)
    assert result.temperature_k[-1] == pytest.approx(equilibrium, abs=1e-6, rel=0)
    assert result.target_time_s is None
    assert simulate(reactor, settings, target_k=equilibrium + 5).target_time_s is None
    assert simulate(reactor, target_k=reactor.water.initial_temperature_k).target_time_s == 0


def test_heater_shutoff_energy_balance_and_tolerance_stability():
    cutoff = 5013.0
    reactor = BatchReactor(equipment=Equipment(heater_off_s=cutoff))
    settings = SolverSettings(duration_s=20_003, sample_interval_s=100)
    reference = simulate(reactor, replace(settings, rtol=1e-11, atol=1e-11))
    tau = reactor.thermal_capacitance_j_k / reactor.ua_w_k
    ambient = reactor.ambient_temperature_k
    rise_at_cutoff = reactor.equipment.heating_power_w / reactor.ua_w_k * (1 - exp(-cutoff / tau))
    target = ambient + 20
    result = simulate(reactor, settings, target_k=target)
    index = np.argmax(result.temperature_k)
    assert result.time_s[index] == cutoff
    assert result.heater_power_w[index - 1] == reactor.equipment.heating_power_w
    assert result.heater_power_w[index] == 0
    assert result.temperature_k[index] == pytest.approx(ambient + rise_at_cutoff, abs=1e-6, rel=0)
    assert result.temperature_k[-1] == pytest.approx(
        ambient + rise_at_cutoff * exp(-(settings.duration_s - cutoff) / tau), abs=1e-6, rel=0
    )
    assert result.target_time_s == pytest.approx(
        -tau * log(1 - 20 * reactor.ua_w_k / reactor.equipment.heating_power_w)
    )
    assert abs(result.energy_residual_j).max() < 1e-6
    np.testing.assert_allclose(result.temperature_k, reference.temperature_k, atol=1e-6, rtol=0)
    np.testing.assert_allclose(result.heat_lost_j, reference.heat_lost_j, atol=0.1, rtol=0)


def test_sensor_can_supply_an_independent_reading():
    class OffsetSensor:
        def measure(self, time_s, true_temperature_k):
            return true_temperature_k + 0.5

    result = simulate(BatchReactor(), sensor=OffsetSensor())
    np.testing.assert_array_equal(result.measured_k, result.temperature_k + 0.5)


def test_thermostat_cycles_at_exact_thresholds_between_samples():
    equipment = Equipment(temperature_setpoint_k=313.15)
    reactor = BatchReactor(equipment=equipment)
    settings = SolverSettings(duration_s=20_000, sample_interval_s=500)
    result = simulate(reactor, settings)
    switches = np.flatnonzero(np.diff(result.heater_power_w)) + 1
    assert switches.size >= 4
    off, on = switches[:2]
    assert result.heater_power_w[off] == 0
    assert result.heater_power_w[on] == equipment.heating_power_w
    assert result.temperature_k[off] == pytest.approx(315.15, abs=1e-6, rel=0)
    assert result.temperature_k[on] == pytest.approx(311.15, abs=1e-6, rel=0)
    assert result.temperature_k.max() == pytest.approx(315.15, abs=1e-6, rel=0)
    assert result.time_s[off] % settings.sample_interval_s != 0
    assert np.all(np.diff(result.time_s) > 0)
    active_s = np.sum(np.diff(result.time_s)[result.heater_power_w[:-1] > 0])
    assert result.heater_energy_j[-1] == pytest.approx(equipment.heating_power_w * active_s)
    assert result.electrical_energy_j == pytest.approx(equipment.electrical_power_w * active_s)
    assert abs(result.energy_residual_j).max() < 1e-6


@pytest.mark.parametrize(("initial_k", "heater_w"), [(320, 0), (315.15, 0), (313.15, 1275)])
def test_thermostat_initial_state(initial_k, heater_w):
    reactor = BatchReactor(water=Water(initial_temperature_k=initial_k),
                           equipment=Equipment(temperature_setpoint_k=313.15))
    result = simulate(reactor, SolverSettings(duration_s=20_000))
    assert result.heater_power_w[0] == heater_w
    assert np.any(result.heater_power_w > 0)


def test_thermostat_cannot_restart_without_passive_cooling():
    reactor = BatchReactor(ua_w_k=0, equipment=Equipment(temperature_setpoint_k=313.15))
    result = simulate(reactor, SolverSettings(duration_s=20_000))
    assert np.count_nonzero(np.diff(result.heater_power_w)) == 1
    assert result.temperature_k[-1] == pytest.approx(315.15, abs=1e-6, rel=0)


def test_scheduled_shutoff_overrides_thermostat_demand():
    reactor = BatchReactor(equipment=Equipment(temperature_setpoint_k=313.15, heater_off_s=6000))
    result = simulate(reactor, SolverSettings(duration_s=20_000))
    assert np.all(result.heater_power_w[result.time_s >= 6000] == 0)


def test_undersized_heater_stays_energized_below_setpoint():
    equipment = Equipment(temperature_setpoint_k=313.15, heater_rated_w=100)
    result = simulate(BatchReactor(equipment=equipment))
    assert np.all(result.heater_power_w == equipment.heating_power_w)
    assert np.max(result.temperature_k) < equipment.temperature_setpoint_k
