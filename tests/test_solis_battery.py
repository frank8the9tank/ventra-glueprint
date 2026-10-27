"""The Solis hybrid battery blueprint: Ventra-EMS's battery setpoint (W, − = charge) → RC force
charge / discharge (the command first, then the power); released: the command "None"."""
import jinja2
import pytest

from conftest import blueprint_path, load


@pytest.fixture(scope="module")
def blueprint():
    return load(blueprint_path("battery", "solis_battery.yaml"))


def _branches(blueprint):
    return {branch["conditions"][0]["state"]: branch["sequence"] for branch in blueprint["actions"][0]["choose"]}


def test_picks_the_entities_of_the_integration(blueprint):
    inputs = blueprint["blueprint"]["input"]
    assert inputs["ems_take_control"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    assert inputs["ems_setpoint"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "number"}
    assert {name: inputs[name]["default"] for name in ("option_charge", "option_discharge", "option_off")} == {
        "option_charge": "Solis RC Force Battery Charge", "option_discharge": "Solis RC Force Battery Discharge", "option_off": "None"}


def test_runs_every_15_seconds_and_on_take_control(blueprint):
    assert {"trigger": "time_pattern", "seconds": "/15"} in blueprint["triggers"]
    assert {"trigger": "state", "entity_id": "ems_take_control"} in blueprint["triggers"]


def test_controlled_selects_the_command_before_the_powers(blueprint):
    command, charge, discharge = _branches(blueprint)["on"]
    assert command["if"][0]["value_template"] == "{{ setpoint > 0 }}"           # written every cycle (RC timeout)
    assert str(command["then"][0]["data"]["option"]) == "option_discharge"
    assert str(command["else"][0]["data"]["option"]) == "option_charge"
    assert charge["then"][0]["data"]["value"] == "{{ charge_value }}" and "!=" in charge["if"][0]["value_template"]
    assert discharge["then"][0]["data"]["value"] == "{{ discharge_value }}" and "!=" in discharge["if"][0]["value_template"]


def test_released_hands_the_battery_back(blueprint):
    (command,) = _branches(blueprint)["off"]
    assert str(command["then"][0]["data"]["option"]) == "option_off"


def _render(blueprint, variable, setpoint, unit="W", maximum=10000):
    attributes = {"unit_of_measurement": unit, "min": 0, "max": maximum}
    environment = jinja2.Environment()
    environment.globals.update(
        states=lambda entity_id: str(setpoint) if entity_id == "number.ems_solis_battery_power" else "0",
        state_attr=lambda entity_id, name: attributes.get(name))
    template = environment.from_string(blueprint["variables"][variable])
    return template.render(ems_setpoint="number.ems_solis_battery_power", charge_power="number.charge",
                           discharge_power="number.discharge").strip()


@pytest.mark.parametrize("setpoint, charge, discharge", [
    (-3000, "3000", "0"),          # charge 3 kW
    (2500, "0", "2500"),           # discharge 2.5 kW
    (0, "0", "0"),
    ("unavailable", "0", "0"),
    (-12000, "10000", "0"),        # inside the power's range
])
def test_the_setpoint_goes_to_one_power(blueprint, setpoint, charge, discharge):
    assert _render(blueprint, "charge_value", setpoint) == charge
    assert _render(blueprint, "discharge_value", setpoint) == discharge
