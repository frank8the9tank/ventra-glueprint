"""The Victron ESS battery blueprint: Ventra-EMS's battery setpoint (W, − = charge) → the ESS AC grid
setpoint with the sign turned round (+ = charge the battery, − = discharge); released: its own value."""
import jinja2
import pytest

from conftest import blueprint_path, load


@pytest.fixture(scope="module")
def blueprint():
    return load(blueprint_path("battery", "victron_ess_battery.yaml"))


def _branches(blueprint):
    return {branch["conditions"][0]["state"]: branch["sequence"] for branch in blueprint["actions"][0]["choose"]}


def test_picks_the_entities(blueprint):
    inputs = blueprint["blueprint"]["input"]
    assert inputs["ems_take_control"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "switch"}
    assert inputs["ems_setpoint"]["selector"]["entity"]["filter"][0] == {"integration": "ventra_ems", "domain": "number"}
    assert inputs["ess_setpoint"]["selector"]["entity"]["filter"][0] == {"domain": "number"}
    assert "number.ess_ac_grid_setpoint" in inputs["ess_setpoint"]["description"]
    assert inputs["released_value"]["default"] == 0


def test_runs_every_5_seconds_and_on_take_control(blueprint):
    """Like the other battery glueprints: every 5 s, not on every change of the setpoint."""
    triggers = blueprint["triggers"]
    assert {"trigger": "time_pattern", "seconds": "/5"} in triggers
    assert {"trigger": "state", "entity_id": "ems_take_control"} in triggers
    assert not any(trigger.get("entity_id") == "ems_setpoint" for trigger in triggers)


def test_controlled_writes_the_turned_setpoint_only_when_it_differs(blueprint):
    (write,) = _branches(blueprint)["on"]
    assert write["then"][0]["data"]["value"] == "{{ ess_value }}" and "!=" in write["if"][0]["value_template"]


def test_released_goes_back_to_its_own_value(blueprint):
    (write,) = _branches(blueprint)["off"]
    assert write["then"][0]["data"]["value"] == "{{ released }}"


def _render(blueprint, variable, setpoint=0, unit="W", low=-15000, high=15000, released=0):
    attributes = {"unit_of_measurement": unit, "min": low, "max": high}
    environment = jinja2.Environment()
    environment.globals.update(states=lambda entity_id: str(setpoint), state_attr=lambda entity_id, name: attributes.get(name))
    return environment.from_string(blueprint["variables"][variable]).render(
        ems_setpoint="number.ems_victron_battery_power", ess_setpoint="number.ess_ac_grid_setpoint",
        released_value=released).strip()


@pytest.mark.parametrize("setpoint, settings, expected", [
    (-3000, {}, "3000"),                       # Ventra-EMS charges 3 kW → ESS +3000 (charge)
    (2500, {}, "-2500"),                       # Ventra-EMS discharges 2.5 kW → ESS −2500
    (0, {}, "0"),
    ("unavailable", {}, "0"),
    (-20000, {}, "15000"),                     # inside the ESS range
    (4000, {"unit": "kW"}, "-4.0"),            # an ESS setpoint in kW
])
def test_the_sign_is_turned_round(blueprint, setpoint, settings, expected):
    assert _render(blueprint, "ess_value", setpoint, **settings) == expected


def test_the_released_value_in_the_entitys_unit(blueprint):
    assert _render(blueprint, "released", released=50) == "50"
    assert _render(blueprint, "released", released=50, unit="kW") == "0.05"
