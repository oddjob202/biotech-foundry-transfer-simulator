import math

import pytest

from biotech_foundry.hydraulics import (HydraulicInputError, SystemConfiguration, calculate_hydraulics,
                                        flow_to_velocity, friction_factor, pipe_area, reynolds_number, water_properties)
from biotech_foundry.pumps import IllustrativeCentrifugalPump, find_operating_point, pump_catalog
from biotech_foundry.simulation import CylindricalTank, TransferState, advance_transfer, operating_point_at_state


def config(**changes):
    base = dict(diameter_m=0.025, length_m=20.0, roughness_m=0.000045, temperature_c=20.0,
                source_elevation_m=0.0, destination_elevation_m=8.0, minor_loss_k=4.0)
    base.update(changes)
    return SystemConfiguration(**base)


def test_pipe_area_and_velocity():
    assert pipe_area(0.1) == pytest.approx(math.pi * .01 / 4)
    assert flow_to_velocity(0.001, 0.1) == pytest.approx(0.12732395)


def test_reynolds_number_reference_case():
    assert reynolds_number(998.2, 1.0, 0.01, 0.001002) == pytest.approx(9962.1, rel=1e-4)


def test_laminar_factor_is_analytical():
    assert friction_factor(1000, 0.001) == pytest.approx(0.064)


def test_turbulent_factor_behavior():
    assert 0.015 < friction_factor(100_000, 0.001) < 0.03
    assert friction_factor(100_000, 0.01) > friction_factor(100_000, 0.0001)


def test_static_and_pressure_losses():
    result = calculate_hydraulics(config(), 60 / 60_000)
    assert result.static_head_m == 8.0
    assert result.pipe_head_loss_m > 0 and result.minor_head_loss_m > 0
    assert result.total_dynamic_head_m > 8.0


def test_loss_increases_with_length_and_decreases_with_diameter():
    q = 60 / 60_000
    assert calculate_hydraulics(config(length_m=40), q).pipe_head_loss_m > calculate_hydraulics(config(), q).pipe_head_loss_m
    assert calculate_hydraulics(config(diameter_m=.04), q).pipe_head_loss_m < calculate_hydraulics(config(), q).pipe_head_loss_m


def test_operating_point_is_valid_intersection():
    pump = IllustrativeCentrifugalPump()
    point = find_operating_point(pump, config())
    assert point is not None
    assert pump.min_flow_m3_s <= point.flow_m3_s <= pump.max_flow_m3_s
    assert pump.head_m(point.flow_m3_s) == pytest.approx(calculate_hydraulics(config(), point.flow_m3_s).total_dynamic_head_m)


def test_no_operating_point_above_shutoff_head():
    assert find_operating_point(IllustrativeCentrifugalPump(), config(destination_elevation_m=31)) is None


@pytest.mark.parametrize("bad", [config(diameter_m=0), config(temperature_c=-1), config(minor_loss_k=-1)])
def test_invalid_configurations_raise(bad):
    with pytest.raises(HydraulicInputError):
        calculate_hydraulics(bad, .001)


def test_out_of_range_pump_head_raises():
    with pytest.raises(HydraulicInputError):
        IllustrativeCentrifugalPump().head_m(.01)


def test_builtin_pump_catalog_has_distinct_supported_curves():
    pumps = pump_catalog()
    assert len(pumps) == 3
    for pump in pumps.values():
        assert pump.head_m(pump.min_flow_m3_s) > 0
        assert pump.head_m(pump.max_flow_m3_s) == pytest.approx(0)


def test_water_properties_reference_temperature():
    density, viscosity = water_properties(20)
    assert density == pytest.approx(998.2, rel=.002)
    assert viscosity == pytest.approx(0.001002, rel=.01)


def test_dynamic_tank_surface_and_transfer_conserve_volume():
    source = CylindricalTank(diameter_m=1.0, capacity_m3=1.0, base_elevation_m=0.0)
    destination = CylindricalTank(diameter_m=1.0, capacity_m3=1.0, base_elevation_m=1.0)
    state = TransferState(source_volume_m3=.5, destination_volume_m3=0.0)
    assert source.surface_elevation_m(.5) == pytest.approx(.5 / (math.pi / 4))
    point = operating_point_at_state(config(destination_elevation_m=0), source, destination, state, IllustrativeCentrifugalPump())
    assert point is not None
    later = advance_transfer(config(destination_elevation_m=0), source, destination, state, IllustrativeCentrifugalPump(), 10)
    assert later.status == "Running"
    assert later.source_volume_m3 < state.source_volume_m3
    assert later.destination_volume_m3 > state.destination_volume_m3
    assert later.source_volume_m3 + later.destination_volume_m3 == pytest.approx(.5)
