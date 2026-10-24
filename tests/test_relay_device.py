"""The relay device blueprint: while Ventra-EMS has control, the device switch follows its relay."""
import pytest


@pytest.fixture(scope="module")
def blueprint():
    from conftest import blueprint_path, load
    return load(blueprint_path("relay_device", "relay_device.yaml"))


def test_picks_the_switches_of_the_integration(blueprint):
    """Ventra-EMS's entities for a relay device `boiler`: switch.ems_boiler_take_control and
    switch.ems_boiler_relay (the add-on's control_entities.relay_load)."""
    inputs = blueprint["blueprint"]["input"]
    for name in ("ems_take_control", "ems_relay"):
        assert inputs[name]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    assert "switch.ems_boiler_take_control" in inputs["ems_take_control"]["description"]
    assert "switch.ems_boiler_relay" in inputs["ems_relay"]["description"]


def test_acts_only_while_ventra_ems_has_control(blueprint):
    """Take control on → the device follows the relay; off → the automation leaves it alone."""
    condition = blueprint["conditions"][0]["value_template"]
    assert "is_state(ems_take_control, 'on')" in condition
    triggers = blueprint["triggers"]
    assert {"trigger": "time_pattern", "seconds": "/5"} in triggers
    assert {str(t.get("entity_id")) for t in triggers if t["trigger"] == "state"} == {"ems_take_control", "ems_relay"}
