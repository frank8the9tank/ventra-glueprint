"""The SolarEdge StorEdge battery blueprint: Ventra-EMS's battery setpoint (W, − = charge) → the storage
remote control (command mode + charge or discharge limit); released: control mode disabled, command off."""
import jinja2
import pytest

from conftest import blueprint_path, load


@pytest.fixture(scope="module")
def blueprint():
    return load(blueprint_path("battery", "solaredge_storedge_battery.yaml"))


def _branches(blueprint):
    return {branch["conditions"][0]["state"]: branch["sequence"] for branch in blueprint["actions"][0]["choose"]}


def test_picks_the_entities_of_the_integration(blueprint):
    inputs = blueprint["blueprint"]["input"]
    assert inputs["ems_take_control"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    assert inputs["ems_setpoint"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "number"}
    assert {name: inputs[name]["default"] for name in ("option_remote", "option_released", "option_charge", "option_discharge", "option_off")} == {
        "option_remote": "Remote Control", "option_released": "Disabled", "option_charge": "Charge from Solar Power and Grid",
        "option_discharge": "Discharge to Maximize Export", "option_off": "Solar Power Only (Off)"}


def test_runs_every_5_seconds_and_on_take_control(blueprint):
    assert {"trigger": "time_pattern", "seconds": "/5"} in blueprint["triggers"]
    assert {"trigger": "state", "entity_id": "ems_take_control"} in blueprint["triggers"]


def test_controlled_sets_remote_control_the_command_and_both_limits(blueprint):
    control, command, charge, discharge = _branches(blueprint)["on"]
    assert str(control["then"][0]["data"]["option"]) == "option_remote" and "!=" in control["if"][0]["value_template"]
    assert command["if"][0]["value_template"] == "{{ setpoint > 0 }}"
    assert str(command["then"][0]["data"]["option"]) == "option_discharge"
    assert str(command["else"][0]["data"]["option"]) == "option_charge"
    assert "if" in command and "!=" not in command["if"][0]["value_template"]   # the command is written every cycle
    assert charge["then"][0]["data"]["value"] == "{{ charge_power }}"
    assert discharge["then"][0]["data"]["value"] == "{{ discharge_power }}"


def test_released_hands_the_battery_back(blueprint):
    control, command = _branches(blueprint)["off"]
    assert str(control["then"][0]["data"]["option"]) == "option_released"
    assert str(command["then"][0]["data"]["option"]) == "option_off"


def _render(blueprint, variable, setpoint, unit="W", maximum=5000):
    attributes = {"unit_of_measurement": unit, "min": 0, "max": maximum}
    environment = jinja2.Environment()
    environment.globals.update(
        states=lambda entity_id: str(setpoint) if entity_id == "number.ems_storedge_battery_power" else "0",
        state_attr=lambda entity_id, name: attributes.get(name))
    template = environment.from_string(blueprint["variables"][variable])
    return template.render(ems_setpoint="number.ems_storedge_battery_power", charge_limit="number.charge",
                           discharge_limit="number.discharge").strip()


@pytest.mark.parametrize("setpoint, charge, discharge", [
    (-3000, "3000", "0"),          # charge 3 kW
    (2500, "0", "2500"),           # discharge 2.5 kW
    (0, "0", "0"),
    ("unavailable", "0", "0"),
    (-9000, "5000", "0"),          # inside the limit's range
])
def test_the_setpoint_goes_to_one_limit(blueprint, setpoint, charge, discharge):
    assert _render(blueprint, "charge_power", setpoint) == charge
    assert _render(blueprint, "discharge_power", setpoint) == discharge


def test_a_limit_in_kw(blueprint):
    assert _render(blueprint, "charge_power", -3000, unit="kW", maximum=5) == "3.0"
